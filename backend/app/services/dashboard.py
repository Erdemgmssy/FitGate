from collections import defaultdict
from datetime import datetime, time, timedelta
from app.core import time as timezone
from app import models as m
from .membership import status as membership_status


def summary(user, day):
    branch = user.branch
    now = timezone.now()
    today = timezone.localdate(now)
    def midnight(value):
        return timezone.make_aware(datetime.combine(value, time.min))
    start, end = midnight(day), midnight(day + timedelta(days=1))
    month_start = day.replace(day=1)
    month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    members = list(m.Member.objects.filter(branch=branch).values('id', 'name', 'number', 'active', 'blocked'))
    member_map = {row['id']: row for row in members}
    subscriptions = [{**{column.key:getattr(sub,column.key) for column in m.Subscription.__table__.columns},'status':membership_status(sub,today)}
        for sub in m.Subscription.objects.filter(branch=branch).order_by('created_at','pk')]
    valid, latest = {}, {}
    for sub in subscriptions:
        if sub['status'] != 'cancelled':
            latest[sub['member_id']] = sub
        if sub['status'] == 'active' and sub['start'] <= today and (sub['end'] is None or today <= sub['end']):
            previous = valid.get(sub['member_id'])
            if not previous or sub['end'] is not None and (previous['end'] is None or sub['end'] < previous['end']):
                valid[sub['member_id']] = sub
    active = sum(row['active'] and not row['blocked'] and row['id'] in valid for row in members)
    ending = {key for key, sub in valid.items() if sub['end'] is not None and today <= sub['end'] <= today + timedelta(days=7)}
    visits = m.Visit.objects.filter(branch=branch)
    confirmed_visits = visits.filter(entry_event__grant__confirmed=True, entry_event__grant__direction='entry', entry_event__device__simulated=False)
    physical = confirmed_visits.exclude(method='Tek sensor prototipi').filter(entry__gte=start, entry__lt=end)
    rejected = m.Attempt.objects.filter(branch=branch, status='rejected', direction='entry', at__gte=start, at__lt=end)
    invoices = list(m.Invoice.objects.filter(branch=branch).values())
    payments = list(m.Payment.objects.filter(branch=branch).values())
    refunds = list(m.Refund.objects.filter(branch=branch).values())
    sales = list(m.Sale.objects.filter(branch=branch).values())
    product_returns = list(m.StockMovement.objects.filter(branch=branch,returned_units__gt=0).values())
    payment_map = {p['id']: p for p in payments}
    paid = defaultdict(int)
    for payment in payments:
        paid[payment['invoice_id']] += payment['amount_cents']
    for refund in refunds:
        payment = payment_map.get(refund['payment_id'])
        if payment:
            paid[payment['invoice_id']] -= refund['amount_cents']
    def collection(first, last):
        return (sum(p['amount_cents'] for p in payments if first <= p['at'] < last)
            - sum(r['amount_cents'] for r in refunds if first <= r['at'] < last)
            + sum(s['total_cents'] for s in sales if first <= s['at'] < last)
            - sum(s['refund_cents'] for s in product_returns if first <= s['at'] < last))
    debts = {i['id']: max(0, i['total_cents'] - paid[i['id']]) for i in invoices if i['status'] != 'cancelled'}
    installments = defaultdict(list)
    for row in m.Installment.objects.filter(branch=branch).order_by('due', 'pk').values():
        installments[row['invoice_id']].append(row)
    attention = []
    def alert(key, severity, message, target, member=None):
        attention.append({'id': key, 'severity': severity, 'message': message, 'target': target,
            'memberId': str(member) if member else None})
    for invoice in invoices:
        if debts.get(invoice['id'], 0) <= 0:
            continue
        due = sum(i['amount_cents'] for i in installments[invoice['id']] if i['due'] < today)
        if due > paid[invoice['id']]:
            name = member_map.get(invoice['member_id'], {}).get('name', 'Üye')
            alert(f'debt-{invoice["id"]}', 'high', f'{name}: gecikmiş ödeme.', 'payments', invoice['member_id'])
    for member_id, sub in latest.items():
        name = member_map.get(member_id, {}).get('name', 'Üye')
        if sub['end'] is not None and sub['end'] < today and member_id not in valid:
            alert(f'expired-{sub["id"]}', 'medium', f'{name}: üyelik süresi dolmuş.', 'members', member_id)
        elif member_id in ending:
            alert(f'ending-{sub["id"]}', 'low', f'{name}: üyelik {sub["end"].isoformat()} tarihinde bitiyor.', 'members', member_id)
    inside = []
    confirmed_ids=set(confirmed_visits.values_list('id',flat=True))
    manual_visits=visits.filter(entry_actor_id__isnull=False,entry_event_id__isnull=True,method__in=['MANUAL','ADMIN_CORRECTION'])
    manual_ids=set(manual_visits.values_list('id',flat=True))
    for visit in visits.filter(exit__isnull=True, exit_event__isnull=True).select_related('member', 'device').order_by('entry', 'pk'):
        if visit.id not in confirmed_ids and visit.id not in manual_ids: continue
        inside.append({'id': str(visit.id), 'memberId': str(visit.member_id), 'name': visit.member.name,
            'number': visit.member.number, 'entry': visit.entry.isoformat(), 'device': visit.device.name if visit.device else 'Manuel',
            'method':visit.method,
            'minutes': max(0, int((now - visit.entry).total_seconds() // 60))})
        if now - visit.entry > timedelta(hours=24):
            alert(f'open-{visit.id}', 'high', f'{visit.member.name}: 24 saati aşan açık ziyaret; çıkış kontrol edilmeli.', 'access', visit.member_id)
    devices = []
    for device in m.Device.objects.filter(branch=branch).order_by('name'):
        online = bool(not device.simulated and device.enabled and device.last_seen and now - device.last_seen < timedelta(seconds=60))
        state = 'simulated' if device.simulated else 'disabled' if not device.enabled else 'offline' if not online else 'fault' if device.sensor == 'fault' else 'unknown' if device.sensor != 'ready' else 'online'
        devices.append({'id': str(device.id), 'name': device.name, 'code': device.code, 'state': state,
            'sensor': device.sensor, 'lastSeen': device.last_seen.isoformat() if device.last_seen else None,
            'rfid': 'unknown', 'controller': 'online' if online else 'unknown',
            'servo': 'unknown',
            'measurements': {
                'outsideCm': device.telemetry.get('outsideCm') if online and device.telemetry_at and now-device.telemetry_at < timedelta(seconds=4) else None,
                'insideCm': device.telemetry.get('insideCm') if online and device.telemetry_at and now-device.telemetry_at < timedelta(seconds=4) else None,
                'at': device.telemetry_at.isoformat() if device.telemetry_at else None,
            },
            'telemetry': device.telemetry, 'simulated': device.simulated})
        known_fault=m.DeviceEvent.objects.filter(device=device,event_type='fault',level='error',at__gte=now-timedelta(hours=24)).exists() if not online and not device.last_seen else False
        if not device.simulated and device.enabled and device.mode=='auto' and ((device.last_seen and (not online or device.sensor=='fault')) or known_fault):
            alert(f'device-{device.id}', 'high', f'{device.name}: ' + ('sensör hatası.' if online else 'haberleşme yok.'), 'devices')
    last_attempts = m.Attempt.objects.filter(branch=branch, at__gte=now-timedelta(hours=24)).select_related('member', 'grant').order_by('-at')
    rejected_count = last_attempts.filter(status='rejected').count()
    if rejected_count:
        alert('rejected', 'medium', f'Son 24 saatte {rejected_count} reddedilen geçiş denemesi.', 'access')
    missing = sum(a.status == 'granted' and hasattr(a, 'grant') and a.grant.expires_at < now for a in last_attempts)
    if missing:
        alert('missing', 'high', f'{missing} izin için fiziksel geçiş kaydı tamamlanmadı.', 'access')
    faults=m.DeviceEvent.objects.filter(branch=branch,device__simulated=False,at__gte=now-timedelta(hours=24)).filter(event_type__in=['fault','queue_review']).count()
    if faults:
        alert('passage-faults', 'high', f'Son 24 saatte {faults} cihaz/geçiş hatası; kayıtlar kontrol edilmeli.', 'access')
    for notice in m.Notice.objects.filter(branch=branch).order_by('-at').values('id', 'message','details'):
        if notice['details'].get('automatic') or notice['details'].get('status','active')!='active':continue
        alert(str(notice['id']), 'low', notice['message'], 'notifications')
    attention.sort(key=lambda item: ({'high': 0, 'medium': 1, 'low': 2}[item['severity']], {'devices': 0, 'access': 1, 'payments': 2}.get(item['target'], 3)))
    reads = set(m.ReadNotice.objects.filter(user=user).values_list('notice_id', flat=True))
    for item in attention:
        item['read'] = item['id'] in reads
    unread = sum(not a['read'] for a in attention)
    hour_counts = defaultdict(int)
    for at in physical.values_list('entry', flat=True):
        hour_counts[timezone.localtime(at).hour] += 1
    hours = set()
    schedules = list(m.Plan.objects.filter(branch=branch, active=True).values('allowed_from', 'allowed_to'))
    for plan in schedules:
        try:
            first = time.fromisoformat(plan['allowed_from']).hour
            last = time.fromisoformat(plan['allowed_to']).hour
        except ValueError:
            continue
        hours.update(range(first, last+1) if first <= last else list(range(first, 24)) + list(range(last+1)))
    hours.update(hour_counts)
    if not hours:
        hours.update(range(24))
    events = []
    for passage in m.Passage.objects.filter(branch=branch, device__simulated=False, grant__confirmed=True, occurred_at__gte=start, occurred_at__lt=end).select_related('grant__member', 'device').order_by('-occurred_at', '-pk')[:10]:
        member = passage.grant.member; employee=passage.grant.employee
        prototype=passage.grant.context.get('validationMode')=='single_sensor_prototype'
        events.append({'id': str(passage.id), 'memberId': str(member.id) if member else None, 'employeeId':str(employee.id) if employee else None,'name': member.name if member else employee.name, 'number': member.number if member else 'Personel',
            'direction': passage.grant.direction, 'at': passage.occurred_at.isoformat(), 'device': passage.device.name,
            'kind': 'prototype' if prototype else 'physical', 'status': 'confirmed', 'reason': 'Tek sensör prototip olayı; tam fiziksel geçiş kanıtı değil' if prototype else 'Doğrulanmış fiziksel geçiş'})
    for visit in visits:
        for direction,at,method,actor,reason in [('entry',visit.entry,visit.method,visit.entry_actor,visit.entry_reason),
                                               ('exit',visit.exit,visit.exit_method,visit.exit_actor,visit.exit_reason)]:
            if not at or not start<=at<end or method not in ['MANUAL','ADMIN_CORRECTION'] or not actor: continue
            events.append({'id':str(visit.id)+'-'+direction,'memberId':str(visit.member_id),
                'name':visit.member.name,'number':visit.member.number,'direction':direction,'at':at.isoformat(),
                'device':'Manuel','kind':'correction' if method=='ADMIN_CORRECTION' else 'manual',
                'status':'confirmed','reason':actor.full_name+': '+reason})
    events.sort(key=lambda item: (item['at'], item['id']), reverse=True)
    return {'serverTime': now.isoformat(), 'date': day.isoformat(), 'branch': {'id': str(branch.id), 'name': branch.name},
        'branches': [{'id': str(branch.id), 'name': branch.name}], 'unread': unread,
        'metrics': {'members': len(members), 'activeMembers': active, 'inside': len(inside), 'capacity': branch.capacity,
            'entries': physical.count(), 'rejectedEntries': rejected.count(), 'ending': len(ending),
            'manualEntries':manual_visits.filter(entry__gte=start,entry__lt=end).count(),
            'dailyCents': collection(start, end), 'weeklyCents': collection(midnight(day-timedelta(days=6)), end),
            'monthlyCents': collection(midnight(month_start), midnight(month_end)), 'debtCents': sum(debts.values())},
        'hourly': [{'hour': hour, 'count': hour_counts[hour]} for hour in sorted(hours)],
        'hoursSource': 'plans' if schedules else 'unconfigured', 'inside': inside,
        'events': events[:10], 'attention': attention, 'devices': devices}
