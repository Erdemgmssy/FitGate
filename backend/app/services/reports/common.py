"""Read-only report filters and SQL pagination; no business state is mutated."""
from dataclasses import dataclass
from datetime import datetime,time,timedelta,date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select,func,cast,String,literal,literal_column,and_,or_,exists,Interval
from sqlalchemy.orm import aliased
from app import models as m
from app.db.session import get_session
from app.core import time as tz
from app.services.business import require,parse_day,integer,RuleError

TABS={'overview':'Genel özet','finance':'Finans','members':'Üyelikler','visits':'Ziyaretler','classes':'Dersler','personnel':'Personel ve mesai','stock':'Stok ve satış','devices':'Cihazlar','audit':'Denetim günlüğü'}

@dataclass
class Filters:
    branch:UUID
    first:date
    last:date
    start:datetime
    end:datetime
    now:datetime
    tab:str
    page:int=1
    size:int=50
    actor:int|None=None
    employee:UUID|None=None
    plan:UUID|None=None
    category:str=''
    type:str=''
    method:str=''
    hour:int|None=None
    weekday:int|None=None
    granularity:str='day'

    @property
    def cutoff(self):return min(self.end,self.now)
    def range(self,column):return and_(column>=self.start,column<self.end)
    def previous(self):
        from dataclasses import replace
        days=(self.last-self.first).days+1
        return replace(self,first=self.first-timedelta(days=days),last=self.first-timedelta(days=1),start=self.start-timedelta(days=days),end=self.start)

def midnight(day):return tz.make_aware(datetime.combine(day,time.min))
def filters(user,p):
    require(user.role=='admin' or p.get('tab')=='personnel','Bu rapor için admin yetkisi gerekli.')
    tab=p.get('tab','overview');require(tab in TABS,'Rapor türü geçersiz.')
    require(p.get('branch',str(user.branch_id))==str(user.branch_id),'Başka şubenin raporuna erişilemez.')
    today=tz.localdate();first=parse_day(p.get('from') or today.replace(day=1).isoformat());last=parse_day(p.get('to') or today.isoformat())
    require(1900<=first.year<=last.year<=9998 and first<=last and (last-first).days<366,'Rapor tarih aralığı en fazla 366 gün olmalı.')
    f=Filters(user.branch_id,first,last,midnight(first),midnight(last+timedelta(days=1)),tz.now(),tab,integer(p.get('page',1),1,100000),integer(p.get('pageSize',50),1,200))
    f.type=p.get('type','');f.method=p.get('method','');require(len(f.type)<=60 and f.method in ['', 'cash','pos','bank','mixed'],'İşlem/yöntem filtresi geçersiz.')
    f.granularity=p.get('granularity','day');require(f.granularity in ['day','week','month'],'Grafik dönemi geçersiz.')
    if p.get('planId'):
        try:f.plan=UUID(p['planId'])
        except (ValueError,TypeError):raise RuleError('Paket filtresi geçersiz.')
        require(scalar(select(func.count()).select_from(m.Plan).where(m.Plan.id==f.plan,m.Plan.branch_id==f.branch))==1,'Paket bu şubeye ait değil.')
    f.category=p.get('category','');require(isinstance(f.category,str) and len(f.category)<=80,'Kategori geçersiz.')
    person=p.get('person','')
    if person:
        try:
            kind,value=person.split(':',1)
            if kind=='u':
                f.actor=int(value);row=get_session().scalar(select(m.User).where(m.User.id==f.actor,m.User.branch_id==f.branch));require(row,'Personel bu şubeye ait değil.')
                f.employee=get_session().scalar(select(m.Employee.id).where(m.Employee.user_id==f.actor,m.Employee.branch_id==f.branch))
            else:
                require(kind=='e','Personel filtresi geçersiz.');f.employee=UUID(value);row=get_session().scalar(select(m.Employee).where(m.Employee.id==f.employee,m.Employee.branch_id==f.branch));require(row,'Personel bu şubeye ait değil.');f.actor=row.user_id
        except (ValueError,TypeError):raise RuleError('Personel filtresi geçersiz.')
    if user.role!='admin':
        own=get_session().scalar(select(m.Employee.id).where(m.Employee.user_id==user.id,m.Employee.branch_id==f.branch))
        require(own and (not f.employee or f.employee==own) and (not f.actor or f.actor==user.id),'Yalnızca kendi mesai raporunuza erişebilirsiniz.')
        f.actor=user.id;f.employee=own
    if p.get('hour') not in [None,'']:f.hour=integer(p['hour'],0,23)
    if p.get('weekday') not in [None,'']:f.weekday=integer(p['weekday'],0,6)
    require(not f.plan or tab in ['overview','finance','members','visits','classes'],'Bu raporda paket filtresi kullanılamaz.')
    require(not f.category or tab in ['overview','finance','stock'],'Bu raporda kategori filtresi kullanılamaz.')
    require(not f.method or tab in ['overview','finance','stock'],'Bu raporda ödeme yöntemi kullanılamaz.')
    require((f.hour is None and f.weekday is None) or tab=='visits','Saat/gün filtresi yalnızca ziyaret raporunda kullanılır.')
    require(not f.method or f.type not in ['debt','overdue','movements','critical','empty'],'Bu işlem türü ödeme yöntemine göre filtrelenemez.')
    return f

def scalar(query):return get_session().scalar(query)
def rows(query):return get_session().execute(query).all()
def count(query):return int(scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
def interval(**values):return literal(timedelta(**values),type_=Interval)
def local(column):return func.timezone(literal_column("'Europe/Istanbul'"),column)
def bucket(column,f):return func.date_trunc(literal_column({'day':"'day'",'week':"'week'",'month':"'month'"}[f.granularity]),local(column))
def metric(key,label,value,format='count',scope='period'):
    return {'key':key,'label':label,'value':float(value) if isinstance(value,Decimal) else value,'format':format,'scope':scope}
def chart(title,points,type='bar',format='count'):
    return {'title':title,'type':type,'format':format,'points':points}
def points(query,label=0,value=1,filterKey=None):
    result=[]
    for row in rows(query):
        value_label=row[label]
        key=(tz.localdate(value_label).isoformat() if value_label.tzinfo else value_label.date().isoformat()) if isinstance(value_label,datetime) else value_label.isoformat() if isinstance(value_label,date) else str(value_label if value_label is not None else 'Bilinmiyor')
        result.append({'label':key,'value':float(row[value] or 0),'filter':{filterKey:key} if filterKey else None})
    return result

PRIVATE={'password','token','photo','image','email','phone','birthDate','birth_date','emergency','emergencyPhone','emergency_phone','address','normalized_phone','secret','token_hash','note','health','health_status','uid'}
def safe_detail(value):
    if isinstance(value,dict):return {k:safe_detail(v) for k,v in value.items() if k not in PRIVATE and not any(secret in k.lower() for secret in ['password','token','secret','api_key','device_key'])}
    if isinstance(value,list):return [safe_detail(v) for v in value]
    return value
def cell(value):
    if isinstance(value,datetime):return value.isoformat()
    if isinstance(value,date):return value.isoformat()
    if isinstance(value,UUID):return str(value)
    if isinstance(value,Decimal):return float(value)
    if isinstance(value,dict):
        import json
        return json.dumps(safe_detail(value),ensure_ascii=False)
    return value
def table(query,columns,f,export=False):
    amount=count(query)
    if export:require(amount<=50000,'Dışa aktarma en fazla 50.000 satır destekler; tarih aralığını daraltın.')
    limited=query if export else query.limit(f.size).offset((f.page-1)*f.size)
    return {'columns':[{'label':label,'format':format} for label,format in columns],'rows':[[cell(value) for value in row] for row in rows(limited)],'count':amount,'page':f.page,'pageSize':f.size}
def result(f,metrics,charts,query,columns,definitions=(),export=False):
    return {'title':TABS[f.tab],'metrics':metrics,'charts':charts,'table':table(query,columns,f,export),'definitions':list(definitions)}

def subscription_actor(sub,actor,branch):
    return exists(select(m.Audit.id).where(m.Audit.branch_id==branch,m.Audit.actor_id==actor,or_(and_(m.Audit.type=='renew',m.Audit.entity_id==cast(sub.id,String)),and_(m.Audit.type=='addMember',m.Audit.entity_id==cast(sub.member_id,String),m.Audit.at>=sub.created_at,m.Audit.at<=sub.created_at+interval(minutes=1)))))

def actor_condition(column,f):
    return column==f.actor if f.actor is not None else literal(False) if f.employee is not None else literal(True)

def options(user):
    branch=user.branch
    people=[{'id':'u:'+str(r.id),'name':r.full_name or r.username} for r in get_session().scalars(select(m.User).where(m.User.branch_id==user.branch_id)).all()] if user.role=='admin' else []
    if user.role=='admin':people+=[{'id':'e:'+str(r.id),'name':r.name} for r in get_session().scalars(select(m.Employee).where(m.Employee.branch_id==user.branch_id,m.Employee.user_id.is_(None))).all()]
    return {'branches':[{'id':str(branch.id),'name':branch.name}],'people':people,'plans':[{'id':str(r.id),'name':r.name} for r in get_session().scalars(select(m.Plan).where(m.Plan.branch_id==user.branch_id)).all()] if user.role=='admin' else [],'categories':[row[0] for row in rows(select(m.Product.category).where(m.Product.branch_id==user.branch_id,m.Product.category!='').distinct())] if user.role=='admin' else [],'tabs':TABS if user.role=='admin' else {'personnel':TABS['personnel']}}
