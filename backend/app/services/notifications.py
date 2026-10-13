"""Existing Notice/ReadNotice storage with branch-scoped event deduplication."""
import uuid
from datetime import datetime,time,timedelta
from sqlalchemy import select
from app import models as m
from app.core import time as tz
from app.db.session import get_session
from .business import require,debt,net_paid
from .membership import current_sub,status

SEVERITIES={'info':2,'warning':1,'critical':0}
KINDS={'manual','membership','payment','stock','class','shift','device'}

def allowed(user,details):
    if user.role not in details.get('roles',['admin','staff']):return False
    if user.role=='admin':return True
    if user.role=='staff' and details.get('type')=='membership':
        from .system_settings import permitted
        if not permitted(user,'memberManagement'):return False
    employee=details.get('employeeId')
    if employee:
        return m.Employee.objects.filter(pk=employee,branch_id=user.branch_id,user_id=user.id).exists()
    if user.role=='trainer':
        return details.get('type')=='class' and bool(details.get('trainerId')) and m.Employee.objects.filter(pk=details['trainerId'],branch_id=user.branch_id,user_id=user.id).exists()
    return True

def sync(user):
    session=get_session();now=tz.now();today=tz.localdate(now);branch=user.branch_id
    from .system_settings import notifications
    preferences=notifications(user.branch)
    # Serialize notification lifecycle changes against existing branch transactions.
    session.execute(select(m.Branch.id).where(m.Branch.id==branch).with_for_update()).one()
    existing=list(session.scalars(select(m.Notice).where(m.Notice.branch_id==branch).execution_options(populate_existing=True)))
    active={row.details.get('source'):row for row in existing if row.details.get('automatic') and row.details.get('status')=='active'}
    seen=set()
    def event(source,message,kind,severity,target,target_id,at,roles=('admin','staff'),**extra):
        if not preferences['enabled'].get(kind,True):return
        roles=tuple(role for role in roles if role in preferences['roles'].get(kind,roles))
        details={'source':source,'automatic':True,'type':kind,'severity':severity,'target':target,'targetId':str(target_id),'roles':list(roles),'status':'active',**extra}
        if not allowed(user,details):return
        seen.add(source)
        obj=active.get(source)
        if not obj:
            details['eventAt']=at.isoformat()
            obj=m.Notice.objects.create(branch_id=branch,actor=user,event_key=f'auto:{uuid.uuid4()}',message=message,at=now,details=details)
            existing.append(obj);active[source]=obj
        else:
            details['eventAt']=obj.details.get('eventAt',at.isoformat())
            if obj.message!=message or obj.details!=details:obj.message=message;obj.details=details;obj.save()
    if user.role in ['admin','staff']:
        for member in m.Member.objects.filter(branch_id=branch,active=True):
            sub=current_sub(member,today)
            if sub and sub.end and 0<=(sub.end-today).days<=preferences['membershipDays']:
                event(f'membership:{sub.id}:{sub.end}',f'{member.name}: üyelik {sub.end:%d.%m.%Y} tarihinde bitiyor.','membership','warning','members',member.id,tz.make_aware(datetime.combine(max(sub.start,sub.end-timedelta(days=preferences['membershipDays'])),time.min)),memberId=str(member.id))
            elif not sub:
                expired=next((row for row in reversed(list(m.Subscription.objects.filter(member=member).order_by('end','created_at','pk'))) if status(row,today)=='expired'),None)
                has_other=m.Subscription.objects.filter(member=member,status='frozen').exists()
                if expired and not has_other and not any(status(row,today)=='frozen' for row in m.Subscription.objects.filter(member=member)):
                    event(f'expired:{expired.id}:{expired.end}',f'{member.name}: üyelik süresi dolmuş.','membership','warning','members',member.id,tz.make_aware(datetime.combine(expired.end+timedelta(days=1),time.min)),memberId=str(member.id))
    if user.role=='admin':
        for invoice in m.Invoice.objects.filter(branch_id=branch).select_related('member'):
            if invoice.status=='cancelled' or debt(invoice)<=0:continue
            paid=net_paid(invoice)
            for part in m.Installment.objects.filter(invoice=invoice,archived=False).order_by('due','pk'):
                used=min(part.amount_cents,max(0,paid));paid-=used
                if part.due<today and used<part.amount_cents:
                    event(f'payment:{invoice.id}:{part.id}',f'{invoice.member.name}: {invoice.number} satışında {part.due:%d.%m.%Y} vadeli taksit gecikmiş.','payment','warning','payments',invoice.id,tz.make_aware(datetime.combine(part.due+timedelta(days=1),time.min)),roles=('admin',),memberId=str(invoice.member_id),invoiceId=str(invoice.id));break
        for product in m.Product.objects.filter(branch_id=branch,active=True):
            if product.stock<=product.minimum:
                event(f'stock:{product.id}',f'{product.name}: '+('stok tükendi.' if product.stock==0 else f'kritik stok ({product.stock}).'),'stock','critical' if product.stock==0 else 'warning','stock',product.id,now,roles=('admin',))
        for device in m.Device.objects.filter(branch_id=branch,simulated=False,enabled=True,mode='auto'):
            online=bool(device.last_seen and now-device.last_seen<timedelta(seconds=60))
            if not online and (device.last_seen or device.telemetry.get('connection')=='retrying'):
                event(f'device:{device.id}:offline',f'{device.name}: bağlantı kesildi.','device','critical','devices',device.id,device.last_seen+timedelta(seconds=60) if device.last_seen else now,roles=('admin',),component='offline')
            if online:
                components={'sensor':device.sensor,'rfid':device.telemetry.get('rfid'),'servo':device.telemetry.get('servo')}
                for component,value in components.items():
                    if value=='fault':event(f'device:{device.id}:{component}',f'{device.name}: {component} arızası.','device','critical','devices',device.id,now,roles=('admin',),component=component)
    for cls in m.ClassSession.objects.filter(branch_id=branch,cancelled=False,at__gt=now,at__lte=now+timedelta(hours=24)):
        if cls.outcome=='notheld':continue
        event(f'class:{cls.id}:{cls.at.isoformat()}',f'{cls.name}: {tz.localtime(cls.at):%d.%m.%Y %H:%M} tarihinde başlayacak.','class','info','classes',cls.id,cls.at-timedelta(hours=24),roles=('admin','staff','trainer'),trainerId=str(cls.trainer_id) if cls.trainer_id else None)
    for shift in m.PlannedShift.objects.filter(branch_id=branch,cancelled=False,kind='work',start__gt=now,start__lte=now+timedelta(hours=24)).select_related('employee'):
        from .personnel import overlap,leave_window
        if any(overlap(shift.start,shift.end,*leave_window(row)) for row in m.LeaveRequest.objects.filter(employee_id=shift.employee_id,branch_id=branch,status='approved')):continue
        event(f'shift:{shift.id}:{shift.start.isoformat()}',f'{shift.employee.name}: vardiya {tz.localtime(shift.start):%d.%m.%Y %H:%M} başlıyor.','shift','info','employees',shift.employee_id,shift.start-timedelta(hours=24),roles=('admin','staff','trainer'),employeeId=str(shift.employee_id),shiftId=str(shift.id))
    for obj in existing:
        info=obj.details
        if info.get('automatic') and (not preferences['enabled'].get(info.get('type'),True) or user.role not in preferences['roles'].get(info.get('type'),['admin','staff'])):continue
        if not info.get('automatic') or info.get('status')!='active' or not allowed(user,info) or info['source'] in seen:continue
        state='resolved';reason='Bildirim koşulu artık geçerli değil.'
        if info.get('type')=='device':
            device=session.get(m.Device,uuid.UUID(info['targetId']))
            if not device or device.simulated or not device.enabled or device.mode!='auto':state='inactive';reason='Cihaz devre dışı, simülasyon veya bakım modunda.'
            else:
                online=device.last_seen and now-device.last_seen<timedelta(seconds=60)
                value=device.sensor if info['component']=='sensor' else device.telemetry.get(info['component'])
                healthy=online and (info['component']=='offline' or value in ['ready','open','closed'])
                if not healthy:continue
                reason='Güncel cihaz bildirimiyle düzeldiği doğrulandı.'
        obj.details={**info,'status':state,'resolvedAt':now.isoformat(),'resolution':reason};obj.save()
    reads=set(m.ReadNotice.objects.filter(user=user).values_list('notice_id',flat=True))
    result=[]
    for obj in existing:
        info=obj.details or {}
        if info.get('automatic') and (not preferences['enabled'].get(info.get('type'),True) or user.role not in preferences['roles'].get(info.get('type'),['admin','staff'])):continue
        if not allowed(user,info):continue
        result.append({'id':str(obj.id),'message':obj.message,'at':obj.at.isoformat(),'severity':info.get('severity','info'),'type':info.get('type','manual'),'status':info.get('status','active'),'resolvedAt':info.get('resolvedAt'),'resolution':info.get('resolution'),'target':info.get('target'),'targetId':info.get('targetId'),'memberId':info.get('memberId'),'read':str(obj.id) in reads})
    return sorted(result,key=lambda row:(row['status']!='active',SEVERITIES[row['severity']],-datetime.fromisoformat(row['at']).timestamp(),row['id']))

def read(user,key):
    try:key=uuid.UUID(str(key))
    except (ValueError,TypeError):require(False,'Bildirim kimliği geçersiz.')
    obj=m.Notice.objects.filter(pk=key,branch_id=user.branch_id).first()
    require(obj and allowed(user,obj.details),'Bildirim bulunamadı veya bu bildirim için yetkiniz yok.')
    m.ReadNotice.objects.get_or_create(user=user,notice_id=str(obj.id))

def compose(user,p):
    message=p.get('message','');severity=p.get('severity','info')
    require(isinstance(message,str) and 0<len(message.strip())<=1500,'Bildirim metni gerekli (en fazla 1500 karakter).')
    require(severity in SEVERITIES and (severity!='critical' or user.role=='admin'),'Bildirim önem derecesi için yetkiniz yok.')
    for row in m.Notice.objects.filter(branch_id=user.branch_id,actor=user,message=message.strip(),at__gte=tz.now()-timedelta(minutes=1)):
        if row.details.get('type','manual')=='manual' and row.details.get('severity','info')==severity:return row
    return m.Notice.objects.create(branch_id=user.branch_id,actor=user,message=message.strip(),details={'type':'manual','severity':severity,'status':'active','roles':['admin','staff']})
