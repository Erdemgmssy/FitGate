"""Explicit development-only weak evidence, snapshotted on the existing Grant."""
from app import models as m
from app.core.config import settings
from .business import require

PROTOTYPE = 'single_sensor_prototype'
NORMAL = 'two_sensor'

def permitted(device):
    return (settings.environment == 'development' and settings.allow_single_sensor_prototype
            and settings.single_sensor_prototype_device_code == device.code and not device.simulated)

def authorization_mode(device, payload):
    mode = payload.get('validationMode', NORMAL)
    require(mode in [NORMAL, PROTOTYPE], 'Geçiş doğrulama modu geçersiz.')
    if mode == PROTOTYPE or device.telemetry.get('firmware') == '7':
        require(mode == PROTOTYPE and permitted(device), 'Tek sensör prototipi bu cihaz/ortam için etkin değil.')
        require(device.telemetry.get('firmware') == '7' and device.telemetry.get('validationMode') == PROTOTYPE,
                'Prototip firmware bildirimi gerekli.')
        require(payload.get('direction') == 'auto', 'Prototip yönü açık ziyaret üzerinden belirlenir.')
    return mode

def annotate(result, mode):
    result['validationMode'] = mode
    result['physicalVerified'] = False
    if result.get('approved'):
        grant = m.Grant.objects.get(pk=result['grantId'])
        grant.context = {**grant.context, 'validationMode': mode}
        grant.save()
    return result

def consistent_visits(visits, subject, branch):
    if len(visits)>1: return False
    if not visits: return True
    visit=visits[0]
    if visit.branch_id!=branch.id: return False
    if not visit.entry_event_id:
        return (isinstance(subject,m.Member) and visit.member_id==subject.id
                and visit.method in ['MANUAL','ADMIN_CORRECTION'] and visit.entry_actor_id is not None)
    event=m.Passage.objects.filter(pk=visit.entry_event_id,branch_id=branch.id).first()
    if not event or not event.grant.confirmed or event.grant.direction!='entry': return False
    return (event.grant.member_id==subject.id if isinstance(subject,m.Member) else event.grant.employee_id==subject.id)

def confirmation(grant, device, payload):
    mode = grant.context.get('validationMode', NORMAL)
    require(payload.get('validationMode', NORMAL) == mode, 'Geçiş kanıtı izin moduyla uyuşmuyor.')
    if mode == PROTOTYPE:
        require(permitted(device), 'Tek sensör prototipi kapalı; olay inceleme gerektiriyor.')
        require(type(payload.get('triggeringSensor')) is int and payload['triggeringSensor'] in [0, 1], 'Tetikleyen sensör gerekli.')
        grant.context = {**grant.context, 'triggeringSensor': payload['triggeringSensor'], 'physicalVerified': False}
        grant.save()
    return mode
