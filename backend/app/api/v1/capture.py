import re
from datetime import timedelta
from app.db import transaction
from app.core import time as timezone
from app import models as m
from app.services.diagnostics import log
from app.api.v1.handlers import authenticated_device, Response
ValidationError = ValueError

def data(item):
    now=timezone.now()
    state='cancelled' if item.cancelled else 'assigned' if item.consumed_at else 'captured' if item.uid else 'expired' if item.expires_at<=now else 'waiting'
    return {'id':str(item.id),'uid':item.uid,'status':state,'expiresAt':item.expires_at.isoformat(),'memberId':str(item.member_id)}



def begin(request):
    from app.services.system_settings import permitted
    if not permitted(request.user,'cardManagement'):return Response({'message':'Kart yönetimi yetkisi gerekli.'},status=403)
    if request.user.role not in ['admin','staff']: return Response({'message':'Kart yönetimi yetkisi gerekli.'},status=403)
    try:
        with transaction.atomic():
            m.Branch.objects.select_for_update().get(pk=request.user.branch_id)
            device=m.Device.objects.filter(pk=request.data.get('deviceId'),branch=request.user.branch,simulated=False,enabled=True).first()
            member=m.Member.objects.filter(pk=request.data.get('memberId'),branch=request.user.branch).first()
            now=timezone.now()
            if not device or not member: return Response({'message':'Üye veya okuyucu bulunamadı.'},status=400)
            if device.purpose not in ['access','mixed']: return Response({'message':'Personel mesai cihazı üye kart tanımlamada kullanılamaz.'},status=400)
            if not device.last_seen or now-device.last_seen>timedelta(seconds=30): return Response({'message':'USB okuyucu çevrimdışı.'},status=400)
            if m.Grant.objects.filter(device=device,confirmed=False,expires_at__gt=now).exists(): return Response({'message':'Okuyucuda devam eden geçiş var.'},status=409)
            if m.CardCapture.objects.filter(device=device,cancelled=False,consumed_at__isnull=True,expires_at__gt=now).exists(): return Response({'message':'Okuyucu başka bir kart tanımlama işlemi için bekliyor.'},status=409)
            item=m.CardCapture.objects.create(branch=request.user.branch,device=device,member=member,actor=request.user,expires_at=now+timedelta(seconds=45))
            log(device,'capture_wait',f'{member.name} için kart bekleniyor (45 saniye).',actor=request.user)
            return Response(data(item))
    except (ValueError,TypeError,ValidationError): return Response({'message':'İstek geçersiz.'},status=400)



def detail(request,id):
    item=m.CardCapture.objects.filter(pk=id,branch=request.user.branch,actor=request.user).first()
    if not item: return Response({'message':'Okutma kaydı bulunamadı.'},status=404)
    if request.method=='DELETE':
        item.cancelled=True; item.save(update_fields=['cancelled'])
        log(item.device,'capture_cancel','Kart tanımlama isteği iptal edildi.',actor=request.user)
    return Response(data(item))





def device_status(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz doğrulanamadı.'},status=401)
    item=m.CardCapture.objects.filter(device=device,cancelled=False,consumed_at__isnull=True,expires_at__gt=timezone.now()).order_by('expires_at').first()
    return Response({'ok':True,'capture':data(item) if item else None})





def device_read(request):
    device=authenticated_device(request)
    if not device: return Response({'message':'Cihaz doğrulanamadı.'},status=401)
    uid=request.data.get('uid','')
    if not isinstance(uid,str) or not re.fullmatch(r'(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})',uid): return Response({'message':'Kart UID geçersiz.'},status=400)
    with transaction.atomic():
        m.Branch.objects.select_for_update().get(pk=device.branch_id)
        item=m.CardCapture.objects.filter(pk=request.data.get('captureId'),device=device,cancelled=False,consumed_at__isnull=True).first()
        if not item or item.expires_at<=timezone.now(): return Response({'message':'Okutma isteği bitmiş.'},status=409)
        if item.uid!=uid:
            item.uid=uid; item.captured_at=timezone.now(); item.save(update_fields=['uid','captured_at'])
        log(device,'capture_read',f'Kart UID alındı: {uid}. Üye: {item.member.name}. Atama onayı bekleniyor.',actor=item.actor)
        return Response({'ok':True,'capture':data(item)})
