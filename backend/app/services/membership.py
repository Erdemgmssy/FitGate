from datetime import timedelta
from app import models as m
from app.core import time as timezone


def freeze_records(sub):
    return list(m.Freeze.objects.filter(subscription=sub).order_by('start', 'pk'))


def frozen_on(sub, day):
    records=freeze_records(sub)
    if any(row.start <= day and (row.end is None or day < row.end) for row in records):
        return True
    return sub.status == 'frozen' and not any(row.planned_end for row in records)


def status(sub, today=None):
    today=today or timezone.localdate()
    if not sub: return 'none'
    if sub.status == 'cancelled': return 'cancelled'
    if sub.start > today: return 'pending'
    if frozen_on(sub, today): return 'frozen'
    if sub.end is not None and sub.end < today: return 'expired'
    return 'active'


def remaining_days(sub, today=None):
    today=today or timezone.localdate()
    if sub.status == 'cancelled': return 0
    if sub.end is None: return None
    records=freeze_records(sub)
    legacy=next((row for row in records if row.end is None and row.planned_end is None and row.start<=today),None)
    first=max(sub.start, legacy.start if legacy else today)
    days=max(0,(sub.end-first).days+1)
    for row in records:
        if row.end:
            days-=max(0,(min(sub.end+timedelta(days=1),row.end)-max(first,row.start)).days)
    return max(0,days)


def subscriptions(member):
    return list(m.Subscription.objects.filter(member=member).order_by('end','start','created_at','pk'))


def member_frozen(member, day=None):
    day=day or timezone.localdate()
    return any(status(sub,day)=='frozen' for sub in subscriptions(member))


def current_sub(member, today=None):
    today=today or timezone.localdate()
    if not member or member_frozen(member,today): return None
    return next((sub for sub in subscriptions(member) if status(sub,today)=='active'),None)


def entry_sub(member, now):
    if not member or member_frozen(member,timezone.localdate(now)): return None
    candidates=[sub for sub in subscriptions(member) if status(sub,timezone.localdate(now))=='active']
    from .plans import entry_error
    eligible=[sub for sub in candidates if not entry_error(sub,now)]
    return next(iter(eligible or candidates),None)
