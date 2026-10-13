from app.models import DeviceEvent


def log(device, event, message, level='info', actor=None):
    DeviceEvent.objects.create(branch_id=device.branch_id,device=device,event_type=event,
        level=level,message=message[:600],actor=actor)
