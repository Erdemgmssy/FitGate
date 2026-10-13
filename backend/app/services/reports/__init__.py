from datetime import timedelta
from sqlalchemy import select,func,literal,case,union_all,exists
from sqlalchemy.orm import aliased
from app import models as m
from .common import *
from .finance import financial,ledger,debt_rows
from .analysis import memberships,lessons,stock,sub_status
from .operations import visits,personnel,devices,audit,physical,visit_density

def overview(f,export=False):
    require(f.type=='','Genel özette işlem türü seçmeyin; ilgili rapor sekmesini kullanın.')
    e=ledger(f).subquery();d=debt_rows(f)
    sums=rows(select(func.coalesce(func.sum(case((e.c.amount>=0,e.c.amount),else_=0)),0),-func.coalesce(func.sum(case((e.c.amount<0,e.c.amount),else_=0)),0)))[0]
    labels={key:sub_status(m.Subscription,min(f.last,tz.localdate()),f.cutoff)==key for key in ['active','expired','frozen','cancelled','pending']}
    eligible=[m.Subscription.branch_id==f.branch,m.Subscription.member_id==m.Member.id,m.Subscription.created_at<f.cutoff,labels['active']]
    if f.plan:eligible.append(m.Subscription.plan_id==f.plan)
    members_base=[m.Member.branch_id==f.branch,actor_condition(m.Member.created_by_id,f)]
    if f.category:members_base.append(literal(False))
    if f.plan:members_base.append(exists(select(m.Subscription.id).where(m.Subscription.member_id==m.Member.id,m.Subscription.plan_id==f.plan,m.Subscription.created_at<f.cutoff)))
    active=int(scalar(select(func.count()).select_from(m.Member).where(*members_base,m.Member.active.is_(True),exists(select(m.Subscription.id).where(*eligible)))) or 0)
    new=select(m.Member.created_at.label('at')).where(*members_base,f.range(m.Member.created_at)).subquery()
    older=aliased(m.Subscription)
    renew_conditions=[m.Subscription.branch_id==f.branch,f.range(m.Subscription.created_at),exists(select(older.id).where(older.member_id==m.Subscription.member_id,older.branch_id==f.branch,older.created_at<m.Subscription.created_at))]
    if f.plan:renew_conditions.append(m.Subscription.plan_id==f.plan)
    if f.actor is not None:renew_conditions.append(subscription_actor(m.Subscription,f.actor,f.branch))
    if f.category or f.employee and f.actor is None:renew_conditions.append(literal(False))
    renewed=int(scalar(select(func.count()).select_from(m.Subscription).where(*renew_conditions)) or 0)
    booking=select(m.Booking.at.label('at')).join(m.ClassSession,m.ClassSession.id==m.Booking.class_session_id).where(m.Booking.branch_id==f.branch,f.range(m.Booking.at))
    if f.employee:booking=booking.where(m.ClassSession.trainer_id==f.employee)
    elif f.actor is not None:booking=booking.where(m.Booking.actor_id==f.actor)
    if f.plan:booking=booking.join(m.Subscription,m.Subscription.id==m.Booking.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.category:booking=booking.where(literal(False))
    b=booking.subquery()
    pv=physical(f).where(m.Grant.direction=='entry')
    has_person=f.actor is not None or f.employee is not None
    if has_person or f.category:pv=pv.where(literal(False))
    p=pv.subquery()
    series=union_all(select(e.c.at,case((e.c.amount>=0,e.c.amount),else_=0).label('gross'),case((e.c.amount<0,-e.c.amount),else_=0).label('refund'),literal(0).label('entries'),literal(0).label('new'),literal(0).label('bookings')),select(p.c.at,literal(0),literal(0),literal(1),literal(0),literal(0)),select(new.c.at,literal(0),literal(0),literal(0),literal(1),literal(0)),select(b.c.at,literal(0),literal(0),literal(0),literal(0),literal(1))).subquery()
    group=bucket(series.c.at,f)
    daily=select(group.label('day'),func.sum(series.c.gross).label('gross'),func.sum(series.c.refund).label('refund'),func.sum(series.c.gross-series.c.refund).label('net'),func.sum(series.c.entries).label('entries'),func.sum(series.c.new).label('new'),func.sum(series.c.bookings).label('bookings')).group_by(group).order_by(group)
    def receipts(first):return int(scalar(select(func.coalesce(func.sum(case((e.c.amount>=0,e.c.amount),else_=0)),0)).where(e.c.at>=max(first,f.start))) or 0)
    density=visit_density(f) if not has_person and not f.category and not f.method else None
    products_net=int(scalar(select(func.coalesce(func.sum(e.c.amount),0)).where(e.c.kind=='product')) or 0)
    critical=select(func.count()).select_from(m.Product).where(m.Product.branch_id==f.branch,m.Product.active.is_(True),m.Product.stock>0,m.Product.stock<=m.Product.minimum)
    if f.category:critical=critical.where(m.Product.category==f.category)
    metrics=[metric('day','Son gün tahsilatı',receipts(midnight(f.last)),'money','lastDay'),metric('week','Son 7 gün tahsilatı',receipts(f.end-timedelta(days=7)),'money','lastWeek'),metric('month','Son ay tahsilatı',receipts(midnight(f.last.replace(day=1))),'money','lastMonth'),metric('net','Dönem net tahsilatı',int(sums[0]-sums[1]),'money'),metric('debt','Kalan toplam alacak',None if f.method else int(scalar(select(func.coalesce(func.sum(d.c.remaining),0))) or 0),'money','asof'),metric('active','Aktif üye',active,'count','asof'),metric('new','Yeni üye',count(select(new))),metric('renew','Yenilenen üyelik',renewed),metric('entry','Fiziksel giriş',None if has_person or f.category else count(pv)),metric('density','Ortalama içeride',density,'decimal'),metric('product','Net ürün satışı',products_net,'money'),metric('booking','Yeni ders rezervasyonu',count(booking)),metric('critical','Kritik stok',None if has_person else int(scalar(critical) or 0),'count','current')]
    metrics.append(metric('dayEntry','Son gün fiziksel giriş',None if has_person or f.category or f.method else count(select(p).where(p.c.at>=midnight(f.last))),'count','lastDay'))
    unavailable=set()
    if f.category:unavailable.update(['active','new','renew','booking'])
    if f.plan:unavailable.update(['product','critical'])
    if f.method:unavailable.update(['active','new','renew','booking','critical','entry'])
    for item in metrics:
        if item['key'] in unavailable:item['value']=None
    daily_sub=daily.subquery()
    charts=[chart('Tahsilat ve iadeler sonrası net',points(select(daily_sub.c.day,daily_sub.c.net).order_by(daily_sub.c.day),filterKey='date'),'line','money'),chart('Giriş ve üyelik hareketi',points(select(daily_sub.c.day,daily_sub.c.entries).order_by(daily_sub.c.day),filterKey='date'),'bar')]
    return result(f,metrics,charts,daily,[('Dönem','date'),('Tahsilat','money'),('İade','money'),('Net','money'),('Fiziksel giriş','count'),('Yeni üye','count'),('Yeni rezervasyon','count')],['Son gün / 7 gün / ay tahsilatı seçili tarih aralığıyla kesişen dönemdir; iadeler dönem net tutarında ayrıca düşülür.','Alacak ve aktif üyeler dönem sonuna, kritik stok mevcut stok kaydına göre gösterilir. Personel filtresinde personele atanamayan salon doluluğu/giriş ve stok bakiyesi gösterilmez.','Yeni üye kayıt tarihi, yeni rezervasyon oluşturulma tarihi ve üyelik satış tarihi ayrı kaynaklardır. Raporlar salt okunurdur.'],export)

BUILDERS={'overview':overview,'finance':financial,'members':memberships,'visits':visits,'classes':lessons,'personnel':personnel,'stock':stock,'devices':devices,'audit':audit}

def build(user,p,export=False):
    f=filters(user,p)
    data=BUILDERS[f.tab](f,export)
    data['context']={'branchId':str(f.branch),'branchName':user.branch.name,'from':f.first.isoformat(),'to':f.last.isoformat(),'timezone':'Europe/Istanbul','generatedAt':f.now.isoformat(),'asOf':f.cutoff.isoformat(),'filters':dict(p)}
    return data
