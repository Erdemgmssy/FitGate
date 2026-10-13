"""Lesson reservations share branch transaction locks and the existing finance ledger."""
import uuid
from datetime import timedelta
from app import models as m
from app.core import time as timezone
from .business import require, get, integer, amount, parse_time, RuleError
from .membership import status, subscriptions, member_frozen
from .projection import wire

ACTIONS={'saveClass','book','bookingStatus','cancelClass','classOutcome','classReminders'}
SEATS={'booked','attended','late','absent'}
LIVE=SEATS|{'waiting'}

def end(cls): return cls.at+timedelta(minutes=cls.duration)

def state(cls,now=None):
    now=now or timezone.now()
    if cls.cancelled: return 'cancelled'
    if cls.outcome=='notheld': return 'notheld'
    if now>=end(cls): return 'completed'
    return 'ongoing' if now>=cls.at else 'planned'

def permissions(user):
    if user.role=='admin': return {'manage':True,'book':True,'attendance':True}
    policy=m.RolePolicy.objects.filter(branch_id=user.branch_id,role=user.role).first()
    values=policy.permissions if policy else {}
    return {'manage':False,'book':user.role=='staff' and values.get('classBooking',True),
            'attendance':user.role in ['trainer','staff'] and values.get('classAttendance',True)}

def audit(action,obj,user,branch,p,before=None):
    m.Audit.objects.create(branch=branch,actor=user,type=action,entity_id=str(obj.id),detail=p,before=before,after=wire(obj))

def notice(user,branch,message,key=None,class_id=None):
    if key and m.Notice.objects.filter(event_key=key).exists(): return
    cls=m.ClassSession.objects.filter(pk=class_id,branch=branch).first() if class_id else None
    details={'type':'class','severity':'info','status':'active','roles':['admin','staff','trainer'],'target':'classes','targetId':str(cls.id),'trainerId':str(cls.trainer_id) if cls.trainer_id else None} if cls else {}
    m.Notice.objects.create(branch=branch,actor=user,channel='panel',message=message[:1500],event_key=key,details=details)

def text(p,key,maximum,required=False):
    value=p.get(key,'')
    require(isinstance(value,str) and len(value.strip())<=maximum and (not required or value.strip()),f'{key}: geçerli metin gerekli.')
    return value.strip()

def overlaps(a,b,c,d): return a<d and c<b

def availability(branch,trainer,room,at,duration,exclude=()):
    finish=at+timedelta(minutes=duration)
    require(trainer.active and trainer.role=='trainer','Aktif antrenör seçilmeli.')
    for cls in m.ClassSession.objects.filter(branch=branch,cancelled=False):
        if str(cls.id) in exclude or cls.outcome=='notheld': continue
        if (cls.trainer_id==trainer.id or cls.trainer==trainer.name or cls.room.casefold()==room.casefold()) and overlaps(at,finish,cls.at,end(cls)):
            raise RuleError('Antrenör veya salon bu saatte dolu.')
    from .personnel import leave_window
    for row in m.LeaveRequest.objects.filter(employee_id=trainer.id,status='approved'):
        if overlaps(at,finish,*leave_window(row)): raise RuleError('Antrenör bu tarihte izinli.')
    shifts=list(m.PlannedShift.objects.filter(employee_id=trainer.id,cancelled=False))
    for row in shifts:
        if row.kind!='work' and overlaps(at,finish,row.start,row.end): raise RuleError('Antrenör bu aralıkta müsait değil.')
    # No fabricated shift schedule: only enforce work windows when one is defined that day.
    work=[row for row in shifts if row.kind=='work' and timezone.localdate(row.start)<=timezone.localdate(at)<=timezone.localdate(row.end)]
    require(not work or any(row.start<=at and finish<=row.end for row in work),'Ders antrenörün planlı çalışma saatleri dışında.')

def member_available(member,cls,ignore=None,at=None,duration=None):
    at=at or cls.at; finish=at+timedelta(minutes=duration or cls.duration)
    for row in m.Booking.objects.filter(member=member,status__in=list(SEATS)):
        if row.id==ignore or row.class_session_id==cls.id: continue
        other=row.class_session
        require(other.cancelled or other.outcome=='notheld' or not overlaps(at,finish,other.at,end(other)),'Üyenin aynı saatte başka rezervasyonu var.')

def lesson_usage(sub,ignore=None):
    return sum(row.id!=ignore for row in m.Booking.objects.filter(subscription=sub,right_state__in=['reserved','consumed']))

def eligible(member,cls,terms=None,ignore=None):
    rules=terms or contract(cls); day=timezone.localdate(cls.at)
    require(member.active and not member.blocked,'Üye aktif değil veya engelli.')
    if not rules['requireMembership'] and not rules['requireLesson']: return None
    require(not member_frozen(member,day),'Dondurulmuş üyelikle ders rezervasyonu yapılamaz.')
    candidates=[sub for sub in subscriptions(member) if status(sub,day)=='active' and cls.kind in sub.rules.get('lessonTypes',['group'])]
    if rules['requireLesson']:
        candidates=[sub for sub in candidates if sub.rules.get('lessonSessions') is None or lesson_usage(sub,ignore)<sub.rules['lessonSessions']]
    require(candidates,'Geçerli ders paketi veya yeterli ders hakkı yok.')
    return candidates[0]

def contract(cls):
    return {'className':cls.name,'kind':cls.kind,'priceCents':cls.price_cents,
            'requireMembership':cls.require_membership,'requireLesson':cls.require_lesson,
            'cancelMinutes':cls.cancel_minutes,'lateCancelConsumes':cls.late_cancel_consumes,'noShowConsumes':cls.no_show_consumes}

def reserve(row,cls):
    sub=eligible(row.member,cls,row.terms,row.id)
    row.subscription=sub
    row.right_state='reserved' if row.terms.get('requireLesson') else 'none'
    row.status='booked';row.updated_at=timezone.now();row.save()
    if row.terms['priceCents'] and not m.Invoice.objects.filter(booking_id=row.id).exists():
        branch=cls.branch;branch.invoice_counter+=1;branch.save()
        invoice=m.Invoice.objects.create(branch=branch,member=row.member,booking_id=row.id,description=f'Ders: {row.terms["className"]}',number=f'SAT-{branch.invoice_counter:06d}',total_cents=row.terms['priceCents'])
        m.Installment.objects.create(branch=branch,invoice=invoice,due=timezone.localdate(),amount_cents=invoice.total_cents)

def promote(cls,user,branch):
    if state(cls)!='planned' or timezone.now()>cls.at-timedelta(minutes=cls.booking_minutes): return
    for waiting in m.Booking.objects.filter(class_session=cls,status='waiting').order_by('at','pk'):
        if m.Booking.objects.filter(class_session=cls,status__in=list(SEATS)).count()>=cls.capacity: break
        try:
            member_available(waiting.member,cls,waiting.id)
            eligible(waiting.member,cls,waiting.terms,waiting.id)
        except RuleError: continue
        before=wire(waiting);reserve(waiting,cls)
        audit('waitlistPromotion',waiting,user,branch,{},before)
        notice(user,branch,f'{waiting.member.name}: {cls.name} bekleme listesinden onaylandı.',class_id=cls.id)

def own_class(user,cls):
    if user.role!='trainer': return
    require(cls.trainer_id is not None and m.Employee.objects.filter(pk=cls.trainer_id,user_id=user.id,active=True).exists(),'Yalnızca size atanmış derslerde yoklama yapabilirsiniz.')

def apply(action,p,user,branch):
    require(user is not None,'Personel oturumu gerekli.')
    rights=permissions(user);now=timezone.now()
    if action in ['saveClass','cancelClass','classOutcome']:
        require(rights['manage'],'Ders yönetimi için admin yetkisi gerekli.')
    elif action in ['book','classReminders']:
        require(rights['book'],'Rezervasyon yetkisi gerekli.')
    elif action=='bookingStatus':
        require(rights['attendance'] or rights['book'],'Rezervasyon/yoklama yetkisi gerekli.')
    if action=='saveClass':
        original=get(m.ClassSession,p['id'],branch) if p.get('id') else None
        require(not original or state(original)=='planned','Başlamış veya iptal edilmiş ders değiştirilemez.')
        at=parse_time(p.get('at'));duration=integer(p.get('duration'),1,1440);kind=p.get('kind','group')
        require(at>now and at.year<=9988 and kind in ['group','private'],'Gelecek tarih ve geçerli ders türü seçilmeli.')
        capacity=integer(p.get('capacity',1),1,10000);require(kind!='private' or capacity==1,'Özel ders kontenjanı bir kişi olmalı.')
        trainer=get(m.Employee,p.get('trainerId'),branch);room=text(p,'room',100,True);name=text(p,'name',120,True)
        fields={'name':name,'description':text(p,'description',600),'kind':kind,'trainer_id':trainer.id,'trainer':trainer.name,'room':room,'duration':duration,'capacity':capacity,
                'booking_minutes':integer(p.get('bookingMinutes',0),0,10080),'cancel_minutes':integer(p.get('cancelMinutes',120),0,10080),'price_cents':amount(p.get('price',0))}
        for key,attr,default in [('requireMembership','require_membership',True),('requireLesson','require_lesson',False),('lateCancelConsumes','late_cancel_consumes',True),('noShowConsumes','no_show_consumes',True)]:
            require(type(p.get(key,default)) is bool,'Ders kuralı geçersiz.');fields[attr]=p.get(key,default)
        require(not fields['require_lesson'] or fields['require_membership'],'Ders hakkı için üyelik kontrolü gerekli.')
        targets=[original] if original else [None]*integer(p.get('repeatCount',1),1,52)
        if original and p.get('scope')=='future':
            require(original.series_id is not None,'Tek ders seri olarak değiştirilemez.')
            targets=list(m.ClassSession.objects.filter(branch=branch,series_id=original.series_id,at__gte=original.at,cancelled=False).order_by('at'))
        require(not original or p.get('scope','single') in ['single','future'],'Düzenleme kapsamı geçersiz.')
        series=original.series_id if original else uuid.uuid4() if len(targets)>1 else None
        exclude={str(row.id) for row in targets if row}
        for index,target in enumerate(targets):
            new_at=at+(target.at-original.at if original else timedelta(weeks=index))
            require(not target or state(target)=='planned','Seride başlamış ders değiştirilemez.')
            availability(branch,trainer,room,new_at,duration,exclude)
            if target:
                require(m.Booking.objects.filter(class_session=target,status__in=list(SEATS)).count()<=capacity,'Kontenjan mevcut kayıtların altında olamaz.')
                live=list(m.Booking.objects.filter(class_session=target,status__in=list(LIVE)))
                if live:
                    require(kind==target.kind,'Rezervasyon varken ders türü değiştirilemez.')
                    for booking in live: member_available(booking.member,target,booking.id,new_at,duration)
                    # Snapshot terms remain unchanged; eligibility is checked at the new date.
                    previous=target.at;target.at=new_at
                    try:
                        for booking in live:
                            if booking.status!='waiting': eligible(booking.member,target,booking.terms,booking.id)
                    finally: target.at=previous
            before=wire(target) if target else None
            obj=target or m.ClassSession(branch=branch,series_id=series)
            for key,value in fields.items(): setattr(obj,key,value)
            obj.at=new_at;obj.save();audit(action,obj,user,branch,p,before)
            if target:
                notice(user,branch,f'{obj.name}: ders bilgileri güncellendi; yeni saat {timezone.localtime(new_at).strftime("%d.%m.%Y %H:%M")}.',class_id=obj.id)
        return {'id':str(obj.id),'count':len(targets)}
    if action=='book':
        cls=get(m.ClassSession,p.get('classId'),branch);member=get(m.Member,p.get('memberId'),branch)
        require(state(cls)=='planned' and now<=cls.at-timedelta(minutes=cls.booking_minutes),'Rezervasyon süresi dolmuş veya ders kapalı.')
        require(not m.Booking.objects.filter(class_session=cls,member=member,status__in=list(LIVE)).exists(),'Üye zaten kayıtlı.')
        member_available(member,cls);eligible(member,cls)
        full=m.Booking.objects.filter(class_session=cls,status__in=list(SEATS)).count()>=cls.capacity
        require(not full or cls.kind!='private','Özel ders kontenjanı dolu.')
        obj=m.Booking.objects.create(branch=branch,class_session=cls,member=member,status='waiting' if full else 'booked',terms=contract(cls),actor_id=user.id)
        if not full: reserve(obj,cls)
        audit(action,obj,user,branch,p);notice(user,branch,f'{member.name}: {cls.name} için '+('bekleme listesine eklendi.' if full else 'rezervasyon onaylandı.'),class_id=cls.id)
        return obj.status
    if action=='bookingStatus':
        obj=get(m.Booking,p.get('id'),branch);cls=obj.class_session;own_class(user,cls);before=wire(obj)
        desired=p.get('status');require(desired in ['booked','attended','late','absent','cancelled','excused'],'Katılım durumu geçersiz.')
        cancelling=desired=='cancelled' or desired=='excused' and state(cls)=='planned'
        require(rights['book'] if cancelling else rights['attendance'],'Bu işlem için yetkiniz yok.')
        require(state(cls) not in ['cancelled','notheld'],'İptal edilmiş derste yoklama değiştirilemez.')
        require(obj.status in LIVE or obj.status=='excused' and obj.terms.get('attendanceRecorded'),'İptal rezervasyon yeniden etkinleştirilemez; yeni rezervasyon oluşturun.')
        if cancelling: require(state(cls)=='planned','Başlamış ders iptal yerine gerekçeli yoklamayla düzeltilmeli.')
        else:
            require(obj.status!='waiting' and now>=cls.at,'Yoklama ders başladığında alınabilir.')
            require(desired!='absent' or now>=end(cls),'Gelmedi durumu ders bitiminde işlenebilir.')
            if obj.status=='booked' and desired in ['attended','late']:
                require(obj.member.active and not obj.member.blocked,'Üye aktif değil veya engelli.')
                if obj.subscription_id:
                    require(status(obj.subscription,timezone.localdate(cls.at))=='active','Rezervasyonun üyeliği ders tarihinde geçerli değil.')
        reason=text(p,'reason',1500,cancelling or obj.terms.get('attendanceRecorded',False) or obj.status in ['attended','late','absent'])
        consume=desired in ['attended','late'] or desired=='absent' and obj.terms.get('noShowConsumes',True) or desired=='cancelled' and now>cls.at-timedelta(minutes=obj.terms.get('cancelMinutes',cls.cancel_minutes)) and obj.terms.get('lateCancelConsumes',True)
        if (consume or desired=='booked') and obj.right_state=='released' and obj.subscription_id:
            total=obj.subscription.rules.get('lessonSessions')
            require(total is None or lesson_usage(obj.subscription,obj.id)<total,'Ders hakkı başka rezervasyonda kullanılmış; düzeltme yapılamaz.')
        if obj.right_state!='none': obj.right_state='reserved' if desired=='booked' else 'consumed' if consume else 'released'
        if not cancelling: obj.terms={**obj.terms,'attendanceRecorded':True}
        obj.status=desired;obj.reason=reason;obj.updated_at=now;obj.save();audit(action,obj,user,branch,p,before)
        if cancelling:
            notice(user,branch,f'{obj.member.name}: {cls.name} rezervasyonu iptal edildi.',class_id=cls.id)
            promote(cls,user,branch)
        return {'id':str(obj.id)}
    if action in ['cancelClass','classOutcome']:
        cls=get(m.ClassSession,p.get('id'),branch);before=wire(cls);reason=text(p,'reason',1500,True)
        require(state(cls) not in ['cancelled','notheld'],'Ders zaten kapalı.')
        if action=='cancelClass': require(state(cls)=='planned','Başlamış ders iptal edilemez; yapılmadı işlemini kullanın.');cls.cancelled=True
        else:
            require(now>=cls.at and not m.Booking.objects.filter(class_session=cls,status__in=['attended','late']).exists(),'Katılım kaydı olan veya başlamamış ders yapılmadı olarak işaretlenemez.')
            cls.outcome='notheld'
        cls.save()
        for booking in m.Booking.objects.filter(class_session=cls,status__in=list(LIVE)):
            old=wire(booking);booking.status='excused';booking.right_state='released' if booking.right_state!='none' else 'none';booking.reason=reason;booking.updated_at=now;booking.save()
            audit('classBookingCancelled',booking,user,branch,{'reason':reason},old)
        audit(action,cls,user,branch,p,before);notice(user,branch,f'{cls.name}: ders iptal edildi / yapılmadı. {reason}',class_id=cls.id)
        # Financial documents stay intact; refunds and sale cancellation use the existing admin finance workflow.
        return {'id':str(cls.id)}
    if action=='classReminders':
        count=0
        for cls in m.ClassSession.objects.filter(branch=branch,cancelled=False,at__gt=now,at__lte=now+timedelta(hours=24)):
            if cls.outcome=='notheld': continue
            for booking in m.Booking.objects.filter(class_session=cls,status='booked'):
                key=f'class-reminder:{booking.id}:{cls.at.isoformat()}'
                if not m.Notice.objects.filter(event_key=key).exists():
                    notice(user,branch,f'{booking.member.name}: {cls.name} yarın/bugün {timezone.localtime(cls.at).strftime("%d.%m %H:%M")}.',key,class_id=cls.id);count+=1
        if count: m.Audit.objects.create(branch=branch,actor=user,type=action,entity_id=str(branch.id),detail={'count':count,'channel':'panel'})
        return {'count':count}
