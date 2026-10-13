import base64
import calendar
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pydantic import ValidationError as SchemaError
from app.schemas.member import MemberDetails, normalize_phone, normalize_email
from app.core.config import settings
ValidationError = ValueError
from app.db import transaction
from app.repositories.query import Sum, Q
from app.core import time as timezone
from app import models as m
from .projection import wire
from .diagnostics import log
from .membership import status, current_sub, entry_sub, member_frozen


class RuleError(Exception):
    pass


def require(condition, message):
    if not condition: raise RuleError(message)


def amount(value):
    try:
        number = Decimal(str(value or 0))
        require(number.is_finite() and number >= 0 and number <= Decimal('9999999999.99'), 'Tutar geçersiz.')
        require(number == number.quantize(Decimal('0.01')), 'Tutar en fazla iki ondalık hane içerebilir.')
        return int(number*100)
    except (InvalidOperation, ValueError, TypeError): raise RuleError('Tutar geçersiz.')


def integer(value, minimum=0, maximum=100000):
    try:
        number=int(value); require(str(number)==str(value) or isinstance(value,int), 'Tam sayı gerekiyor.')
        require(minimum <= number <= maximum, 'Sayı sınırların dışında.'); return number
    except (ValueError, TypeError): raise RuleError('Tam sayı gerekiyor.')


def parse_day(value):
    try: return date.fromisoformat(str(value))
    except (ValueError, TypeError): raise RuleError('Tarih geçersiz.')


def parse_time(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        return result if timezone.is_aware(result) else timezone.make_aware(result)
    except (ValueError, TypeError, AttributeError): raise RuleError('Tarih/saat geçersiz.')


def months(day, count):
    total=day.year*12+day.month-1+count; year, month=divmod(total,12); month+=1
    return date(year,month,min(day.day,calendar.monthrange(year,month)[1]))


def end_for(plan, start):
    if plan.kind=='sessions': return None
    if plan.duration_unit=='month': return months(start,plan.duration_value)-timedelta(days=1)
    if plan.duration_unit=='year': return months(start,plan.duration_value*12)-timedelta(days=1)
    return start+timedelta(days=plan.duration_value*(7 if plan.duration_unit=='week' else 1)-1)


def get(cls, key, branch):
    try: return cls.objects.get(pk=key,branch_id=branch.id)
    except (cls.DoesNotExist, ValueError, ValidationError): raise RuleError('Kayıt bulunamadı veya bu şubeye ait değil.')


def net_paid(invoice):
    payments=m.Payment.objects.filter(invoice=invoice)
    return (payments.aggregate(total=Sum('amount_cents'))['total'] or 0)-(m.Refund.objects.filter(payment__in=payments).aggregate(total=Sum('amount_cents'))['total'] or 0)


def debt(invoice):
    return 0 if invoice.status=='cancelled' else max(0,invoice.total_cents-net_paid(invoice))


def member_debt(member):
    return sum(debt(invoice) for invoice in m.Invoice.objects.filter(member=member))


def member_details(payload, branch, member=None):
    names={'birthDate':'birth_date','emergencyPhone':'emergency_phone'}
    existing={key:getattr(member,names.get(key,key)) for key in MemberDetails.model_fields} if member else {}
    try:
        details=MemberDetails.model_validate({**existing,**payload}).model_dump()
    except SchemaError as error:
        first=error.errors()[0]
        message=first.get('ctx',{}).get('error')
        raise RuleError(str(message) if message else 'Üye bilgileri geçersiz; alan biçimini ve uzunluğunu kontrol edin.') from None
    phone=normalize_phone(details['phone'])
    old_phone=None
    old_email=None
    if member:
        try: old_phone=normalize_phone(member.phone)
        except ValueError: pass
        try: old_email=normalize_email(member.email)
        except ValueError: old_email=member.email.strip().lower()
    # Legacy telephone formats are compared canonically without rewriting existing records.
    for other in m.Member.objects.filter(branch=branch):
        if member and other.pk==member.pk: continue
        try: other_phone=normalize_phone(other.phone)
        except ValueError: other_phone=other.normalized_phone
        if not member or phone!=old_phone:
            require(other_phone!=phone,'Bu telefonla kayıtlı üye var; mevcut üyeliği kullanın.')
        if details['email'] and (not member or details['email']!=old_email):
            try: other_email=normalize_email(other.email)
            except ValueError: other_email=other.email.strip().lower()
            require(other_email!=details['email'],'Bu e-posta ile kayıtlı üye var; mevcut üyeliği kullanın.')
    stored_phone=member.normalized_phone if member and phone==old_phone else phone
    return {names.get(key,key):value for key,value in details.items()} | {'normalized_phone':stored_phone}


def collect(branch, user, p):
    from .system_settings import permitted
    require(permitted(user,'collections'),'Tahsilat yetkiniz yok.')
    invoice=get(m.Invoice,p.get('invoiceId'),branch)
    count=amount(p.get('amount'))
    require(0<count<=debt(invoice),'Ödeme kalan borcu aşamaz ve sıfırdan büyük olmalı.')
    require(p.get('method') in ['cash','pos','bank','mixed'],'Ödeme yöntemi geçersiz.')
    branch.payment_counter+=1; branch.save(update_fields=['payment_counter'])
    from .finance import payment_date
    at=payment_date(p,invoice)
    return m.Payment.objects.create(branch=branch,invoice=invoice,amount_cents=count,method=p['method'],note=str(p.get('note',''))[:600],actor=user,at=at,recorded_at=timezone.now(),number=f'ODM-{branch.payment_counter:06d}')


def sell(branch, user, member, p):
    from .plans import available, campaign_price
    plan=get(m.Plan,p.get('planId'),branch); require(available(plan),'Paket satışa kapalı veya satış tarihi uygun değil.')
    if p.get('planRevision') not in [None,'']:
        require(integer(p['planRevision'],1)==plan.revision,'Paket fiyatı/koşulları değişti; güncel paketi tekrar seçin.')
    start=parse_day(p.get('start') or timezone.localdate().isoformat())
    require(1900<=start.year<=9988,'Üyelik başlangıcı desteklenen tarih aralığında değil.')
    end=end_for(plan,start)
    require(not p.get('end') or parse_day(p['end'])==end,'Bitiş tarihi paket süresine uymuyor.')
    discount=amount(p.get('discount',0)); price=amount(plan.price)
    effective,campaign_discount,campaign=campaign_price(plan)
    require(not campaign or discount==0,'Kampanya ile manuel indirim aynı satışta birleştirilemez.')
    discount+=campaign_discount; require(discount<=price,'İndirim fiyatı aşamaz.')
    rules=wire(plan); rules['appliedCampaign']=campaign
    sub=m.Subscription.objects.create(branch=branch,member=member,plan=plan,plan_name=plan.name,start=start,end=end,price_cents=price,remaining=plan.sessions,total_sessions=plan.sessions,rules=rules)
    branch.invoice_counter+=1; branch.save(update_fields=['invoice_counter'])
    invoice=m.Invoice.objects.create(branch=branch,member=member,subscription=sub,total_cents=price-discount,discount_cents=discount,number=f'SAT-{branch.invoice_counter:06d}')
    count=integer(p.get('installments',1),1,12); quotient, remainder=divmod(invoice.total_cents,count)
    for index in range(count): m.Installment.objects.create(branch=branch,invoice=invoice,due=months(start,index),amount_cents=quotient+(index<remainder))
    if amount(p.get('paid',0))>0: collect(branch,user,{'invoiceId':str(invoice.id),'amount':p['paid'],'method':p.get('method','cash')})
    return sub


def validate_photo(value):
    if not value: return ''
    require(isinstance(value,str) and len(value)<700000,'Fotoğraf boyutu çok büyük.')
    require(re.match(r'^data:image/(png|jpeg|webp);base64,',value),'Fotoğraf biçimi geçersiz.')
    try:
        data=base64.b64decode(value.split(',',1)[1],validate=True)
        require(len(data)<=500000,'Fotoğraf en fazla 500 KB olabilir.')
        require(data.startswith(b'\x89PNG') or data.startswith(b'\xff\xd8\xff') or (data.startswith(b'RIFF') and data[8:12]==b'WEBP'),'Fotoğraf içeriği geçersiz.')
    except (ValueError, TypeError): raise RuleError('Fotoğraf içeriği geçersiz.')
    return value


ADMIN = {'savePlan','freeze','resume','cancelSubscription','refund','saveProduct','stock','returnSale','saveClass','cancelClass','saveSettings','deviceMode','devicePurpose','correctVisit','addEmployee','employeeStatus','saveRates','correctShift','openCash','closeCash'}
ADMIN.add('queueDeviceDiagnostic')
ADMIN.update({'correctPayment','saveInstallments','cancelInvoice'})
ADMIN.add('classOutcome')
ADMIN.add('saveSupplier')
ADMIN.update({'adminManualEntryOverride','correctManualVisit'})
ADMIN.discard('returnSale')
STAFF_ONLY = {'authorize','confirmPassage','scanEmployee'}
CARD_ACTIONS = {'assignCard','cardStatus','releaseCard'}
KNOWN = ADMIN | STAFF_ONLY | CARD_ACTIONS | {'addMember','editMember','renew','collect','book','bookingStatus','notice','readNotice','sellProduct'}


def apply_action(action,p,user,branch, device=None):
    from .system_settings import open_for_entry
    from . import manual_operations
    if action in manual_operations.ACTIONS:
        require(device is None, 'Manuel işlem personel oturumu gerektirir.')
        return manual_operations.apply(action,p,user,branch)
    if user and device is None:
        from . import system_settings
        if action in system_settings.ACTIONS:return system_settings.apply(action,p,user,branch)
        access={'addMember':'memberManagement','editMember':'memberManagement','renew':'memberManagement','assignCard':'cardManagement','cardStatus':'cardManagement','releaseCard':'cardManagement','collect':'collections'}
        if action in access:require(system_settings.permitted(user,access[action]),'Bu işlem için rol yetkiniz yok.')
    from . import stock
    if action in stock.ACTIONS:
        return stock.apply(action,p,user,branch)
    from . import classes
    if action in classes.ACTIONS:
        return classes.apply(action,p,user,branch)
    if action=='savePlan':
        from .plans import save
        return save(p,user,branch)
    if action=='queueDeviceDiagnostic':
        require(user is not None and user.role=='admin','Admin yetkisi gerekli.')
        from .device_controls import queue
        return queue(p,user,branch)
    if action in ['correctPayment','saveInstallments','cancelInvoice']:
        from .finance import apply
        return apply(action,p,user,branch)
    from . import personnel
    if action=='employeeStatus': return personnel.apply('saveEmployee',p,user,branch,device)
    if action=='correctShift': return personnel.apply('correctAttendance',p,user,branch,device)
    if action in personnel.ACTIONS:
        return personnel.apply(action,p,user,branch,device)
    if action=='readNotice':
        from .notifications import read
        read(user,p.get('id'));return None
    require(not user or user.role!='trainer','Antrenör hesabının bu işlem için yetkisi yok.')
    now=timezone.now(); today=timezone.localdate(); obj=None; before=None; result=None
    require(action in KNOWN,'İşlem tanınmıyor.')
    if device is None:
        require(user.role=='admin' or action not in ADMIN,'Yönetici yetkisi gerekiyor.')
        require(user.role in ['admin','staff'] or action not in STAFF_ONLY,'Bu işlem yetkili operasyon hesabından yapılır.')
        require(action not in CARD_ACTIONS or user.role in ['admin','staff'],'Kart yönetimi yetkisi gerekli.')
    if action=='addMember':
        fields=member_details(p,branch)
        require(p.get('consent') is True,'Bilgilendirme kaydı gerekli.')
        uid=p.get('uid','')
        require(isinstance(uid,str),'Kart UID geçersiz.')
        uid=uid.strip().upper()
        require(not uid or re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,99}',uid),'Kart UID geçersiz.')
        if not p.get('planId'):
            require(amount(p.get('paid',0))==0 and amount(p.get('discount',0))==0,'Paket olmadan ödeme veya indirim kaydedilemez.')
        branch.member_counter+=1; branch.save(update_fields=['member_counter'])
        obj=m.Member.objects.create(branch=branch,number=f'GYM-{branch.member_counter:06d}',created_by=user,consent=True,marketing=bool(p.get('marketing')),photo=validate_photo(p.get('photo')),**fields)
        if p.get('planId'): sell(branch,user,obj,p)
        if uid: apply_action('assignCard',{'memberId':str(obj.id),'uid':uid},user,branch)
        result=str(obj.id)
    elif action=='editMember':
        obj=get(m.Member,p.get('id'),branch); before=wire(obj)
        allowed=['active','marketing']+(['blocked'] if user.role=='admin' else [])
        if any(key in p for key in MemberDetails.model_fields):
            fields=member_details(p,branch,obj)
            for field,value in fields.items(): setattr(obj,field,value)
        for field in allowed:
            if field in p: setattr(obj,field,p[field])
        if 'photo' in p: obj.photo=validate_photo(p['photo'])
        obj.save()
    elif action=='renew':
        member=get(m.Member,p.get('memberId'),branch); obj=sell(branch,user,member,p); result=str(obj.id)
    elif action in ['freeze','resume','cancelSubscription']:
        obj=get(m.Subscription,p.get('id'),branch); before=wire(obj)
        if action=='freeze':
            first=parse_day(p.get('start')); last=parse_day(p.get('end'))
            days=(last-first).days+1
            require(obj.status=='active' and (obj.end is None or obj.end>=today) and max(today,obj.start)<=first and (obj.end is None or first<=obj.end) and last>=first,'Dondurma tarihleri veya üyelik uygun değil.')
            require(not any(row.end is None or row.end>max(today,row.start) for row in m.Freeze.objects.filter(subscription=obj)),'Bekleyen veya devam eden dondurma var.')
            require(0<days<=obj.rules.get('freezeDays',0)-obj.frozen_days,'Paketin dondurma hakkı yetersiz.')
            require(days>=obj.rules.get('freezeMin',1) and days<=(obj.rules.get('freezeMax') or obj.rules.get('freezeDays',0)),'Dondurma süresi paket alt/üst sınırına uymuyor.')
            require(not obj.rules.get('freezeLimit') or m.Freeze.objects.filter(subscription=obj).count()<obj.rules['freezeLimit'],'Dondurma sayısı limiti doldu.')
            require(isinstance(p.get('reason'),str) and 0<len(p['reason'].strip())<=1500,'Dondurma gerekçesi gerekli (en fazla 1500 karakter).')
            if obj.end is not None: obj.end+=timedelta(days=days)
            obj.frozen_days+=days
            m.Freeze.objects.create(branch=branch,subscription=obj,start=first,end=last+timedelta(days=1),planned_end=last,reason=p['reason'].strip(),actor=user)
        elif action=='resume':
            require(obj.status!='cancelled','Üyelik iptal edilmiş.')
            freeze=next((row for row in m.Freeze.objects.filter(subscription=obj).order_by('-start','-pk') if row.end is None or row.end>max(today,row.start)),None)
            require(freeze,'Devam eden veya planlanmış dondurma yok.')
            if freeze.planned_end:
                used=max(0,(today-freeze.start).days)
                reserved=(freeze.end-freeze.start).days
                unused=reserved-used
                if obj.end is not None: obj.end-=timedelta(days=unused)
                obj.frozen_days-=unused
                freeze.end=max(today,freeze.start)
            else:
                days=min(max(0,(today-freeze.start).days),obj.rules.get('freezeDays',0)-obj.frozen_days)
                if obj.end is not None: obj.end+=timedelta(days=days)
                obj.frozen_days+=days; freeze.end=today
            freeze.save(); obj.frozen_at=None; obj.status='active'
        else:
            require(obj.status!='cancelled','Üyelik zaten iptal edilmiş.')
            require(p.get('confirmed') is True and isinstance(p.get('reason'),str) and 0<len(p['reason'].strip())<=1500,'İptal onayı ve gerekçesi gerekli.')
            obj.status='cancelled'
        obj.save()
    elif action=='collect': obj=collect(branch,user,p)
    elif action=='refund':
        payment=get(m.Payment,p.get('paymentId'),branch); previous=m.Refund.objects.filter(payment=payment).aggregate(total=Sum('amount_cents'))['total'] or 0
        count=amount(p.get('amount')); require(0<count<=payment.amount_cents-previous and p.get('reason','').strip(),'İade tutarı veya gerekçe geçersiz.')
        obj=m.Refund.objects.create(branch=branch,payment=payment,amount_cents=count,reason=p['reason'],actor=user)
    elif action=='assignCard':
        member=get(m.Member,p.get('memberId'),branch); card=p.get('uid','').strip().upper()
        existing=m.Card.objects.filter(uid=card).first()
        require(card and len(card)<=100 and (not existing or existing.branch_id==branch.id and existing.status=='available' and existing.member_id is None) and not m.Employee.objects.filter(card=card).exists() and not m.EmployeeCard.objects.filter(uid=card).exists(),'Kart başka bir kişiye atanmış veya kullanıma kapalı. Yeniden kullanmak için önce teslim alın.')
        if p.get('captureId'):
            capture=get(m.CardCapture,p['captureId'],branch)
            require(capture.actor_id==user.id and capture.member_id==member.id and capture.uid==card and not capture.cancelled and not capture.consumed_at and capture.captured_at and now-capture.captured_at<timedelta(minutes=5),'Kart okutma kaydı bu üyeye ait değil veya süresi dolmuş.')
            capture.consumed_at=now; capture.save(update_fields=['consumed_at'])
            log(capture.device,'card_assigned',f'{card} kartı {member.name} üyesine atandı.',actor=user)
        m.Card.objects.filter(member=member,status__in=['active','inactive']).update(status='cancelled')
        if existing:
            obj=existing; before=wire(obj)
            obj.member=member; obj.member_id=member.id; obj.status='active'; obj.at=now; obj.save()
        else: obj=m.Card.objects.create(branch=branch,member=member,uid=card)
    elif action=='releaseCard':
        require(user is not None and user.role in ['admin','staff'],'Kart yönetimi yetkisi gerekli.')
        obj=get(m.Card,p.get('id'),branch); before=wire(obj)
        require(p.get('confirmed') is True,'Kartın fiziksel olarak teslim alındığını onaylayın.')
        require(obj.member_id is not None and obj.status in ['active','inactive','lost','cancelled'],'Kart zaten boş veya teslim alınamaz.')
        require(not m.Visit.objects.filter(member_id=obj.member_id,exit__isnull=True).exists(),'Üyenin açık ziyareti var. Kartı teslim almadan önce çıkışı tamamlayın.')
        require(not m.Grant.objects.filter(member_id=obj.member_id,confirmed=False,expires_at__gt=now).exists(),'Bekleyen geçiş izni var. Geçişin tamamlanmasını veya izin süresinin dolmasını bekleyin.')
        m.CardCapture.objects.filter(member_id=obj.member_id,cancelled=False,consumed_at__isnull=True).update(cancelled=True)
        obj.member=None; obj.member_id=None; obj.status='available'; obj.at=now; obj.save()
    elif action=='cardStatus':
        obj=get(m.Card,p.get('id'),branch); before=wire(obj); require(obj.status in ['active','inactive'] and p.get('status') in ['active','inactive','lost','cancelled'],'Kart iptal edilmiş veya durum geçersiz.')
        require(p['status']!='active' or not m.Card.objects.filter(member=obj.member,status='active').exclude(pk=obj.pk).exists(),'Üyenin aktif kartı var.'); obj.status=p['status']; obj.save()
    elif action=='authorize':
        from . import passage_validation
        from .plans import entry_error
        device=device or get(m.Device,p.get('deviceId'),branch)
        validation_mode=passage_validation.authorization_mode(device,p)
        from . import physical_personnel
        credential=str(p.get('uid','')).strip().upper()
        employee_card=m.EmployeeCard.objects.filter(uid=credential,branch_id=branch.id).first()
        employee=employee_card.employee if employee_card else m.Employee.objects.filter(card=credential,branch=branch).first()
        member_card=m.Card.objects.filter(uid=credential,branch=branch).first()
        if device.purpose in ['mixed','attendance']:
            require(not (employee and member_card and member_card.member_id and device.credential_context=='auto'),'Kart hem üye hem personel kaydına bağlı; admin cihaz kart bağlamını seçmeli.')
            if device.purpose=='attendance' or employee and device.credential_context!='member':
                if validation_mode==passage_validation.PROTOTYPE and employee:
                    visits=list(m.PersonnelVisit.objects.filter(employee=employee,exit__isnull=True))
                    require(passage_validation.consistent_visits(visits,employee,branch),'Personel ziyaret durumu tutarsız; yönetici kontrolü gerekli.')
                return passage_validation.annotate(physical_personnel.authorize(employee,not employee_card or employee_card.status=='active',credential,p.get('direction'),device,branch,now),validation_mode)
        require(device.purpose in ['access','mixed'],'Cihaz üye turnike amacıyla kullanılmıyor.')
        if user is not None:
            require(settings.ALLOW_DEVICE_SIMULATION and device.simulated,'Terminal simülasyonu kapalı.')
            device.last_seen=now
            device.save(update_fields=['last_seen'])
        card_uid=p.get('uid','').strip().upper(); require(card_uid and p.get('direction') in ['entry','exit','auto'],'Kart ve yön gerekli.')
        log(device,'rfid',f'RFID kart okundu: {card_uid}.')
        card=m.Card.objects.filter(uid=card_uid,branch=branch).select_related('member').first(); member=card.member if card else None
        sub=entry_sub(member,now) if member else None; inside=m.Visit.objects.filter(member=member,exit__isnull=True).exists() if member else False
        if validation_mode==passage_validation.PROTOTYPE and member:
            visits=list(m.Visit.objects.filter(member=member,exit__isnull=True))
            require(passage_validation.consistent_visits(visits,member,branch),'Üye ziyaret durumu tutarsız; yönetici kontrolü gerekli.')
        rule_reason=entry_error(sub,now) if sub else ''
        p=dict(p)
        if p['direction']=='auto': p['direction']='exit' if inside else 'entry'
        reason=''; clock=timezone.localtime(now); weekday=(clock.weekday()+1)%7
        if m.CardCapture.objects.filter(device=device,cancelled=False,consumed_at__isnull=True,expires_at__gt=now).exists(): reason='Okuyucu kart tanımlama modunda'
        elif m.DeviceCommand.objects.filter(device=device,status__in=['queued','sent'],expires_at__gt=now).exists(): reason='Donanım testi devam ediyor'
        elif m.Grant.objects.filter(device=device,confirmed=False,expires_at__gt=now).exists(): reason='Turnikede bekleyen işlem var'
        elif not device.enabled or not device.last_seen or device.last_seen<now-timedelta(seconds=60) or device.mode!='auto': reason='Cihaz çevrimdışı veya bakımda'
        elif not device.simulated and device.sensor!='ready': reason='Geçiş sensörleri hazır değil'
        elif device.direction not in ['both',p['direction']]: reason='Cihaz bu yön için yetkili değil'
        elif not card: reason='Kart tanımsız'
        elif card.status=='available': reason='Kart teslim alınmış; henüz bir üyeye atanmadı'
        elif card.status!='active': reason='Kart pasif, kayıp veya iptal edilmiş'
        elif m.Attempt.objects.filter(branch=branch,card=card_uid,at__gt=now-timedelta(seconds=10)).exists() or m.Grant.objects.filter(member=member,confirmed=False,expires_at__gt=now).exists() or manual_operations.recent_human_visit(member,now): reason='Tekrar okutma / bekleyen geçiş'
        elif p['direction']=='exit':
            if not inside: reason='Açık giriş kaydı yok'
        elif not member.active or member.blocked: reason='Üye pasif veya engelli'
        elif member_frozen(member,today): reason='Üyelik dondurulmuş'
        elif not sub: reason='Üyelik geçerli değil'
        elif inside: reason='Üye zaten içeride'
        elif sub.remaining is not None and sub.remaining<=0: reason='Seans hakkı kalmadı'
        elif rule_reason: reason=rule_reason
        elif not open_for_entry(branch,now): reason='Salon çalışma takvimi dışında'
        elif branch.debt_block and member_debt(member)>0: reason='Borç nedeniyle giriş engeli'
        elif m.Visit.objects.filter(branch=branch,exit__isnull=True).count()+m.Grant.objects.filter(branch=branch,direction='entry',confirmed=False,expires_at__gt=now).count()>=branch.capacity: reason='Kapasite dolu'
        attempt=m.Attempt.objects.create(branch=branch,member=member,card=card_uid,device=device,direction=p['direction'],status='rejected' if reason else 'granted',reason=reason or 'Sensör bekleniyor')
        log(device,'access_rejected' if reason else 'access_granted',f'{card_uid}: '+(reason or ('Giriş' if p['direction']=='entry' else 'Çıkış')+' izni verildi; fiziksel geçiş bekleniyor.'),'warning' if reason else 'info')
        result={'approved':not bool(reason),'subjectType':'member','memberId':str(member.id) if member else None,'memberName':member.name if member else '', 'reason':reason,'direction':p['direction'],'serverTime':now.isoformat()}; obj=attempt
        if not reason:
            grant=m.Grant.objects.create(branch=branch,attempt=attempt,member=member,subscription=sub,device=device,direction=p['direction'],expires_at=now+timedelta(seconds=30)); result['grantId']=str(grant.id); result['expiresAt']=grant.expires_at.isoformat()
        result=passage_validation.annotate(result,validation_mode)
    elif action=='confirmPassage':
        from . import passage_validation
        grant=get(m.Grant,p.get('id'),branch)
        if device is None:
            require(settings.ALLOW_DEVICE_SIMULATION and grant.device.simulated,'Sensör simülasyonu kapalı.'); device=grant.device
        require(grant.device_id==device.id,'İzin başka cihaza ait.'); require(not grant.confirmed,'İzin kullanılmış.')
        event_key=uuid.UUID(p.get('eventId') or str(uuid.uuid4())); occurred=parse_time(p['occurredAt']) if p.get('occurredAt') else now
        require(occurred<=now+timedelta(seconds=5) and grant.expires_at-timedelta(seconds=30)<=occurred<=grant.expires_at,'Olay zamanı geçersiz.')
        require(now-occurred<=timedelta(minutes=5),'Geçiş olayı çok geç ulaştı; yönetici kontrolü gerekiyor.')
        require(p.get('direction',grant.direction)==grant.direction,'Sensör yönü izinle uyuşmuyor.')
        validation_mode=passage_validation.confirmation(grant,device,p)
        event=m.Passage.objects.create(branch=branch,grant=grant,device=device,event_key=event_key,occurred_at=occurred)
        if grant.employee_id:
            from . import physical_personnel
            result=physical_personnel.confirm(grant,event,branch)
            result.update(validationMode=validation_mode,physicalVerified=validation_mode!=passage_validation.PROTOTYPE)
            grant.confirmed=True; grant.save(); grant.attempt.status='confirmed'; grant.attempt.reason=('Tek sensör prototipi: ' if validation_mode==passage_validation.PROTOTYPE else '')+result['message']; grant.attempt.save()
            log(device,'passage_recorded',grant.employee.name+': '+result['message'])
            return result
        visit=m.Visit.objects.filter(member=grant.member,exit__isnull=True).first()
        if grant.direction=='exit': require(visit,'Açık ziyaret yok.'); require(visit.entry<=occurred,'Çıkış zamanı girişten önce olamaz.'); visit.exit=occurred; visit.exit_event=event; visit.exit_method='Tek sensor prototipi' if validation_mode==passage_validation.PROTOTYPE else 'RFID'; visit.save()
        else:
            require(not visit,'Üye zaten içeride.'); m.Visit.objects.create(branch=branch,member=grant.member,subscription=grant.subscription,device=device,entry=occurred,entry_event=event,method='Tek sensor prototipi' if validation_mode==passage_validation.PROTOTYPE else 'RFID')
            require(grant.subscription and status(grant.subscription,timezone.localdate(occurred))=='active' and not member_frozen(grant.member,timezone.localdate(occurred)), 'Üyelik geçişten önce sona ermiş veya dondurulmuş.')
            from .plans import entry_error
            rule_reason=entry_error(grant.subscription,occurred)
            require(not rule_reason,rule_reason)
            if grant.subscription.remaining is not None:
                require(grant.subscription.remaining>0,'Seans hakkı yok.')
                previous=grant.subscription.remaining
                grant.subscription.remaining-=1; grant.subscription.save()
                m.Audit.objects.create(branch=branch,actor=user,type='sessionUsed',entity_id=str(grant.subscription.id),detail={'deviceId':str(device.id),'grantId':str(grant.id)},before={'remaining':previous},after={'remaining':grant.subscription.remaining})
        grant.confirmed=True; grant.save(); grant.attempt.status='confirmed'; grant.attempt.reason='Tek sensör prototip olayı kaydedildi; tam fiziksel geçiş kanıtı değil' if validation_mode==passage_validation.PROTOTYPE else 'Fiziksel geçiş tamamlandı'; grant.attempt.save(); obj=grant.attempt
        if validation_mode==passage_validation.PROTOTYPE:
            result={'validationMode':validation_mode,'physicalVerified':False}
        log(device,'passage_recorded',f'{grant.member.name}: '+('Giriş' if grant.direction=='entry' else 'Çıkış')+' PostgreSQL veritabanina kaydedildi.')
    elif action=='correctVisit':
        obj=get(m.Visit,p.get('id'),branch); before=wire(obj); require(not obj.exit and p.get('reason','').strip(),'Açık ziyaret ve gerekçe gerekli.')
        manual_operations.pending(obj.member,now)
        require(obj.entry<=now,'Ziyaret zamanı tutarsız.')
        obj.exit=now; obj.correction_reason=p['reason']; obj.exit_method='ADMIN_CORRECTION'; obj.exit_actor=user; obj.exit_reason=p['reason']; obj.save()
    elif action=='addEmployee':
        card=p.get('card','').strip().upper(); require(p.get('name','').strip() and card and not m.Card.objects.filter(uid=card).exists() and not m.Employee.objects.filter(card=card).exists(),'Çalışan adı veya kart geçersiz.')
        require(p.get('type') in ['fixed','hourly'] and p.get('role','staff') in ['staff','trainer'],'Personel tipi veya rol geçersiz.')
        rate=amount(p.get('hourlyRate',0)); obj=m.Employee.objects.create(branch=branch,name=p['name'].strip(),card=card,type=p['type'],role=p.get('role','staff'),hourly_rate=Decimal(rate)/100,phone=p.get('phone',''))
        if obj.type=='hourly': m.Rate.objects.create(branch=branch,employee=obj,effective_at=now,rate=obj.hourly_rate)
    elif action=='employeeStatus':
        obj=get(m.Employee,p.get('id'),branch); before=wire(obj); require(p.get('role',obj.role) in ['staff','trainer'],'Rol geçersiz.'); obj.role=p.get('role',obj.role); obj.active=bool(p.get('active',obj.active)); obj.save()
    elif action=='scanEmployee':
        employee=m.Employee.objects.filter(branch=branch,card=p.get('uid','').strip().upper()).first(); require(employee,'Çalışan kartı bulunamadı.')
        last=m.Shift.objects.filter(employee=employee).order_by('-entry').first(); require(not last or now-(last.exit or last.entry)>=timedelta(seconds=10),'Tekrar okutma; 10 saniye bekleyin.')
        obj=m.Shift.objects.filter(employee=employee,exit__isnull=True).first()
        if obj: obj.exit=now; obj.save(); result=f'{employee.name}: Mesai çıkışı kaydedildi.'
        else: require(employee.active,'Personel pasif.'); obj=m.Shift.objects.create(branch=branch,employee=employee,entry=now); result=f'{employee.name}: Mesai girişi kaydedildi.'
    elif action=='correctShift':
        obj=get(m.Shift,p.get('id'),branch); before=wire(obj); exit_time=parse_time(p.get('exit')); require(obj.entry<exit_time<=now and p.get('reason','').strip(),'Çıkış zamanı veya gerekçe geçersiz.')
        require(not m.Shift.objects.filter(employee=obj.employee,entry__lt=exit_time).filter(Q(exit__gt=obj.entry)|Q(exit__isnull=True)).exclude(pk=obj.pk).exists(),'Başka mesaiyle çakışıyor.'); obj.exit=exit_time; obj.reason=p['reason']; obj.save()
    elif action=='saveRates':
        require(p.get('confirmed') is True,'Fiyat ve ücret değişiklikleri onaylanmalı.')
        for plan in p.get('plans',[]):
            obj=get(m.Plan,plan['id'],branch)
            if amount(plan['price'])!=amount(obj.price):
                from .plans import save
                save({**wire(obj),'price':plan['price'],'revision':plan.get('revision'),'confirmed':p.get('confirmed')},user,branch)
        for key, rate in p.get('rates',{}).items():
            obj=get(m.Employee,key,branch); value=Decimal(amount(rate))/100
            if obj.type=='hourly' and obj.hourly_rate!=value: obj.hourly_rate=value; obj.save(); m.Rate.objects.create(branch=branch,employee=obj,rate=value,effective_at=now)
    elif action=='saveSettings':
        branch.capacity=integer(p.get('capacity'),1,100000); branch.debt_block=bool(p.get('debtBlock')); branch.save()
    elif action=='devicePurpose':
        require(user and user.role=='admin','Yönetici yetkisi gerekiyor.')
        obj=get(m.Device,p.get('id'),branch); before=wire(obj)
        require(p.get('purpose') in ['access','attendance','mixed'],'Cihaz kullanım amacı geçersiz.')
        require(not m.Grant.objects.filter(device=obj,confirmed=False,expires_at__gt=now).exists(),'Bekleyen geçiş varken cihaz amacı değiştirilemez.')
        require(not m.CardCapture.objects.filter(device=obj,cancelled=False,consumed_at__isnull=True,expires_at__gt=now).exists(),'Kart tanımlama sırasında cihaz amacı değiştirilemez.')
        context=p.get('credentialContext',obj.credential_context); require(context in ['auto','member','employee'],'Kart bağlamı geçersiz.')
        obj.purpose=p['purpose']; obj.credential_context=context; obj.save()
    elif action=='deviceMode':
        obj=get(m.Device,p.get('id'),branch); before=wire(obj); require(p.get('mode') in ['auto','maintenance'],'Cihaz modu geçersiz.'); obj.mode=p['mode']; obj.save(); m.DeviceEvent.objects.create(branch=branch,device=obj,message=f'Mod: {obj.mode}',actor=user)
    elif action=='notice':
        from .notifications import compose
        obj=compose(user,p)
    elif action=='openCash':
        require(not m.CashSession.objects.filter(branch=branch,closed_at__isnull=True).exists(),'Kasa zaten açık.'); obj=m.CashSession.objects.create(branch=branch,opening_cents=amount(p.get('amount')),actor=user)
    elif action=='closeCash':
        obj=m.CashSession.objects.filter(branch=branch,closed_at__isnull=True).first(); require(obj,'Açık kasa yok.'); obj.counted_cents=amount(p.get('amount')); obj.expected_cents=cash_balance(branch,obj,now); obj.closed_at=now; obj.closed_by=user; obj.note=p.get('note',''); obj.save()
    if action!='readNotice':
        safe={key:value for key,value in p.items() if key not in ['password','photo','token','requestId']}
        after=wire(obj) if obj else None
        if after: after.pop('photo',None)
        if before: before.pop('photo',None)
        m.Audit.objects.create(branch=branch,actor=user,type=action,entity_id=str(obj.pk) if obj else '',detail=safe,before=before,after=after)
    return result


def cash_balance(branch,session,now):
    def total(qs,field): return qs.aggregate(total=Sum(field))['total'] or 0
    return session.opening_cents+total(m.Payment.objects.filter(branch=branch,method='cash',recorded_at__gte=session.opened_at,recorded_at__lte=now),'amount_cents')-total(m.Refund.objects.filter(branch=branch,payment__method='cash',at__gte=session.opened_at,at__lte=now),'amount_cents')+total(m.Sale.objects.filter(branch=branch,method='cash',at__gte=session.opened_at,at__lte=now),'total_cents')-total(m.StockMovement.objects.filter(branch=branch,method='cash',at__gte=session.opened_at,at__lte=now),'refund_cents')


@transaction.atomic
def execute(action,p,user,request_id,device=None):
    require(user is not None or device is not None,'Oturum gerekli.')
    branch=m.Branch.objects.select_for_update().get(pk=user.branch_id if user else device.branch_id)
    if device: device.refresh_from_db()
    try: key=uuid.UUID(str(request_id))
    except (ValueError,TypeError): raise RuleError('Benzersiz işlem anahtarı gerekli.')
    digest=hashlib.sha256(json.dumps({'action':action,'payload':p},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    receipt=m.OperationReceipt.objects.filter(request_id=key).first()
    if receipt:
        require(receipt.actor_id==(user.id if user else None) and receipt.device_id==(device.id if device else None) and receipt.payload_hash==digest,'İşlem anahtarı başka isteğe ait.')
        return receipt.response
    result=apply_action(action,p,user,branch,device)
    response={'ok':True,'result':result}
    m.OperationReceipt.objects.create(request_id=key,actor=user,device=device,payload_hash=digest,response=response)
    return response
