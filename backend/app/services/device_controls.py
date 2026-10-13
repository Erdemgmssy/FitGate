from datetime import timedelta
import uuid
from app import models as m
from app.core import time as timezone
from app.db import transaction
from app.services.business import require, get
from app.services.diagnostics import log
from app.api.v1.handlers import authenticated_device, Response


def queue(p,user,branch):
    device=get(m.Device,p.get('deviceId'),branch); now=timezone.now()
    require(user.role=='admin' and p.get('confirmed') is True,'Admin ve güvenli test alanı onayı gerekli.')
    require(p.get('action') in ['servo','lcd','indicators'],'Tanılama testi geçersiz.')
    require(device.enabled and not device.simulated and device.last_seen and now-device.last_seen<timedelta(seconds=10),'Gerçek cihaz bağlantısı güncel değil.')
    require(device.telemetry.get('firmware') in ['5','6'],'Tanılama için firmware 5 veya 6 gerekli.')
    require(not m.Grant.objects.filter(device=device,confirmed=False,expires_at__gt=now).exists(),'Bekleyen turnike işlemi var.')
    require(not m.CardCapture.objects.filter(device=device,cancelled=False,consumed_at__isnull=True,expires_at__gt=now).exists(),'Kart tanımlama devam ediyor.')
    require(not m.DeviceCommand.objects.filter(device=device,status__in=['queued','sent'],expires_at__gt=now).exists(),'Önceki tanılama testi devam ediyor.')
    if p['action']=='servo':
        require(device.sensor=='ready' and device.telemetry_at and now-device.telemetry_at<timedelta(seconds=4) and all(type(device.telemetry.get(key)) is int and device.telemetry[key]>20 for key in ['outsideCm','insideCm']),'Servo testi için iki sensör de güncel, geçerli ve alan boş olmalı.')
    item=m.DeviceCommand.objects.create(branch=branch,device=device,actor=user,action=p['action'],expires_at=now+timedelta(seconds=15))
    m.Audit.objects.create(branch=branch,actor=user,type='queueDeviceDiagnostic',entity_id=str(item.id),detail={'deviceId':str(device.id),'action':item.action})
    return {'id':str(item.id),'message':'Tanılama testi kuyruğa alındı.'}


def poll(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz doğrulanamadı.'},status=401)
    with transaction.atomic():
        m.Branch.objects.select_for_update().get(pk=device.branch_id)
        now=timezone.now()
        m.DeviceCommand.objects.filter(device=device,status__in=['queued','sent'],expires_at__lte=now).update(status='expired',result='Cihaz sonucu zamanında alınamadı.')
        command=m.DeviceCommand.objects.filter(device=device,status='queued',expires_at__gt=now).order_by('created_at').first()
        if command: command.status='sent'; command.save()
        return Response({'ok':True,'command':{'id':str(command.id),'action':command.action} if command else None})


def complete(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz doğrulanamadı.'},status=401)
    with transaction.atomic():
        m.Branch.objects.select_for_update().get(pk=device.branch_id)
        try: identifier=uuid.UUID(str(request.data.get('id')))
        except (ValueError,TypeError): return Response({'message':'Komut kimliği geçersiz.'},status=400)
        command=m.DeviceCommand.objects.filter(device=device,pk=identifier).first()
        status=request.data.get('status')
        if not command or status not in ['ok','error']: return Response({'message':'Tanılama sonucu geçersiz.'},status=400)
        if command.status in ['complete','failed','expired']: return Response({'ok':True})
        command.status='complete' if status=='ok' and command.expires_at>timezone.now() else 'failed'
        command.completed_at=timezone.now(); command.result=str(request.data.get('detail',''))[:120]; command.save()
        log(device,'diagnostic_result',command.action+': '+command.status+(' '+command.result if command.result else ''),'info' if command.status=='complete' else 'warning',command.actor)
        return Response({'ok':True})
