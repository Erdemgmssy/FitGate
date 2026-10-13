import hmac
import jwt
from datetime import timedelta
from fastapi import HTTPException
from starlette.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from app import models as m
from app.core import time as timezone
from app.core.config import settings
from app.core.security import check_password,hash_password,hasher,digest,random_token,access_token,decode_access
from app.db.session import get_session

def user_info(user):
    from app.services.personnel import permissions
    return {'id':user.id,'name':user.full_name,'role':user.role,'branchId':str(user.branch_id),'personnelPermissions':permissions(user)}

def csrf_value(request): return request.cookies.get('fitgate_csrf') or random_token()

def response(data,request,status=200):
    token=csrf_value(request)
    result=JSONResponse({**data,'csrfToken':token},status_code=status)
    result.set_cookie('fitgate_csrf',token,secure=settings.environment!='development',samesite='lax',max_age=settings.refresh_hours*3600)
    return result

def verify_csrf(request):
    origin=request.headers.get('origin')
    if origin and origin not in settings.allowed_origins.split(','): raise HTTPException(403,'Origin not allowed')
    cookie=request.cookies.get('fitgate_csrf',''); header=request.headers.get('x-csrftoken','')
    if not cookie or not hmac.compare_digest(cookie.encode('utf-8'),header.encode('utf-8')): raise HTTPException(403,'CSRF doğrulaması gerekli.')

def current_user(request):
    header=request.headers.get('authorization','')
    token=header[7:] if header.startswith('Bearer ') else request.cookies.get('fitgate_access','')
    try:
        body=decode_access(token)
        session=m.AuthSession.objects.get(pk=body['sid'])
        user=session.user
        if body.get('type')!='access' or session.revoked or session.expires_at<=timezone.now() or str(user.id)!=body['sub'] or not user.is_active or not user.branch_id or user.role not in ['admin','staff','trainer']: raise ValueError()
        if user.role=='trainer' and not request.url.path.startswith(('/api/v1/auth/','/api/v1/state/','/api/v1/personnel/','/api/v1/actions/','/api/v1/reports/')):
            raise HTTPException(403,'Antrenör hesabı için bu ekran yetkisi yok.')
        return user
    except (ValueError,KeyError,jwt.PyJWTError,NoResultFound):
        raise HTTPException(401,'Oturum geçersiz veya süresi doldu.') from None

def cookies(result,user,session,refresh):
    secure=settings.environment!='development'
    result.set_cookie('fitgate_access',access_token(user,session),httponly=True,secure=secure,samesite='lax',max_age=settings.access_minutes*60)
    result.set_cookie('fitgate_refresh',refresh,httponly=True,secure=secure,samesite='lax',max_age=settings.refresh_hours*3600,path='/api/v1/auth/')
    return result

def login(request):
    email=request.data['email'].strip().lower(); password=request.data['password']; now=timezone.now()
    attempts=[]
    for scope in ['account:'+email,'ip:'+(request.client.host if request.client else 'unknown')]:
        item,_=m.LoginAttempt.objects.get_or_create(key=digest(scope))
        item=m.LoginAttempt.objects.select_for_update().get(pk=item.pk)
        if item.blocked_until and item.blocked_until>now: return response({'message':'Çok fazla giriş denemesi.'},request,429)
        if item.blocked_until and item.blocked_until<=now: item.failures=0; item.blocked_until=None
        attempts.append(item)
    user=m.User.objects.filter(email=email).first()
    valid=check_password(password,user.password) if user else False
    if not user:
        check_password(password,hasher.hash('timing-check-password'))
    if not valid or not user.is_active or not user.branch_id or user.role not in ['admin','staff','trainer']:
        for index,item in enumerate(attempts):
            item.failures+=1
            if item.failures >= (5 if index==0 else 25): item.blocked_until=now+timedelta(minutes=15)
            item.save()
        return response({'message':'E-posta veya şifre hatalı.'},request,401)
    if not user.password.startswith('$argon2') or hasher.check_needs_rehash(user.password): user.password=hash_password(password)
    user.last_login=now; user.save()
    for item in attempts: item.failures=0; item.blocked_until=None; item.save()
    refresh=random_token(); session=m.AuthSession.objects.create(user=user,refresh_hash=digest(refresh),expires_at=now+timedelta(hours=settings.refresh_hours))
    return cookies(response({'user':user_info(user)},request),user,session,refresh)

def renew(request):
    session=m.AuthSession.objects.select_for_update().filter(refresh_hash=digest(request.cookies.get('fitgate_refresh',''))).first()
    if not session or session.revoked or session.expires_at<=timezone.now() or not session.user.is_active or not session.user.branch_id or session.user.role not in ['admin','staff','trainer']: raise HTTPException(401,'Oturum yenilenemedi.')
    refresh=random_token(); session.refresh_hash=digest(refresh); session.save()
    return cookies(response({'user':user_info(session.user)},request),session.user,session,refresh)

def logout(request):
    session=m.AuthSession.objects.select_for_update().filter(refresh_hash=digest(request.cookies.get('fitgate_refresh',''))).first()
    if session: session.revoked=True; session.save()
    result=response({'ok':True},request)
    result.delete_cookie('fitgate_access'); result.delete_cookie('fitgate_refresh',path='/api/v1/auth/')
    return result
