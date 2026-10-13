from datetime import datetime, timezone as utc
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Istanbul')

def now(): return datetime.now(utc.utc)
def localtime(value=None): return (value or now()).astimezone(ZONE)
def localdate(value=None): return localtime(value).date()
def is_aware(value): return value.tzinfo is not None and value.utcoffset() is not None
def make_aware(value): return value.replace(tzinfo=ZONE)
