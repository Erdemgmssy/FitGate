from datetime import datetime, time, timedelta
import re
from sqlalchemy import select
from app import models as m
from app.core import time as timezone
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_session
from app.services.business import require, RuleError, get, parse_day, parse_time, integer, validate_photo, months
from app.schemas.member import normalize_phone, normalize_email

ADMIN_ACTIONS = {'saveEmployee','assignEmployeeCard','employeeCardStatus','savePlannedShift','cancelPlannedShift','saveLeaveType','reviewLeave','saveAttendanceRules','saveRolePolicy','correctAttendance'}
SELF_ACTIONS = {'requestLeave','withdrawLeave','manualAttendance','attendanceBreak','simulateAttendance','scanEmployee','physicalAttendanceIntent'}
ADMIN_ACTIONS.add('correctPersonnelPresence')
ACTIONS = ADMIN_ACTIONS | SELF_ACTIONS
DEFAULT_RULES = {'lateGraceMinutes':5,'overtimeGraceMinutes':15,'missingExitHours':16,'duplicateSeconds':10,'paidBreaks':False}
DEFAULT_PERMISSIONS = {'manualAttendance':False,'requestLeave':True,'attendanceBreak':True,'simulateAttendance':False,'classBooking':True,'classAttendance':True,'productSales':True,'productDiscount':False,'productReturns':False,'memberManagement':True,'cardManagement':True,'collections':True,'deviceRead':True}
DEFAULT_PERMISSIONS['manualVisits'] = False


def rules(branch):
    return {**DEFAULT_RULES,**branch.attendance_rules}


def permissions(user):
    if user.role == 'admin': return {key:True for key in DEFAULT_PERMISSIONS}
    policy=m.RolePolicy.objects.filter(branch_id=user.branch_id,role=user.role).first()
    return {**DEFAULT_PERMISSIONS,**({'memberManagement':False,'cardManagement':False,'collections':False,'deviceRead':False} if user.role=='trainer' else {}),**(policy.permissions if policy else {})}


def own_employee(user):
    return m.Employee.objects.filter(branch_id=user.branch_id,user_id=user.id).first()


def scoped_employee(user, branch, key=None):
    employee=get(m.Employee,key,branch) if key else own_employee(user)
    require(employee is not None,'Bu hesap bir personel kaydına bağlı değil; yönetici hesabı eşleştirmeli.')
    require(user.role=='admin' or employee.user_id==user.id,'Yalnızca kendi personel kaydınıza erişebilirsiniz.')
    return employee


def audit(action, obj, user, branch, detail, before=None):
    safe={key:value for key,value in detail.items() if key not in ['password','photo']}
    m.Audit.objects.create(branch=branch,actor=user,type=action,entity_id=str(obj.id) if obj else '',detail=safe,before=before,after=None)


def overlap(start,end,other_start,other_end):
    return start<other_end and other_start<end


def leave_window(row):
    return timezone.make_aware(datetime.combine(row.start,time.min)),timezone.make_aware(datetime.combine(row.end+timedelta(days=1),time.min))


def leave_days(start,end,weekdays):
    return sum(((start+timedelta(days=i)).weekday()+1)%7 in weekdays for i in range((end-start).days+1))


def validate_leave(employee, item, branch):
    snapshot=item.rules
    require(employee.start_date is None or item.start>=employee.start_date,'İzin işe başlangıçtan önce olamaz.')
    service=snapshot.get('serviceMonths',0)
    require(not service or employee.start_date is not None and months(employee.start_date,service)<=item.start,'İzin hak ediş süresi henüz dolmadı.')
    for other in m.LeaveRequest.objects.filter(employee=employee,status='approved').exclude(pk=item.pk):
        require(other.end<item.start or item.end<other.start,'Onaylı izin ile çakışıyor.')
    require(not m.Shift.objects.filter(employee=employee,exit__isnull=True).exists() or not item.start<=timezone.localdate()<=item.end,'Açık mesai varken bugünü kapsayan izin onaylanamaz.')
    cap=snapshot.get('annualDays')
    if cap is not None:
        for year in range(item.start.year,item.end.year+1):
            first=parse_day(f'{year}-01-01'); last=parse_day(f'{year}-12-31')
            count=leave_days(max(item.start,first),min(item.end,last),snapshot['weekdays'])
            for previous in m.LeaveRequest.objects.filter(employee=employee,type_id=item.type_id,status='approved').exclude(pk=item.pk):
                if previous.start<=last and previous.end>=first:
                    count+=leave_days(max(previous.start,first),min(previous.end,last),previous.rules.get('weekdays',list(range(7))))
            require(count<=cap,'Yıllık izin hakkı yetersiz.')


def assign_card(employee, uid, branch):
    require(isinstance(uid,str),'Kart UID geçersiz.')
    uid=uid.strip().upper()
    require(re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,99}',uid),'Kart UID geçersiz.')
    existing=m.EmployeeCard.objects.filter(uid=uid).first()
    if existing and existing.employee_id==employee.id and existing.status=='active': return existing
    require(not existing and not m.Card.objects.filter(uid=uid).exists() and not m.Employee.objects.filter(card=uid).exclude(pk=employee.pk).exists(),'Kart başka kayda ait veya daha önce iptal edilmiş.')
    m.EmployeeCard.objects.filter(employee=employee,status='active').update(status='cancelled')
    employee.card=uid; employee.save()
    return m.EmployeeCard.objects.create(branch_id=branch.id,employee=employee,uid=uid)


def choose_plan(employee, at):
    plans=list(m.PlannedShift.objects.filter(employee=employee,cancelled=False,kind='work').order_by('start','pk'))
    # Match the closest start within its shift, including early arrivals and overnight work.
    return min((p for p in plans if p.start-timedelta(hours=4)<=at<p.end),key=lambda p:abs((p.start-at).total_seconds()),default=None)


def record_attendance(action,p,user,branch,device=None):
    now=timezone.now(); config=rules(branch)
    source='device' if device else 'simulation' if action in ['simulateAttendance','scanEmployee'] else 'manual'
    employee=None; message=''; approved=False; shift=None
    uid=str(p.get('uid','')).strip().upper()[:100]
    occurred=parse_time(p['occurredAt']) if device and p.get('occurredAt') else now
    require(occurred<=now+timedelta(seconds=5) and now-occurred<=timedelta(minutes=5),'Mesai olayı zamanı geçersiz.')
    direction=p.get('direction','auto'); require(direction in ['entry','exit','auto'],'Mesai yönü geçersiz.')
    if source!='manual':
        card=m.EmployeeCard.objects.filter(uid=uid,branch_id=branch.id).first()
        # The fallback only serves pre-migration/test legacy records without a card history.
        employee=m.Employee.objects.filter(card=uid,branch_id=branch.id).first() if not card else card.employee
        if card and card.status!='active': message='Mesai kartı iptal edilmiş.'
        elif not employee: message='Personel kartı bilinmiyor.'
    else:
        require(user is not None and (user.role=='admin' or permissions(user)['manualAttendance']),'Manuel mesai yetkisi yok.')
        employee=scoped_employee(user,branch,p.get('employeeId'))
        require(isinstance(p.get('reason'),str) and p['reason'].strip(),'Manuel işlem gerekçesi gerekli.')
    if user and user.role!='admin':
        if employee is None and message:
            employee=own_employee(user)
        require(employee is not None and employee.user_id==user.id,'Yalnızca kendi mesai kartınız kullanılabilir.')
        if source=='manual':
            require(not m.PersonnelVisit.objects.filter(employee=employee,exit__isnull=True).exists() and not m.Shift.objects.filter(employee=employee,source='device',exit__isnull=True).exists(),'Fiziksel mesai için başlat/mola/bitir seçimlerini kullanın; manuel düzeltme admin onayı gerektirir.')
    if source=='simulation':
        require(settings.allow_device_simulation,'Kontrollü simülasyon sunucuda kapalı.')
        require(user and (user.role=='admin' or permissions(user)['simulateAttendance']),'Simülasyon yetkisi yok.')
    if device:
        require(device.enabled and not device.simulated,'Gerçek, doğrulanmış cihaz gerekli.')
        require(False,'Mesai yalnızca doğrulanmış fiziksel geçiş üzerinden kaydedilir.')
    if employee and not message:
        shift=m.Shift.objects.filter(employee=employee,exit__isnull=True).first()
        last=m.AttendanceEvent.objects.filter(employee_id=employee.id,approved=True).order_by('-occurred_at').first()
        legacy=m.Shift.objects.filter(employee=employee).order_by('-entry').first()
        last_at=last.occurred_at if last else (legacy.exit or legacy.entry) if legacy else None
        if last_at and (occurred-last_at).total_seconds()<config['duplicateSeconds']: message='Tekrar okutma; kısa süre bekleyin.'
        elif direction=='entry' and shift: message='Zaten açık mesai var.'
        elif direction=='exit' and not shift: message='Açık mesai yok.'
        elif shift:
            if source!='simulation' and shift.simulated or source=='simulation' and not shift.simulated: message='Simülasyon ve gerçek mesai birbirine karıştırılamaz.'
            elif occurred<=shift.entry: message='Çıkış girişten sonra olmalı.'
            else:
                for pause in m.ShiftBreak.objects.filter(shift_id=shift.id,end__isnull=True): pause.end=occurred; pause.save()
                shift.exit=occurred; shift.save(); direction='exit'; approved=True
        elif not employee.active: message='Personel pasif.'
        elif any(row.start<=timezone.localdate(occurred)<=row.end for row in m.LeaveRequest.objects.filter(employee=employee,status='approved')): message='Personel onaylı izinde.'
        elif any(row.start<=occurred<row.end for row in m.PlannedShift.objects.filter(employee=employee,cancelled=False,kind='off')): message='Personelin izin günü.'
        else:
            prior=m.Shift.objects.filter(employee=employee,exit__isnull=False).order_by('-exit').first()
            if prior and prior.exit>occurred: message='Mesai geçmişi ile çakışıyor.'
            else:
                plan=choose_plan(employee,occurred)
                shift=m.Shift.objects.create(branch=branch,employee=employee,entry=occurred,planned_id=plan.id if plan else None,source=source,simulated=source=='simulation',device_id=device.id if device else None,reason=p.get('reason','')[:1500]); direction='entry'; approved=True
    message=message or ('Simülasyon: ' if source=='simulation' else '')+('Mesai girişi kaydedildi.' if direction=='entry' else 'Mesai çıkışı kaydedildi.')
    event=m.AttendanceEvent.objects.create(branch_id=branch.id,employee_id=employee.id if employee else None,shift_id=shift.id if shift else None,device_id=device.id if device else None,occurred_at=occurred,direction=direction,source=source,uid=uid,approved=approved,message=message,actor_id=user.id if user else None)
    audit(action,event,user,branch,{'employeeId':str(employee.id) if employee else None,'approved':approved,'source':source,'direction':direction,'reason':p.get('reason','')})
    return {'approved':approved,'message':message,'eventId':str(event.id),'shiftId':str(shift.id) if shift else None,'source':source}


def apply(action,p,user,branch,device=None):
    if action=='physicalAttendanceIntent':
        require(user is not None,'Personel oturumu gerekli.')
        from .physical_personnel import intent_action
        return intent_action(p,user,branch)
    if action in ['scanEmployee','simulateAttendance','manualAttendance']: return record_attendance(action,p,user,branch,device)
    require(user is not None,'Personel yönetimi kullanıcı oturumu gerektirir.')
    require(user.role=='admin' or action not in ADMIN_ACTIONS,'Yönetici yetkisi gerekiyor.')
    if action in DEFAULT_PERMISSIONS: require(permissions(user)[action],'Bu işlem için rol yetkisi yok.')
    obj=None; before=None
    if action=='correctPersonnelPresence':
        employee=get(m.Employee,p.get('employeeId'),branch); reason=str(p.get('reason','')).strip()
        require(0<len(reason)<=1500 and p.get('direction') in ['entry','exit'],'Düzeltme yönü ve gerekçesi gerekli.')
        now=timezone.now(); opened=m.PersonnelVisit.objects.filter(employee=employee,exit__isnull=True).first()
        require(not m.Grant.objects.filter(employee=employee,confirmed=False,expires_at__gt=now).exists(),'Bekleyen fiziksel geçiş var.')
        if p['direction']=='exit':
            require(opened and now>opened.entry,'Açık ziyaret yok veya zaman geçersiz.'); opened.exit=now; opened.correction_reason=reason; opened.save(); obj=opened
        else:
            require(not opened,'Personel zaten içeride.'); device=get(m.Device,p.get('deviceId'),branch)
            obj=m.PersonnelVisit.objects.create(branch=branch,employee=employee,device=device,entry=now,correction_reason=reason)
        audit(action,obj,user,branch,{'employeeId':str(employee.id),'reason':reason,'direction':p['direction']})
        return {'message':'Yönetici onaylı personel ziyaret düzeltmesi kaydedildi. Mesai ayrıca düzeltilmelidir.'}
    if action=='saveEmployee':
        require('createAccount' not in p or type(p['createAccount'])==bool,'Hesap oluşturma seçimi geçersiz.')
        obj=get(m.Employee,p['id'],branch) if p.get('id') else m.Employee(branch=branch,type='fixed')
        before={'name':obj.name,'active':obj.active,'userId':obj.user_id} if p.get('id') else None
        name=p.get('name',obj.name or '').strip(); require(1<=len(name)<=120,'Ad soyad gerekli (en fazla 120 karakter).')
        role=p.get('role',obj.role or 'staff'); require(role in ['admin','staff','trainer'],'Rol geçersiz.')
        phone=p.get('phone',obj.phone or ''); email=p.get('email',obj.email or '')
        try: phone=normalize_phone(phone) if phone else ''; email=normalize_email(email) if email else ''
        except ValueError as error: raise RuleError(str(error)) from None
        require(not email or not m.Employee.objects.filter(branch_id=branch.id,email=email).exclude(pk=obj.id).exists(),'Bu e-posta ile kayıtlı personel var.')
        job=p.get('jobTitle',obj.job_title or '').strip(); require(len(job)<=120,'Görev adı çok uzun.')
        obj.name=name; obj.role=role; obj.phone=phone; obj.email=email; obj.job_title=job
        obj.type=p.get('type',obj.type or 'fixed'); require(obj.type in ['fixed','hourly'],'Çalışan tipi geçersiz.')
        obj.start_date=parse_day(p['startDate']) if p.get('startDate') else obj.start_date
        if 'photo' in p: obj.photo=validate_photo(p['photo'])
        if 'active' in p: require(isinstance(p['active'],bool),'Aktiflik geçersiz.'); obj.active=p['active']
        if 'branchId' in p: require(str(p['branchId'])==str(branch.id),'Başka şubeye personel atama yetkisi yok.')
        if p.get('userId') and not obj.user_id:
            account=get_session().get(m.User,integer(p['userId'],1,2147483647))
            require(account and account.branch_id==branch.id and not m.Employee.objects.filter(user_id=account.id).exists(),'Hesap bu şubeye ait değil veya zaten bağlı.')
            require(account.role==role,'Hesap ve personel rolleri aynı olmalı.')
            obj.user=account
        if p.get('createAccount'):
            require(not obj.user_id and email,'Hesap için benzersiz e-posta gerekli.')
            password=p.get('password'); require(isinstance(password,str) and 12<=len(password)<=128 and any(c.isalpha() for c in password) and any(c.isdigit() for c in password),'Şifre 12-128 karakter, harf ve sayı içermeli.')
            require(not m.User.objects.filter(email=email).exists() and not m.User.objects.filter(username=email).exists(),'Bu e-posta ile giriş hesabı var; mevcut hesabı eşleştirin.')
            obj.user=m.User.objects.create(username=email,email=email,password=hash_password(password),full_name=name,role=role,branch=branch,is_active=obj.active if obj.active is not None else True)
        if obj.user:
            from .system_settings import protect_admin
            protect_admin(obj.user,obj.active is not False,role)
            require(obj.user.id!=user.id or obj.active is not False and role=='admin','Kendi yönetici hesabınızı pasifleştiremez veya rolünü düşüremezsiniz.')
            if obj.user.role!=role or obj.active is False:
                m.AuthSession.objects.filter(user_id=obj.user.id,revoked=False).update(revoked=True)
            obj.user.full_name=name; obj.user.role=role; obj.user.is_active=obj.active if obj.active is not None else True; obj.user.save()
        obj.save()
        if p.get('card'): assign_card(obj,p['card'],branch)
    elif action in ['assignEmployeeCard','employeeCardStatus']:
        if action=='assignEmployeeCard': obj=assign_card(get(m.Employee,p.get('employeeId'),branch),p.get('uid'),branch)
        else:
            obj=get(m.EmployeeCard,p.get('id'),branch); require(obj.status=='active' and p.get('status') in ['lost','cancelled'],'Kart durumu geçersiz.')
            obj.status=p['status']; obj.save(); obj.employee.card=None; obj.employee.save()
    elif action=='savePlannedShift':
        employee=get(m.Employee,p.get('employeeId'),branch); require(employee.active,'Personel pasif.')
        start=parse_time(p.get('start')); end=parse_time(p.get('end')); require(start<end<=start+timedelta(hours=24),'Vardiya 0-24 saat arasında olmalı.')
        kind=p.get('kind','work'); require(kind in ['work','off'],'Vardiya türü geçersiz.')
        pause=integer(p.get('breakMinutes',0),0,1440); require(pause*60<(end-start).total_seconds(),'Planlanan mola vardiyadan kısa olmalı.')
        starts=[start]
        if p.get('repeatUntil'):
            until=parse_day(p['repeatUntil']); first=timezone.localdate(start); require(first<=until<=first+timedelta(days=366),'Tekrar aralığı en fazla 366 gün.')
            weekdays=p.get('weekdays'); require(isinstance(weekdays,list) and weekdays and all(type(d)==int and 0<=d<=6 for d in weekdays),'Tekrar günleri geçersiz.')
            starts=[start+timedelta(days=i) for i in range((until-first).days+1) if ((first+timedelta(days=i)).weekday()+1)%7 in weekdays]
            require(starts,'Seçili günlerde vardiya yok.')
        for at in starts:
            finish=at+(end-start)
            require(not any(overlap(at,finish,row.start,row.end) for row in m.PlannedShift.objects.filter(employee=employee,cancelled=False)),'Vardiya/izin günü çakışıyor.')
            require(not any(overlap(at,finish,*leave_window(row)) for row in m.LeaveRequest.objects.filter(employee=employee,status='approved')),'Onaylı izin ile vardiya çakışıyor.')
            require(type(p.get('autoStart',True)) is bool,'Otomatik mesai seçimi geçersiz.')
            obj=m.PlannedShift.objects.create(branch_id=branch.id,employee=employee,start=at,end=finish,kind=kind,break_minutes=pause,actor=user,auto_start=p.get('autoStart',True))
            audit(action,obj,user,branch,p)
        return {'count':len(starts),'id':str(obj.id)}
    elif action=='cancelPlannedShift':
        obj=get(m.PlannedShift,p.get('id'),branch); require(p.get('reason','').strip(),'Vardiya iptal gerekçesi gerekli.'); require(not obj.cancelled,'Vardiya zaten iptal.'); obj.cancelled=True; obj.save()
    elif action=='attendanceBreak':
        employee=scoped_employee(user,branch,p.get('employeeId')); shift=m.Shift.objects.filter(employee=employee,exit__isnull=True).first(); require(shift,'Mola için açık mesai gerekli.')
        require(user.role=='admin' or shift.source!='device','Fiziksel mesai molası doğrulanmış çıkış/giriş ile tamamlanır; mola seçimini kullanın.')
        now=timezone.now(); opened=m.ShiftBreak.objects.filter(shift_id=shift.id,end__isnull=True).first()
        require(p.get('direction') in ['start','end'],'Mola yönü gerekli.')
        if p['direction']=='end': require(opened and now>opened.start,'Açık mola yok.'); opened.end=now; opened.save(); obj=opened
        else:
            require(not opened,'Mola zaten açık.')
            obj=m.ShiftBreak.objects.create(branch_id=branch.id,shift=shift,start=now,paid=rules(branch)['paidBreaks'])
    elif action=='correctAttendance':
        obj=get(m.Shift,p.get('id'),branch)
        require(isinstance(p.get('reason'),str) and 0<len(p['reason'].strip())<=1500,'Düzeltme gerekçesi gerekli.')
        before={'entry':obj.entry.isoformat(),'exit':obj.exit.isoformat() if obj.exit else None,'reason':obj.reason}
        start=parse_time(p['entry']) if p.get('entry') else obj.entry
        end=parse_time(p['exit']) if p.get('exit') else obj.exit
        require(start<=timezone.now() and (end is None or start<end<=timezone.now()),'Mesai tarihleri geçersiz.')
        require(not any(overlap(start,end or timezone.now()+timedelta(seconds=1),other.entry,other.exit or timezone.now()+timedelta(seconds=1)) for other in m.Shift.objects.filter(employee=obj.employee).exclude(pk=obj.id)),'Başka mesai ile çakışıyor.')
        for pause in m.ShiftBreak.objects.filter(shift_id=obj.id):
            require(pause.start>=start and (not end or (pause.end or end)<=end),'Düzeltme mevcut mola aralığını dışarıda bırakamaz.')
            if end and not pause.end: pause.end=end; pause.save()
        obj.entry=start; obj.exit=end; obj.reason=p['reason'].strip(); obj.save()
    elif action=='saveLeaveType':
        obj=get(m.LeaveType,p['id'],branch) if p.get('id') else m.LeaveType(branch_id=branch.id)
        name=p.get('name','').strip(); require(0<len(name)<=120,'İzin türü adı gerekli.')
        weekdays=p.get('weekdays',list(range(7))); require(isinstance(weekdays,list) and weekdays and all(type(day)==int and 0<=day<=6 for day in weekdays),'İzin hesabı günleri geçersiz.')
        obj.name=name; obj.annual_days=integer(p['annualDays'],0,366) if p.get('annualDays') not in [None,''] else None; obj.service_months=integer(p.get('serviceMonths',0),0,1200); obj.weekdays=weekdays; obj.active=p.get('active',True); require(type(obj.active)==bool,'Aktiflik geçersiz.'); obj.save()
    elif action=='requestLeave':
        employee=scoped_employee(user,branch,p.get('employeeId')); require(employee.active,'Personel pasif.')
        kind=get(m.LeaveType,p.get('typeId'),branch); require(kind.active,'İzin türü kapalı.')
        start=parse_day(p.get('start')); end=parse_day(p.get('end')); require(timezone.localdate()<=start<=end<=start+timedelta(days=366),'İzin tarihleri geçersiz.')
        reason=p.get('reason','').strip(); require(0<len(reason)<=1500,'İzin gerekçesi gerekli.')
        require(not any(row.start<=end and start<=row.end for row in m.LeaveRequest.objects.filter(employee=employee,status__in=['pending','approved'])),'İzin talebi mevcut talep ile çakışıyor.')
        obj=m.LeaveRequest.objects.create(branch_id=branch.id,employee=employee,type_id=kind.id,start=start,end=end,reason=reason,actor=user,rules={'annualDays':kind.annual_days,'serviceMonths':kind.service_months,'weekdays':kind.weekdays})
        require(leave_days(start,end,kind.weekdays)>0,'Seçili aralıkta hesaplanacak izin günü yok.')
        validate_leave(employee,obj,branch)
    elif action in ['reviewLeave','withdrawLeave']:
        obj=get(m.LeaveRequest,p.get('id'),branch); require(obj.status=='pending','Yalnızca bekleyen talep değiştirilebilir.')
        if action=='withdrawLeave': scoped_employee(user,branch,str(obj.employee_id)); obj.status='withdrawn'
        else:
            require(p.get('status') in ['approved','rejected'],'Onay/red seçimi gerekli.')
            reason=p.get('reason','').strip(); require(reason and len(reason)<=1500,'Karar gerekçesi gerekli.')
            if p['status']=='approved': validate_leave(obj.employee,obj,branch)
            obj.status=p['status']; obj.reviewer=user; obj.reviewed_at=timezone.now(); obj.review_reason=reason
        obj.save()
    elif action=='saveAttendanceRules':
        values={key:integer(p.get(key,rules(branch)[key]),0,1440 if key!='missingExitHours' else 168) for key in DEFAULT_RULES if key!='paidBreaks'}
        require(values['missingExitHours']>=1 and 1<=values['duplicateSeconds']<=120,'Eksik çıkış ve tekrar aralığı geçersiz.')
        require(type(p.get('paidBreaks',False))==bool,'Mola ücret kuralı geçersiz.')
        branch.attendance_rules={**values,'paidBreaks':p.get('paidBreaks',False)}; branch.save(); obj=branch
    elif action=='saveRolePolicy':
        require(p.get('role') in ['staff','trainer'],'Yönetici izinleri değiştirilemez.')
        values=p.get('permissions'); require(isinstance(values,dict) and set(values)<=set(DEFAULT_PERMISSIONS) and all(type(v)==bool for v in values.values()),'İzin listesi geçersiz.')
        obj=m.RolePolicy.objects.filter(branch_id=branch.id,role=p['role']).first() or m.RolePolicy(branch_id=branch.id,role=p['role'])
        obj.permissions={**DEFAULT_PERMISSIONS,**({'memberManagement':False,'cardManagement':False,'collections':False,'deviceRead':False} if p['role']=='trainer' else {}),**(obj.permissions or {}),**values}; obj.save()
        m.AuthSession.objects.filter(user_id__in=[row.id for row in m.User.objects.filter(branch_id=branch.id,role=p['role'])],revoked=False).update(revoked=True)
    else: raise RuleError('Personel işlemi tanınmıyor.')
    audit(action,obj,user,branch,p,before)
    return str(obj.id) if obj else None


def milliseconds(shift, first, last, now=None):
    now=now or timezone.now()
    begin=max(shift.entry,first); finish=min(shift.exit or now,last)
    total=max(0,(finish-begin).total_seconds()*1000)
    for pause in m.ShiftBreak.objects.filter(shift_id=shift.id,paid=False):
        total-=max(0,(min(pause.end or now,finish)-max(pause.start,begin)).total_seconds()*1000)
    return max(0,round(total))


def state(user):
    from app.services.projection import wire
    employee=own_employee(user)
    employees=m.Employee.objects.filter(branch_id=user.branch_id)
    if user.role!='admin': employees=employees.filter(user_id=user.id)
    ids=[row.id for row in employees]
    config=rules(user.branch); now=timezone.now()
    tables=[('plannedShifts',m.PlannedShift,'employee_id'),('shiftBreaks',m.ShiftBreak,None),('leaveRequests',m.LeaveRequest,'employee_id'),('employeeCards',m.EmployeeCard,'employee_id'),('attendanceEvents',m.AttendanceEvent,'employee_id'),('personnelVisits',m.PersonnelVisit,'employee_id')]
    result={'rules':config,'permissions':permissions(user),'ownEmployeeId':str(employee.id) if employee else None,'simulationEnabled':settings.allow_device_simulation}
    for key,model,field in tables:
        query=model.objects.filter(branch_id=user.branch_id)
        if user.role!='admin':
            if field: query=query.filter(**{field+'__in':ids})
            else: query=query.filter(shift_id__in=[row.id for row in m.Shift.objects.filter(employee_id__in=ids)])
        rows=list(query.order_by('-at')[:100]) if key=='attendanceEvents' else list(query)
        result[key]=[wire(row) for row in rows]
    result['leaveTypes']=[wire(row) for row in m.LeaveType.objects.filter(branch_id=user.branch_id)]
    result['rolePolicies']=[wire(row) for row in m.RolePolicy.objects.filter(branch_id=user.branch_id)] if user.role=='admin' else []
    result['accounts']=[{'id':row.id,'name':row.full_name,'email':row.email,'role':row.role,'active':row.is_active,'linked':m.Employee.objects.filter(user_id=row.id).exists()} for row in m.User.objects.filter(branch_id=user.branch_id)] if user.role=='admin' else []
    metrics=[]
    for row in m.Shift.objects.filter(employee_id__in=ids):
        plan=get_session().get(m.PlannedShift,row.planned_id) if row.planned_id else choose_plan(row.employee,row.entry)
        pauses=list(m.ShiftBreak.objects.filter(shift_id=row.id))
        late=max(0,int((row.entry-plan.start).total_seconds()/60)-config['lateGraceMinutes']) if plan else None
        elapsed=milliseconds(row,row.entry,row.exit or now,now)
        overtime=max(0,int(elapsed/60000)-int((plan.end-plan.start).total_seconds()/60)+plan.break_minutes-config['overtimeGraceMinutes']) if plan and row.exit else None
        metrics.append({'id':str(row.id),'workedMs':elapsed,'lateMinutes':late,'overtimeMinutes':overtime,'missingExit':not row.exit and (now-row.entry).total_seconds()>config['missingExitHours']*3600,'onBreak':any(not pause.end for pause in pauses),'plannedId':str(plan.id) if plan else None})
    result['shiftMetrics']=metrics
    result['scheduleStatus']=[]
    for plan in m.PlannedShift.objects.filter(employee_id__in=ids,cancelled=False):
        leave=next((row for row in m.LeaveRequest.objects.filter(employee_id=plan.employee_id,status='approved') if overlap(plan.start,plan.end,*leave_window(row))),None)
        matched=[row for row in m.Shift.objects.filter(employee_id=plan.employee_id,simulated=False) if row.planned_id==plan.id or not row.planned_id and choose_plan(row.employee,row.entry) and choose_plan(row.employee,row.entry).id==plan.id]
        value='off' if plan.kind=='off' else 'leave' if leave else 'attended' if matched else 'absent' if plan.end<now else 'late' if plan.start+timedelta(minutes=config['lateGraceMinutes'])<now else 'planned'
        result['scheduleStatus'].append({'id':str(plan.id),'status':value})
    return result
