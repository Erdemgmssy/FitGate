"""Branch configuration and account administration reuse existing entities."""
from datetime import date,time,timedelta
from app import models as m
from app.core import time as tz
from app.core.config import settings
from app.core.security import hash_password,check_password
from app.schemas.member import normalize_phone,normalize_email
from app.db.session import get_session
from .business import require,integer,validate_photo,RuleError

ADMIN_ACTIONS={'saveBranchProfile','saveOpeningHours','saveNotificationPreferences','manageAccount','saveDeviceName'}
ACTIONS=ADMIN_ACTIONS|{'changePassword'}
KINDS={'membership','payment','stock','class','shift','device'}
DEFAULT_NOTIFICATIONS={'membershipDays':7,'enabled':{key:True for key in KINDS},'roles':{'membership':['admin','staff'],'payment':['admin'],'stock':['admin'],'class':['admin','staff','trainer'],'shift':['admin','staff','trainer'],'device':['admin']}}

def notifications(branch):
    value=branch.configuration.get('notifications',{})
    return {**DEFAULT_NOTIFICATIONS,**value,'enabled':{**DEFAULT_NOTIFICATIONS['enabled'],**value.get('enabled',{})},'roles':{**DEFAULT_NOTIFICATIONS['roles'],**value.get('roles',{})}}

def profile(branch):
    return {'name':branch.name,'phone':'','email':'','address':'','logo':'',**branch.configuration.get('profile',{})}

def opening(branch):
    return {'enforced':False,'from':'06:00','to':'23:00','days':[0,1,2,3,4,5,6],'closures':[],**branch.configuration.get('opening',{})}

def open_for_entry(branch,at):
    rule=opening(branch)
    if not rule['enforced']:return True
    clock=tz.localtime(at);start=time.fromisoformat(rule['from']);end=time.fromisoformat(rule['to'])
    day=clock.date();instant=clock.time().replace(tzinfo=None)
    # After midnight, an overnight window belongs to the previous working day.
    service_day=day-timedelta(days=1) if start>end and instant<end else day
    if day.isoformat() in rule['closures'] or service_day.isoformat() in rule['closures']:return False
    weekday=(service_day.weekday()+1)%7
    return weekday in rule['days'] and (start<=instant<end if start<end else instant>=start or instant<end)

def permitted(user,key):
    from .personnel import permissions
    return user.role=='admin' or bool(permissions(user).get(key,False))

def protect_admin(account,active,role):
    if account.role=='admin' and account.is_active and (not active or role!='admin'):
        require(m.User.objects.filter(branch_id=account.branch_id,role='admin',is_active=True).exclude(pk=account.id).exists(),'Son aktif yönetici pasifleştirilemez veya rolü düşürülemez.')

def revoke(account):m.AuthSession.objects.filter(user_id=account.id,revoked=False).update(revoked=True)

def password(value):
    require(isinstance(value,str) and 12<=len(value)<=128 and any(c.isalpha() for c in value) and any(c.isdigit() for c in value),'Parola 12-128 karakter, harf ve sayı içermeli.')
    return value

def apply(action,p,user,branch):
    require(action not in ADMIN_ACTIONS or user.role=='admin','Yönetici yetkisi gerekli.')
    before=None;entity=str(branch.id)
    if action in ADMIN_ACTIONS:
        require(p.get('confirmed') is True,'Bu değişikliği onaylamalısınız.')
    if action=='saveBranchProfile':
        name=p.get('name','');require(isinstance(name,str) and 1<=len(name.strip())<=120,'Salon adı gerekli.')
        address=p.get('address','');require(isinstance(address,str) and len(address)<=600,'Adres çok uzun.')
        try:phone=normalize_phone(p['phone']) if p.get('phone') else '';email=normalize_email(p['email']) if p.get('email') else ''
        except (ValueError,AttributeError,TypeError) as error:raise RuleError('Telefon veya e-posta geçersiz.') from None
        value={'name':name.strip(),'phone':phone,'email':email,'address':address.strip(),'logo':validate_photo(p.get('logo')) or ''}
        before={**profile(branch),'logo':'[gizli]'};branch.name=value['name'];branch.configuration={**branch.configuration,'profile':value};branch.save()
    elif action=='saveOpeningHours':
        require(type(p.get('enforced')) is bool,'Çalışma takvimi seçimi geçersiz.')
        try:first=time.fromisoformat(p['from']);last=time.fromisoformat(p['to'])
        except (ValueError,TypeError,KeyError):raise RuleError('Açılış ve kapanış saatleri geçersiz.') from None
        require(first!=last and first.tzinfo is None and last.tzinfo is None,'Saatler farklı ve yerel olmalı.')
        days=p.get('days');require(isinstance(days,list) and len(set(days))==len(days) and all(type(d)==int and 0<=d<=6 for d in days) and (days or not p['enforced']),'Çalışma günlerini seçin.')
        closures=p.get('closures',[]);require(isinstance(closures,list) and len(closures)<=366,'Kapanış takvimi geçersiz.')
        try:closures=sorted({date.fromisoformat(d).isoformat() for d in closures})
        except (ValueError,TypeError):raise RuleError('Kapanış tarihleri geçersiz.') from None
        before=opening(branch);value={'enforced':p['enforced'],'from':first.isoformat(timespec='minutes'),'to':last.isoformat(timespec='minutes'),'days':days,'closures':closures};branch.configuration={**branch.configuration,'opening':value};branch.save()
    elif action=='saveNotificationPreferences':
        days=integer(p.get('membershipDays'),0,90);enabled=p.get('enabled');roles=p.get('roles')
        require(isinstance(enabled,dict) and set(enabled)==KINDS and all(type(v)==bool for v in enabled.values()),'Bildirim tercihleri geçersiz.')
        require(isinstance(roles,dict) and set(roles)==KINDS,'Bildirim rol listesi geçersiz.')
        for key,values in roles.items():require(isinstance(values,list) and len(set(values))==len(values) and set(values)<=set(DEFAULT_NOTIFICATIONS['roles'][key]),'Rolün mevcut erişim sınırı genişletilemez.')
        before=notifications(branch);value={'membershipDays':days,'enabled':enabled,'roles':roles};branch.configuration={**branch.configuration,'notifications':value};branch.save()
    elif action=='saveDeviceName':
        device=m.Device.objects.filter(pk=p.get('id'),branch_id=branch.id).first();require(device,'Cihaz bulunamadı.')
        name=p.get('name','');require(isinstance(name,str) and 1<=len(name.strip())<=120,'Cihaz adı gerekli.')
        before={'name':device.name};entity=str(device.id);device.name=name.strip();device.save()
    elif action=='manageAccount':
        account=m.User.objects.filter(pk=integer(p.get('id'),1,2147483647),branch_id=branch.id).first();require(account,'Hesap bulunamadı.')
        operation=p.get('operation');require(operation in ['update','resetPassword'],'Hesap işlemi geçersiz.')
        reason=p.get('reason','');require(isinstance(reason,str) and 3<=len(reason.strip())<=600,'İşlem gerekçesi gerekli.')
        before={'active':account.is_active,'role':account.role};entity=str(account.id)
        if operation=='resetPassword':account.password=hash_password(password(p.get('password')))
        else:
            active=p.get('active');role=p.get('role');require(type(active)==bool and role in ['admin','staff','trainer'],'Hesap durumu veya rol geçersiz.')
            protect_admin(account,active,role)
            require(account.id!=user.id or active and role=='admin','Kendi yönetici hesabınızı kilitleyemezsiniz.')
            account.is_active=active;account.role=role
            employee=m.Employee.objects.filter(branch_id=branch.id,user_id=account.id).first()
            if employee:employee.role=role;employee.active=active;employee.save()
        account.save();revoke(account)
    elif action=='changePassword':
        require(check_password(p.get('currentPassword',''),user.password),'Mevcut parola hatalı.')
        value=password(p.get('password'));require(not check_password(value,user.password),'Yeni parola mevcut paroladan farklı olmalı.')
        user.password=hash_password(value);user.save();revoke(user);entity=str(user.id)
    m.Audit.objects.create(branch=branch,actor=user,type=action,entity_id=entity,before=before,detail={k:v for k,v in p.items() if k not in ['password','currentPassword','logo']})
    return entity

def state(user):
    require(user.role=='admin','Yönetici yetkisi gerekli.')
    from .backups import status
    return {'profile':profile(user.branch),'opening':opening(user.branch),'notifications':notifications(user.branch),'security':{'hash':'Argon2','accessMinutes':settings.access_minutes,'refreshHours':settings.refresh_hours,'environment':settings.environment,'secureCookies':settings.environment!='development','loginAccountLimit':5,'loginIpLimit':25,'lockMinutes':15},'data':status()}
