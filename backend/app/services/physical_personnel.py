"""Personnel side effects of the existing authenticated Grant/Passage pipeline."""
from datetime import timedelta
from app import models as m
from app.core import time as timezone
from app.services.business import require, get, parse_time
from app.services.personnel import rules, scoped_employee, permissions, audit
from app.services.diagnostics import log


def work_plan(employee, at):
    return m.PlannedShift.objects.filter(employee=employee,kind='work',cancelled=False,start__lte=at,end__gt=at).order_by('start','pk').first()


def active_intent(employee, at):
    value=employee.passage_intent
    return value if value and parse_time(value['expiresAt'])>at else {}


def attendance_allowed(employee, at):
    day=timezone.localdate(at)
    return not m.LeaveRequest.objects.filter(employee=employee,status='approved',start__lte=day,end__gte=day).exists() and not m.PlannedShift.objects.filter(employee=employee,kind='off',cancelled=False,start__lte=at,end__gt=at).exists()


def intent_action(p,user,branch):
    employee=scoped_employee(user,branch,p.get('employeeId')); now=timezone.now()
    require(employee.active,'Personel pasif.')
    action=p.get('intent'); require(action in ['break','finish','cancel','start'],'Mesai seçimi geçersiz.')
    require(not m.Grant.objects.filter(employee=employee,confirmed=False,expires_at__gt=now).exists(),'Bekleyen turnike geçişi var; önce tamamlayın.')
    shift=m.Shift.objects.filter(employee=employee,exit__isnull=True,simulated=False).first()
    visit=m.PersonnelVisit.objects.filter(employee=employee,exit__isnull=True).first()
    inside=visit is not None
    if action=='start':
        require(inside and visit.entry_event_id is not None and not shift,'Mesai için doğrulanmış giriş olmalı ve açık mesai bulunmamalı.')
        plan=work_plan(employee,now); require(plan and attendance_allowed(employee,now),'Şu anda geçerli çalışma vardiyası yok. Yönetici onaylı manuel işlem gerekli.')
        require(not m.Shift.objects.filter(employee=employee,planned_id=plan.id,simulated=False).exists(),'Bu vardiyanın mesaisi zaten kaydedilmiş.')
        shift=m.Shift.objects.create(branch=branch,employee=employee,entry=now,planned_id=plan.id,source='device',reason='Personel tarafından doğrulanmış giriş sonrası başlatıldı.')
        audit('startPhysicalWork',shift,user,branch,{'employeeId':str(employee.id)})
        return {'message':'Mesai başladı.'}
    if action!='cancel':
        require(shift and inside,'Bu işlem için içeride olunmalı ve açık mesai bulunmalı.')
        if action=='break':
            require(permissions(user)['attendanceBreak'],'Mola yetkisi yok.')
            require(not m.ShiftBreak.objects.filter(shift=shift,end__isnull=True).exists(),'Mola zaten açık.')
    before=dict(employee.passage_intent)
    employee.passage_intent={} if action=='cancel' else {'action':action,'shiftId':str(shift.id),'actorId':user.id,'expiresAt':(now+timedelta(minutes=15)).isoformat()}
    employee.save()
    audit('physicalAttendanceIntent',employee,user,branch,{'intent':action,'before':before})
    return {'message':'Seçim iptal edildi.' if action=='cancel' else 'Fiziksel çıkış bekleniyor.'}


def authorize(employee, card_active, uid, direction, device, branch, now):
    visit=m.PersonnelVisit.objects.filter(employee=employee,exit__isnull=True).first() if employee else None
    if direction=='auto': direction='exit' if visit else 'entry'
    reason=''
    if direction not in ['entry','exit']: reason='Fiziksel yön gerekli'
    elif not device.enabled or not device.last_seen or now-device.last_seen>timedelta(seconds=60) or device.mode!='auto': reason='Cihaz çevrimdışı veya bakımda'
    elif device.sensor!='ready': reason='Geçiş sensörleri hazır değil'
    elif device.direction not in ['both',direction]: reason='Cihaz bu yön için yetkili değil'
    elif m.DeviceCommand.objects.filter(device=device,status__in=['queued','sent'],expires_at__gt=now).exists(): reason='Donanım testi devam ediyor'
    elif m.CardCapture.objects.filter(device=device,cancelled=False,consumed_at__isnull=True,expires_at__gt=now).exists(): reason='Kart tanımlama devam ediyor'
    elif m.Grant.objects.filter(device=device,confirmed=False,expires_at__gt=now).exists(): reason='Turnikede bekleyen işlem var'
    elif not employee: reason='Personel kartı bilinmiyor'
    elif not card_active: reason='Personel kartı pasif veya iptal edilmiş'
    elif m.Attempt.objects.filter(branch=branch,card=uid,at__gt=now-timedelta(seconds=10)).exists(): reason='Tekrar okutma; kısa süre bekleyin'
    elif direction=='exit' and not visit: reason='Açık personel ziyareti yok'
    elif direction=='entry' and not employee.active: reason='Personel pasif'
    elif direction=='entry' and visit: reason='Personel zaten içeride'
    elif m.Grant.objects.filter(employee=employee,confirmed=False,expires_at__gt=now).exists(): reason='Personelin bekleyen geçişi var'
    attempt=m.Attempt.objects.create(branch=branch,employee=employee,card=uid,device=device,direction=direction,status='rejected' if reason else 'granted',reason=reason or 'Fiziksel personel geçişi bekleniyor',at=now)
    result={'approved':not bool(reason),'subjectType':'employee','employeeId':str(employee.id) if employee else None,'memberName':'Personel','reason':reason,'direction':direction,'serverTime':now.isoformat()}
    if not reason:
        shift=m.Shift.objects.filter(employee=employee,exit__isnull=True,simulated=False).first()
        plan=work_plan(employee,now)
        context={'shiftId':str(shift.id) if shift else None,'planId':str(plan.id) if plan else None,'intent':active_intent(employee,now)}
        grant=m.Grant.objects.create(branch=branch,attempt=attempt,employee=employee,device=device,direction=direction,context=context,expires_at=now+timedelta(seconds=30))
        result.update(grantId=str(grant.id),expiresAt=grant.expires_at.isoformat())
    audit('authorizePersonnel',attempt,None,branch,{'employeeId':str(employee.id) if employee else None,'approved':not bool(reason)})
    log(device,'rfid','Personel kartı okundu: '+uid)
    log(device,'access_rejected' if reason else 'access_granted',reason or 'Personel fiziksel geçiş izni verildi.','warning' if reason else 'info')
    return result


def confirm(grant,event,branch):
    employee=grant.employee; at=event.occurred_at
    visit=m.PersonnelVisit.objects.filter(employee=employee,exit__isnull=True).first()
    shift=m.Shift.objects.filter(employee=employee,exit__isnull=True,simulated=False).first()
    message='GECIS TAMAMLANDI'
    if grant.direction=='entry':
        require(not visit,'Personel zaten içeride.')
        m.PersonnelVisit.objects.create(branch=branch,employee=employee,device=grant.device,entry_event_id=event.id,entry=at)
        pause=m.ShiftBreak.objects.filter(shift=shift,end__isnull=True).first() if shift else None
        if pause:
            require(at>pause.start,'Mola dönüş zamanı geçersiz.'); pause.end=at; pause.save(); message='MOLA BITTI'
        elif not shift:
            plan=work_plan(employee,at)
            if plan and plan.auto_start and attendance_allowed(employee,at) and employee.active and not m.Shift.objects.filter(employee=employee,planned_id=plan.id,simulated=False).exists():
                shift=m.Shift.objects.create(branch=branch,employee=employee,device_id=grant.device_id,entry=at,planned_id=plan.id,source='device'); message='MESAI BASLADI'
    else:
        require(visit and at>visit.entry,'Açık personel ziyareti veya çıkış zamanı geçersiz.')
        visit.exit=at; visit.exit_event_id=event.id; visit.save()
        choice=grant.context.get('intent',{})
        if shift and grant.context.get('shiftId')==str(shift.id):
            pause=m.ShiftBreak.objects.filter(shift=shift,end__isnull=True).first()
            if choice.get('action')=='finish' and choice.get('shiftId')==str(shift.id):
                for row in m.ShiftBreak.objects.filter(shift=shift,end__isnull=True): row.end=at; row.save()
                require(at>shift.entry,'Mesai çıkışı girişten sonra olmalı.'); shift.exit=at; shift.save(); message='MESAI BITTI'
            elif not pause:
                # An unmarked physical absence must not be counted as work either.
                paid=choice.get('action')=='break' and choice.get('shiftId')==str(shift.id) and rules(branch)['paidBreaks']
                m.ShiftBreak.objects.create(branch_id=branch.id,shift=shift,start=at,paid=paid); message='MOLAYA CIKILDI'
        if employee.passage_intent==choice: employee.passage_intent={}; employee.save()
    attendance=m.AttendanceEvent.objects.create(branch_id=branch.id,employee_id=employee.id,shift_id=shift.id if shift else None,device_id=grant.device_id,passage_id=event.id,occurred_at=at,direction=grant.direction,source='device',uid=grant.attempt.card,approved=True,message=('Tek sensör prototipi: ' if grant.context.get('validationMode')=='single_sensor_prototype' else '')+message)
    audit('physicalPersonnelPassage',attendance,None,branch,{'employeeId':str(employee.id),'passageId':str(event.id),'message':message})
    return {'message':message,'employeeId':str(employee.id),'shiftId':str(shift.id) if shift else None}
