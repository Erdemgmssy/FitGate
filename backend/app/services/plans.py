"""Plan contracts and pricing use the existing Plan and sale snapshot models."""
import re
import uuid
from datetime import timedelta, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from app import models as m
from app.core import time as timezone
from .business import require, get, amount, integer, parse_day, RuleError
from .projection import wire


def available(plan, day=None):
    day=day or timezone.localdate()
    return plan.active and (not plan.sale_start or plan.sale_start<=day) and (not plan.sale_end or plan.sale_end>=day)


def campaign_price(plan, day=None):
    day=day or timezone.localdate(); base=amount(plan.price)
    campaigns=[row for row in plan.campaigns if row.get('active',True) and parse_day(row['start'])<=day<=parse_day(row['end'])]
    require(len(campaigns)<=1,'Aynı satışta birden fazla kampanya uygulanamaz.')
    campaign=campaigns[0] if campaigns else None
    discount=0
    if campaign:
        discount=amount(campaign['value']) if campaign['type']=='amount' else int((Decimal(base)*Decimal(str(campaign['value']))/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    require(discount<=base,'Kampanya indirimi satış fiyatını aşamaz.')
    return base-discount,discount,campaign


def save(p,user,branch):
    require(user is not None and user.role=='admin','Paket yönetimi için admin yetkisi gerekli.')
    obj=get(m.Plan,p['id'],branch) if p.get('id') else m.Plan(branch=branch)
    before=wire(obj) if p.get('id') else None
    if p.get('id'):
        require(p.get('confirmed') is True,'Paket fiyat/koşul değişikliğini onaylayın.')
        require(integer(p.get('revision'),1)==obj.revision,'Paket başka bir işlemde güncellendi; güncel paketi tekrar açın.')
    name=p.get('name',''); description=p.get('description','')
    require(isinstance(name,str) and 1<=len(name.strip())<=120 and isinstance(description,str) and len(description)<=600,'Paket adı/açıklaması geçersiz.')
    kind=p.get('kind','hybrid' if p.get('sessions') is not None else 'timed')
    require(kind in ['timed','sessions','hybrid'],'Paket türü geçersiz.')
    sessions=integer(p['sessions'],1) if p.get('sessions') not in [None,''] else None
    require((kind=='timed' and sessions is None) or (kind!='timed' and sessions is not None),'Süreli paket sınırsız, seanslı/karma paket pozitif seans hakkı içermeli.')
    unit=p.get('durationUnit','day'); require(unit in ['day','week','month','year'],'Süre birimi geçersiz.')
    value=0 if kind=='sessions' else integer(p.get('durationValue') or p.get('days'),1,{'day':3660,'week':520,'month':120,'year':10}[unit])
    require(kind!='sessions' or p.get('durationValue') in [None,'',0,'0'],'Saf seans paketinde süre belirlenemez.')
    price=amount(p.get('price')); first=p.get('from',''); last=p.get('to','')
    require(all(isinstance(v,str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v) for v in [first,last]) and first!=last,'Giriş saatleri geçersiz; başlangıç ve bitiş farklı olmalı.')
    weekdays=p.get('weekdays'); require(isinstance(weekdays,list) and weekdays and all(type(v) is int and 0<=v<=6 for v in weekdays) and len(set(weekdays))==len(weekdays),'Geçerli günler seçilmeli ve tekrarlanmamalı.')
    def optional(key): return integer(p[key],1) if p.get(key) not in [None,''] else None
    freeze=integer(p.get('freezeDays',0)); minimum=integer(p.get('freezeMin',1),1); maximum=optional('freezeMax'); limit=optional('freezeLimit')
    require(not freeze or minimum<=freeze and (maximum is None or minimum<=maximum<=freeze),'Dondurma alt/üst süreleri toplam hakla uyumlu olmalı.')
    require(freeze or maximum is None and limit is None,'Dondurma hakkı yokken ek dondurma sınırı tanımlanamaz.')
    sale_start=parse_day(p['saleStart']) if p.get('saleStart') else None; sale_end=parse_day(p['saleEnd']) if p.get('saleEnd') else None
    require(not sale_start or not sale_end or sale_start<=sale_end,'Satış tarih aralığı geçersiz.')
    campaigns=p.get('campaigns',[]); require(isinstance(campaigns,list) and len(campaigns)<=30,'En fazla 30 kampanya tanımlanabilir.')
    parsed=[]
    for row in campaigns:
        require(isinstance(row,dict) and isinstance(row.get('name'),str) and 1<=len(row['name'].strip())<=120,'Kampanya adı gerekli.')
        start=parse_day(row.get('start')); end=parse_day(row.get('end')); require(start<=end,'Kampanya tarihleri geçersiz.')
        require(row.get('type') in ['amount','percent'],'Kampanya indirim türü geçersiz.')
        cents=amount(row.get('value')); require(cents>0 and cents<=(price if row['type']=='amount' else 10000),'Kampanya tutarı/oranı geçersiz.')
        require(type(row.get('active',True)) is bool,'Kampanya aktif durumu geçersiz.')
        identifier=str(row.get('id') or uuid.uuid4());require(len(identifier)<=50,'Kampanya kimliği geçersiz.')
        parsed.append({'id':identifier,'name':row['name'].strip(),'type':row['type'],'value':str(Decimal(cents)/100),'start':start.isoformat(),'end':end.isoformat(),'active':row.get('active',True)})
    require(len({r['id'] for r in parsed})==len(parsed),'Kampanya kimlikleri tekrar edemez.')
    for index,row in enumerate(parsed):
        require(not any(row['active'] and other['active'] and row['start']<=other['end'] and other['start']<=row['end'] for other in parsed[index+1:]),'Aktif kampanya tarihleri çakışıyor.')
    require(type(p.get('active',True)) is bool,'Paket aktif durumu geçersiz.')
    values={'name':name.strip(),'description':description,'kind':kind,'duration_unit':unit,'duration_value':value,'days':value*{'day':1,'week':7,'month':30,'year':365}[unit],'sessions':sessions,'price':Decimal(price)/100,'allowed_from':first,'allowed_to':last,'weekdays':weekdays,'freeze_days':freeze,'freeze_min':minimum,'freeze_max':maximum,'freeze_limit':limit,'daily_limit':optional('dailyLimit'),'weekly_limit':optional('weeklyLimit'),'sale_start':sale_start,'sale_end':sale_end,'campaigns':parsed,'active':p.get('active',True),'revision':obj.revision+1 if p.get('id') else 1}
    for key,value in values.items():setattr(obj,key,value)
    lesson_types=p.get('lessonTypes',obj.lesson_types if p.get('id') else ['group'])
    require(isinstance(lesson_types,list) and all(isinstance(item,str) and item in ['group','private'] for item in lesson_types) and len(lesson_types)==len(set(lesson_types)),'Ders türleri geçersiz.')
    lesson_sessions=p.get('lessonSessions',obj.lesson_sessions if p.get('id') else None)
    lesson_sessions=integer(lesson_sessions,1) if lesson_sessions not in [None,''] else None
    require(lesson_types or lesson_sessions is None,'Ders türü olmadan ders hakkı tanımlanamaz.')
    obj.lesson_types=lesson_types;obj.lesson_sessions=lesson_sessions
    obj.save()
    m.Audit.objects.create(branch=branch,actor=user,type='savePlan',entity_id=str(obj.id),detail={'confirmed':p.get('confirmed',False),'revision':obj.revision},before=before,after=wire(obj))
    return {'id':str(obj.id)}


def entry_error(sub, now):
    rules=sub.rules; clock=timezone.localtime(now); current=clock.strftime('%H:%M')
    first=rules.get('from','00:00');last=rules.get('to','23:59')
    overnight=first>last
    day=clock.date()-timedelta(days=1) if overnight and current<last else clock.date()
    weekday=(day.weekday()+1)%7
    if weekday not in rules.get('weekdays',[]) or not ((current>=first or current<last) if overnight else first<=current<last): return 'Paket gün / saat kısıtlaması'
    if sub.remaining is not None and sub.remaining<=0:return 'Seans hakkı kalmadı'
    midnight=timezone.make_aware(datetime.combine(clock.date(),time.min))
    for key,start in [('dailyLimit',midnight),('weeklyLimit',midnight-timedelta(days=clock.weekday()))]:
        if rules.get(key):
            end=start+timedelta(days=1 if key=='dailyLimit' else 7)
            used=m.Passage.objects.filter(grant__subscription_id=sub.id,grant__direction='entry',grant__confirmed=True,device__simulated=False,occurred_at__gte=start,occurred_at__lt=end).count()
            used+=m.Visit.objects.filter(subscription_id=sub.id,entry_event_id__isnull=True,
                entry_actor_id__isnull=False,method__in=['MANUAL','ADMIN_CORRECTION'],entry__gte=start,entry__lt=end).count()
            if used>=rules[key]:return 'Günlük giriş limiti doldu' if key=='dailyLimit' else 'Haftalık giriş limiti doldu'
    return ''
