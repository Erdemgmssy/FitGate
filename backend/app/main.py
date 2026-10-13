from datetime import date
import json
from types import SimpleNamespace
from fastapi import FastAPI, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core import time as timezone
from app.db.session import SessionLocal,active_session,get_session
from app.api.v1 import auth,handlers,capture
from app.services import device_controls
from app.services.projection import snapshot
from app.services.dashboard import summary
from app.schemas.requests import LoginRequest,ActionRequest

app=FastAPI(title='FitGate API',version='4.0.0')
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins.split(','),allow_credentials=True,allow_methods=['GET','POST','DELETE'],allow_headers=['Content-Type','Authorization','X-CSRFToken','Idempotency-Key','X-Device-Code','X-Device-Key'])

@app.middleware('http')
async def database_unit_of_work(request,call_next):
    with SessionLocal() as session:
        token=active_session.set(session)
        try:
            result=await call_next(request)
            await run_in_threadpool(session.commit)
            return result
        except SQLAlchemyError:
            await run_in_threadpool(session.rollback)
            return JSONResponse({'message':'Veritabanı işlemi tamamlanamadı.'},status_code=503)
        finally: active_session.reset(token)

def response(data,status=200): return JSONResponse(jsonable_encoder(data),status_code=status)

async def facade(request,device=False,login=False,action=False):
    if request.method in ['POST','DELETE'] and not device: auth.verify_csrf(request)
    payload={}
    if request.method=='POST':
        raw=bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>900000: raise HTTPException(413,'Request too large')
            raw.extend(chunk)
        try:
            payload=json.loads(raw or b'{}')
            if not isinstance(payload,dict): raise ValueError()
            if login: payload=LoginRequest.model_validate(payload).model_dump()
            if action: payload=ActionRequest.model_validate(payload).model_dump()
        except (ValueError,ValidationError): raise HTTPException(400,'İstek nesnesi geçersiz.') from None
    return SimpleNamespace(user=None if device or login else await run_in_threadpool(auth.current_user,request),data=payload,
        method=request.method,headers=request.headers,query_params=request.query_params,cookies=request.cookies,client=request.client)

@app.get('/api/v1/health/')
def health():
    get_session().execute(text('SELECT 1'))
    return {'status':'ready','database':'postgresql','deviceSimulation':settings.allow_device_simulation}

@app.get('/api/v1/auth/csrf/')
def csrf(request:Request): return auth.response({},request)

@app.post('/api/v1/auth/login/',openapi_extra={'requestBody':{'required':True,'content':{'application/json':{'schema':LoginRequest.model_json_schema()}}},'parameters':[{'name':'X-CSRFToken','in':'header','required':True,'schema':{'type':'string'}}]})
async def login(request:Request): return await run_in_threadpool(auth.login,await facade(request,login=True))

@app.post('/api/v1/auth/refresh/')
def refresh(request:Request):
    auth.verify_csrf(request); return auth.renew(request)

@app.post('/api/v1/auth/logout/')
def logout(request:Request):
    auth.verify_csrf(request); return auth.logout(request)

@app.get('/api/v1/auth/me/')
def me(request:Request): return auth.response({'user':auth.user_info(auth.current_user(request))},request)

@app.get('/api/v1/state/')
def state(request:Request): return {'db':snapshot(auth.current_user(request))}

@app.get('/api/v1/finance/export/')
def finance_export(request:Request):
    from app.services.finance import excel
    from app.services.business import RuleError
    user=auth.current_user(request)
    if user.role!='admin': raise HTTPException(403,'Rapor dışa aktarımı için admin yetkisi gerekli.')
    try: return excel(user,dict(request.query_params))
    except RuleError as error: raise HTTPException(400,str(error)) from None

@app.get('/api/v1/personnel/')
def personnel_state(request:Request):
    from app.services.personnel import state
    return state(auth.current_user(request))

def read_report_transaction():
    session=get_session()
    if not session.in_transaction():
        session.connection(execution_options={'isolation_level':'REPEATABLE READ'})
        session.execute(text('SET TRANSACTION READ ONLY'))

def report_user(request):
    read_report_transaction()
    user=auth.current_user(request)
    if request.query_params.get('branch',str(user.branch_id))!=str(user.branch_id):raise HTTPException(403,'Başka şubenin raporuna erişilemez.')
    if user.role!='admin':
        if request.query_params.get('tab','personnel')!='personnel':raise HTTPException(403,'Yalnızca kendi mesai raporunuza erişebilirsiniz.')
        from app import models as m
        own=m.Employee.objects.filter(user=user,branch_id=user.branch_id).first()
        person=request.query_params.get('person','')
        if not own or person not in ['',f'u:{user.id}',f'e:{own.id}']:raise HTTPException(403,'Yalnızca kendi mesai raporunuza erişebilirsiniz.')
    return user

@app.get('/api/v1/reports/options/')
def report_options(request:Request):
    from app.services.reports.common import options
    read_report_transaction()
    return options(auth.current_user(request))

@app.get('/api/v1/reports/')
def reports(request:Request):
    from app.services.reports import build
    from app.services.business import RuleError
    user=report_user(request)
    try:return build(user,dict(request.query_params),export=request.query_params.get('all')=='true')
    except RuleError as error:raise HTTPException(400,str(error)) from None

@app.get('/api/v1/reports/export/')
def report_export(request:Request):
    from app.services.reports.export import export
    from app.services.business import RuleError
    user=report_user(request)
    try:return export(user,dict(request.query_params))
    except RuleError as error:raise HTTPException(400,str(error)) from None

@app.get('/api/v1/admin/dashboard/')
def dashboard(request:Request):
    user=auth.current_user(request)
    if user.role!='admin' or request.query_params.get('branch',str(user.branch_id))!=str(user.branch_id): raise HTTPException(403,'Yönetici/sube yetkisi gerekli.')
    try:
        day=date.fromisoformat(request.query_params.get('date',timezone.localdate().isoformat()))
        if not 1900<=day.year<=9998: raise ValueError()
    except ValueError: raise HTTPException(400,'Geçerli bir tarih seçin.')
    return summary(user,day)

@app.post('/api/v1/actions/{action}/',openapi_extra={'requestBody':{'required':True,'content':{'application/json':{'schema':ActionRequest.model_json_schema()}}},'parameters':[{'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string','format':'uuid'}},{'name':'X-CSRFToken','in':'header','required':True,'schema':{'type':'string'}}]})
async def action(request:Request,action:str): return await run_in_threadpool(handlers.action,await facade(request,action=True),action)

@app.get('/api/v1/actions/status/{key}/')
def action_status(request:Request,key:str):
    import uuid
    from app import models as m
    user=auth.current_user(request)
    try:key=uuid.UUID(key)
    except ValueError:raise HTTPException(400,'İşlem anahtarı geçersiz.') from None
    m.Branch.objects.select_for_update().get(pk=user.branch_id)
    record=m.OperationReceipt.objects.filter(request_id=key,actor_id=user.id).first()
    return {'status':'completed' if record else 'not_found'}

@app.get('/api/v1/cards/capture/{id}/')
@app.delete('/api/v1/cards/capture/{id}/')
async def capture_detail(request:Request,id:str): return await run_in_threadpool(capture.detail,await facade(request),id)

def register(path,function,methods,device=False):
    async def endpoint(request:Request): return await run_in_threadpool(function,await facade(request,device=device))
    endpoint.__name__=function.__name__
    extra={}
    if 'POST' in methods:
        extra['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','additionalProperties':True}}}}
        headers=['X-Device-Code','X-Device-Key'] if device else ['X-CSRFToken']
        if path in ['device/access/authorize/','device/passage-events/','device/attendance/']: headers.append('Idempotency-Key')
        extra['parameters']=[{'name':name,'in':'header','required':True,'schema':{'type':'string'}} for name in headers]
    app.add_api_route('/api/v1/'+path,endpoint,methods=methods,openapi_extra=extra)

for path,fn,methods,device in [
    ('members/',handlers.members,['GET'],False),
    ('access/recent-entries/',handlers.recent_entries,['GET'],False),
    ('diagnostics/events/',handlers.diagnostic_events,['GET'],False),
    ('sensors/measurements/',handlers.sensor_measurements,['GET'],False),
    ('cards/capture/',capture.begin,['POST'],False),
    ('device/capture/status/',capture.device_status,['POST'],True),
    ('device/capture/read/',capture.device_read,['POST'],True),
    ('device/access/authorize/',handlers.device_authorize,['POST'],True),
    ('device/passage-events/',handlers.device_passage,['POST'],True),
    ('device/heartbeat/',handlers.device_heartbeat,['POST'],True),
    ('device/attendance/',handlers.device_attendance,['POST'],True),
    ('device/measurements/',handlers.device_measurements,['POST'],True),
    ('device/diagnostics/',handlers.device_diagnostic,['POST'],True),
    ('device/commands/poll/',device_controls.poll,['POST'],True),
    ('device/commands/result/',device_controls.complete,['POST'],True),
]: register(path,fn,methods,device)
