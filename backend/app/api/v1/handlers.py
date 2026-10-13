import uuid
from datetime import timedelta
from sqlalchemy.exc import IntegrityError
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse
from app import models as m
from app.core import time as timezone
from app.core.config import settings
from app.core.security import check_password
from app.services.business import execute, RuleError, ADMIN, parse_time
from app.services.projection import snapshot, wire
from app.services.diagnostics import log
from app.repositories.query import Q

class Response(JSONResponse):
    def __init__(self,data,status=200): super().__init__(jsonable_encoder(data),status_code=status)

def members(request):
    from app.services.system_settings import permitted
    if not permitted(request.user,'memberManagement'):return Response({'message':'Üye görüntüleme yetkisi gerekli.'},status=403)
    if request.user.role=='trainer': return Response({'message':'Genel üye listesi için yetkiniz yok; dersinizin katılımcı listesini kullanın.'},status=403)
    query=request.query_params.get('q','')[:120]
    try: page=max(1,int(request.query_params.get('page',1))); size=min(100,max(1,int(request.query_params.get('page_size',20))))
    except ValueError: return Response({'message':'Sayfalama geçersiz.'},status=400)
    records=m.Member.objects.filter(branch=request.user.branch).order_by('number')
    if query:
        records=records.filter(Q(name__icontains=query)|Q(phone__icontains=query)|Q(number__icontains=query))
    total=records.count(); return Response({'count':total,'page':page,'pageSize':size,'results':[wire(item) for item in records[(page-1)*size:page*size]]})



def action(request,action):
    from app.services.personnel import ADMIN_ACTIONS
    if request.user.role!='admin' and action in ADMIN_ACTIONS: return Response({'message':'Yönetici yetkisi gerekiyor.'},status=403)
    if request.user.role!='admin' and action in ADMIN: return Response({'message':'Bu işlem için yönetici yetkisi gerekiyor.'},status=403)
    try:
        if not isinstance(request.data,dict) or not isinstance(request.data.get('payload',{}),dict):
            return Response({'message':'İstek nesne biçiminde olmalı.'},status=400)
        response=execute(action,request.data.get('payload',{}),request.user,request.headers.get('Idempotency-Key'))
        return Response({**response,'db':snapshot(request.user)})
    except RuleError as error: return Response({'message':str(error)},status=400)
    except (ValueError,TypeError,KeyError,AttributeError): return Response({'message':'İstek alanları geçersiz.'},status=400)
    except IntegrityError: return Response({'message':'İşlem mevcut bir kayıtla çakışıyor. Veriyi yenileyip tekrar deneyin.'},status=409)


def authenticated_device(request):
    code=request.headers.get('X-Device-Code',''); token=request.headers.get('X-Device-Key','')
    device=m.Device.objects.filter(code=code,enabled=True,simulated=False).first()
    if not device or not token or not check_password(token,device.token_hash): return None
    return device





def device_authorize(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz kimliği doğrulanamadı.'},status=401)
    try:
        p={'uid':request.data.get('credential',''),'direction':request.data.get('direction')}
        if 'validationMode' in request.data: p['validationMode']=request.data['validationMode']
        response=execute('authorize',p,None,request.headers.get('Idempotency-Key'),device)
        return Response(response)
    except (RuleError,ValueError,IntegrityError) as error: return Response({'message':str(error)},status=400)





def device_passage(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz kimliği doğrulanamadı.'},status=401)
    try:
        p={'id':request.data.get('grantId'),'eventId':request.data.get('eventId'),'occurredAt':request.data.get('occurredAt'),'direction':request.data.get('direction')}
        for field in ['validationMode','triggeringSensor']:
            if field in request.data: p[field]=request.data[field]
        if p['direction'] not in ['entry','exit']: raise RuleError('Sensör yönü gerekli.')
        if not p['eventId'] or not p['occurredAt']: raise RuleError('Olay kimliği ve zaman gerekli.')
        return Response(execute('confirmPassage',p,None,request.headers.get('Idempotency-Key'),device))
    except (RuleError,ValueError,IntegrityError) as error:
        log(device,'passage_rejected','Fiziksel geçiş kaydı reddedildi: '+str(error),'error')
        return Response({'message':str(error)},status=400)





def device_heartbeat(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz kimliği doğrulanamadı.'},status=401)
    if not isinstance(request.data,dict): return Response({'message':'Cihaz bilgisi nesne olmalı.'},status=400)
    connected=request.data.get('connected',True)
    sensor=request.data.get('sensor','unknown')
    if type(connected) is not bool or sensor not in ['ready','fault','disabled','unknown']:
        return Response({'message':'Bağlantı veya sensör durumu geçersiz.'},status=400)
    previous=device.sensor
    telemetry=request.data.get('telemetry',{})
    if isinstance(telemetry,dict):
        values={key:value for key,value in telemetry.items() if key in ['outsideCm','insideCm'] and (value is None or type(value) is int and 2<=value<=340)}
        for key,allowed in {'rfid':['ready','fault','unknown'],'servo':['open','closed','unknown'],'lcd':['ready','fault','unknown'],'connection':['connected','retrying']}.items():
            if telemetry.get(key) in allowed: values[key]=telemetry[key]
        for key in ['port','lastError','firmware','lcdTop','lcdBottom','lastScanUid']:
            if isinstance(telemetry.get(key),str): values[key]=telemetry[key][:120]
        for key in ['buzzer','led']:
            if type(telemetry.get(key)) is bool: values[key]=telemetry[key]
        for key,allowed in {'validationMode':['two_sensor','single_sensor_prototype'], 'passageState':['idle','authorizing','waiting_first','detected','waiting_clear','completed','prototype_triggered','fault'],'detectedDirection':['none','entry','exit']}.items():
            if telemetry.get(key) in allowed: values[key]=telemetry[key]
        if isinstance(telemetry.get('progressAt'),str):
            try:
                if abs((timezone.now()-parse_time(telemetry['progressAt'])).total_seconds())<15: values['progressAt']=telemetry['progressAt']
            except (ValueError,TypeError,RuleError): pass
        device.telemetry={**device.telemetry,**values}
    device.last_seen=timezone.now() if connected else None; device.sensor=sensor if connected else 'unknown'
    device.save(update_fields=['last_seen','sensor','telemetry'])
    if previous!=device.sensor: log(device,'sensor','Sensör durumu: '+device.sensor,'info' if device.sensor=='ready' else 'warning')
    return Response({'ok':True,'serverTime':timezone.now().isoformat(),'purpose':device.purpose,'mode':device.mode})





def device_attendance(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz kimliği doğrulanamadı.'},status=401)
    try:
        return Response(execute('scanEmployee',{'uid':request.data.get('credential',''),'direction':request.data.get('direction','auto'),'occurredAt':request.data.get('occurredAt')},None,request.headers.get('Idempotency-Key'),device))
    except (RuleError,ValueError,IntegrityError) as error: return Response({'message':str(error)},status=400)



def recent_entries(request):
    from app.services.system_settings import permitted
    if request.user.role!='admin' and not permitted(request.user,'memberManagement'):return Response({'message':'Geçiş listesi yetkisi gerekli.'},status=403)
    branch=request.user.branch_id
    visits=m.Visit.objects.filter(branch_id=branch)
    today=timezone.localdate()
    latest=visits.select_related('member','device').order_by('-entry','-pk')[:10]
    movements=[]
    for direction,field,records in [
        ('entry','entry',visits.select_related('member','device').order_by('-entry','-pk')[:10]),
        ('exit','exit',visits.filter(exit__isnull=False).select_related('member','device').order_by('-exit','-pk')[:10]),
    ]:
        for item in records:
            movements.append({'id':f'{item.id}:{direction}','memberId':str(item.member_id),
                'name':item.member.name,'number':item.member.number,'direction':direction,
                'at':getattr(item,field).isoformat(),'device':item.device.name if item.device else '',
                'method':item.method})
    movements.sort(key=lambda item:(item['at'],item['id']),reverse=True)
    attempts=m.Attempt.objects.filter(branch_id=branch).select_related('member','device','grant').order_by('-at','-pk')[:10]
    now=timezone.now()
    attempt_rows=[]
    for item in attempts:
        expired=item.status=='granted' and item.grant is not None and item.grant.expires_at<=now
        if item.employee_id and request.user.role!='admin' and item.employee.user_id!=request.user.id: continue
        attempt_rows.append({'id':str(item.id),'name':item.member.name if item.member else item.employee.name if item.employee else 'Tanımsız kart',
            'uid':item.card,'direction':item.direction,'status':'expired' if expired else item.status,
            'reason':'Geçiş tamamlanmadı; izin süresi doldu.' if expired else item.reason,
            'at':item.at.isoformat(),'device':item.device.name,'employeeId':str(item.employee_id) if item.employee_id else None})
    return Response({'inside':visits.filter(exit__isnull=True).count(),
        'today':visits.filter(entry__date=today).count(),
        'movements':movements[:10],
        'attempts':attempt_rows,
        'serverTime':timezone.now().isoformat(),
        'entries':[{'id':str(item.id),'memberId':str(item.member_id),'name':item.member.name,
            'number':item.member.number,'entry':item.entry.isoformat(),
            'exit':item.exit.isoformat() if item.exit else None,'device':item.device.name if item.device else '',
            'method':item.method} for item in latest]})



def diagnostic_events(request):
    if request.user.role!='admin':return Response({'message':'Teknik cihaz günlüğü için admin yetkisi gerekli.'},status=403)
    from app.services.system_settings import permitted
    if not permitted(request.user,'deviceRead'):return Response({'message':'Cihaz bilgisi yetkisi gerekli.'},status=403)
    records=m.DeviceEvent.objects.filter(branch=request.user.branch).select_related('device','actor')
    if request.user.role!='admin': records=records.filter(Q(actor=request.user)|Q(actor__isnull=True))
    records=list(records.order_by('-at','-pk')[:60])
    devices=m.Device.objects.filter(branch=request.user.branch,simulated=False)
    now=timezone.now()
    return Response({'events':[{'id':str(item.id),'at':item.at.isoformat(),'level':item.level,
        'type':item.event_type,'message':item.message,'device':item.device.name} for item in reversed(records)],
        'devices':[{'name':d.name,'online':bool(d.last_seen and now-d.last_seen<timedelta(seconds=30)), 'sensor':d.sensor,'telemetry':d.telemetry} for d in devices]})





def device_diagnostic(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz doğrulanamadı.'},status=401)
    messages={'connected':'Arduino USB bağlantısı kuruldu.','capture_mode':'Kart tanımlama modu etkin; turnike açılmaz.',
        'normal_mode':'Okuyucu geçiş moduna döndü.','rfid':'RFID kart okundu.',
        'removed':'Kart okuyucudan kaldırıldı; yeniden okutmaya hazır.',
        'sensor_denied':'Geçiş reddedildi: sensörler hazır değil.','fault':'Arduino geçiş/sensör hatası bildirdi.',
        'queued':'Fiziksel geçiş PC kuyruğuna kaydedildi.','queue_review':'Geçiş kaydı inceleme gerektiriyor.',
        'prototype_queued':'Tek sensör prototip olayı PC kuyruğuna kaydedildi; tam fiziksel geçiş kanıtı değildir.',
        'server_error':'Sunucuya ulaşılamadı; turnike açma onayı verilmedi.',
        'entry_detected':'Giriş algılandı; ikinci sensör ve alanın boşalması bekleniyor.',
        'exit_detected':'Çıkış algılandı; ikinci sensör ve alanın boşalması bekleniyor.'}
    event=request.data.get('type')
    if event not in messages: return Response({'message':'Olay türü geçersiz.'},status=400)
    message=messages[event]
    detail=request.data.get('detail','')
    if isinstance(detail,str) and event=='fault': message+=' '+detail[:80]
    level='warning' if event in ['sensor_denied','fault','queue_review','server_error'] else 'info'
    log(device,event,message,level)
    return Response({'ok':True})





def device_measurements(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz doğrulanamadı.'},status=401)
    payload=request.data
    if not isinstance(payload,dict) or set(payload)!= {'outsideCm','insideCm'}:
        return Response({'message':'İki sensör ölçümü gerekli.'},status=400)
    if any(v is not None and (type(v) is not int or not 2<=v<=340) for v in payload.values()):
        return Response({'message':'Mesafe değeri geçersiz.'},status=400)
    device.telemetry={**device.telemetry,**payload};device.telemetry_at=timezone.now()
    device.save(update_fields=['telemetry','telemetry_at'])
    return Response({'ok':True})



def sensor_measurements(request):
    if request.user.role!='admin':return Response({'message':'Teknik sensör bilgisi için admin yetkisi gerekli.'},status=403)
    from app.services.system_settings import permitted
    if not permitted(request.user,'deviceRead'):return Response({'message':'Cihaz bilgisi yetkisi gerekli.'},status=403)
    now=timezone.now()
    devices=m.Device.objects.filter(branch=request.user.branch,simulated=False).order_by('code')
    return Response({'serverTime':now.isoformat(),'devices':[{
        'id':str(d.id),'name':d.name,'code':d.code,
        'online':bool(d.last_seen and now-d.last_seen<timedelta(seconds=30)),
        'sensor':d.sensor,'measuredAt':d.telemetry_at.isoformat() if d.telemetry_at else None,
        'ageSeconds':max(0,(now-d.telemetry_at).total_seconds()) if d.telemetry_at else None,
        'stale':not d.telemetry_at or now-d.telemetry_at>timedelta(seconds=4),
        'outsideCm':d.telemetry.get('outsideCm'),'insideCm':d.telemetry.get('insideCm')
    } for d in devices]})
