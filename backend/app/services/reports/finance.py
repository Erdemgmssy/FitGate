from sqlalchemy import select,func,literal,case,union_all,and_,or_,exists
from sqlalchemy.orm import aliased
from app import models as m
from .common import *

def invoice_scope(f):
    sale_sub=aliased(m.Subscription);lesson_sub=aliased(m.Subscription)
    q=select(m.Invoice.id.label('id'),m.Invoice.number.label('number'),m.Invoice.total_cents.label('amount'),m.Invoice.created_at.label('at'),m.Member.name.label('member'),case((m.Invoice.subscription_id.is_not(None),'membership'),else_='lesson').label('kind'))
    q=q.join(m.Member,m.Member.id==m.Invoice.member_id).outerjoin(sale_sub,sale_sub.id==m.Invoice.subscription_id).outerjoin(m.Booking,m.Booking.id==m.Invoice.booking_id).outerjoin(lesson_sub,lesson_sub.id==m.Booking.subscription_id)
    q=q.where(m.Invoice.branch_id==f.branch,m.Member.branch_id==f.branch)
    if f.plan:q=q.where(or_(sale_sub.plan_id==f.plan,lesson_sub.plan_id==f.plan))
    if f.category:q=q.where(literal(False))
    if f.actor is not None:q=q.where(or_(subscription_actor(sale_sub,f.actor,f.branch),m.Booking.actor_id==f.actor))
    elif f.employee is not None:q=q.where(literal(False))
    if f.type in ['membership','lesson','product']:q=q.where(m.Invoice.subscription_id.is_not(None) if f.type=='membership' else m.Invoice.booking_id.is_not(None) if f.type=='lesson' else literal(False))
    return q

def valid_invoice(cutoff):
    return or_(m.Invoice.status!='cancelled',exists(select(m.Audit.id).where(m.Audit.branch_id==m.Invoice.branch_id,m.Audit.type=='cancelInvoice',m.Audit.entity_id==cast(m.Invoice.id,String),m.Audit.at>=cutoff)))

def ledger(f):
    sub=aliased(m.Subscription);lesson_sub=aliased(m.Subscription)
    def membership_events(refund=False):
        event=m.Refund if refund else m.Payment
        actor=aliased(m.User)
        q=select(event.at.label('at'),m.Payment.number.label('number'),case((m.Invoice.subscription_id.is_not(None),'membership'),else_='lesson').label('kind'),literal('refund' if refund else 'collection').label('event'),func.coalesce(sub.plan_name,m.Invoice.description).label('subject'),m.Member.name.label('member'),m.Payment.method.label('method'),(-event.amount_cents if refund else event.amount_cents).label('amount'),actor.full_name.label('actor'))
        q=q.select_from(event)
        if refund:q=q.join(m.Payment,m.Payment.id==m.Refund.payment_id)
        q=q.join(m.Invoice,m.Invoice.id==m.Payment.invoice_id).join(m.Member,m.Member.id==m.Invoice.member_id).join(actor,actor.id==event.actor_id).outerjoin(sub,sub.id==m.Invoice.subscription_id).outerjoin(m.Booking,m.Booking.id==m.Invoice.booking_id).outerjoin(lesson_sub,lesson_sub.id==m.Booking.subscription_id)
        q=q.where(event.branch_id==f.branch,m.Payment.branch_id==f.branch,m.Invoice.branch_id==f.branch,f.range(event.at),actor_condition(event.actor_id,f))
        if f.plan:q=q.where(or_(sub.plan_id==f.plan,lesson_sub.plan_id==f.plan))
        if f.category:q=q.where(literal(False))
        return q
    member=aliased(m.Member);actor=aliased(m.User)
    sale=select(m.Sale.at.label('at'),m.Sale.number.label('number'),literal('product').label('kind'),literal('collection').label('event'),m.Sale.product_name.label('subject'),func.coalesce(member.name,'Misafir').label('member'),m.Sale.method.label('method'),m.Sale.total_cents.label('amount'),actor.full_name.label('actor')).select_from(m.Sale).join(m.Product,m.Product.id==m.Sale.product_id).join(actor,actor.id==m.Sale.actor_id).outerjoin(member,member.id==m.Sale.member_id).where(m.Sale.branch_id==f.branch,m.Product.branch_id==f.branch,f.range(m.Sale.at),actor_condition(m.Sale.actor_id,f))
    refunds=select(m.StockMovement.at.label('at'),m.Sale.number.label('number'),literal('product').label('kind'),literal('refund').label('event'),m.Sale.product_name.label('subject'),func.coalesce(member.name,'Misafir').label('member'),m.StockMovement.method.label('method'),(-m.StockMovement.refund_cents).label('amount'),func.coalesce(actor.full_name,'Eski kayıt: bilinmiyor').label('actor')).select_from(m.StockMovement).join(m.Sale,m.Sale.id==m.StockMovement.sale_id).join(m.Product,m.Product.id==m.Sale.product_id).outerjoin(actor,actor.id==m.StockMovement.actor_id).outerjoin(member,member.id==m.Sale.member_id).where(m.StockMovement.branch_id==f.branch,m.Sale.branch_id==f.branch,m.StockMovement.returned_units>0,f.range(m.StockMovement.at),actor_condition(m.StockMovement.actor_id,f))
    if f.plan:sale=sale.where(literal(False));refunds=refunds.where(literal(False))
    if f.category:sale=sale.where(m.Product.category==f.category);refunds=refunds.where(m.Product.category==f.category)
    u=union_all(membership_events(),membership_events(True),sale,refunds).subquery()
    q=select(u)
    if f.type in ['membership','lesson','product']:q=q.where(u.c.kind==f.type)
    if f.method:q=q.where(u.c.method==f.method)
    return q

def accrual(f):
    q=invoice_scope(f).where(f.range(m.Invoice.created_at),valid_invoice(f.end)).subquery()
    sale=select(m.Sale.at.label('at'),literal('product').label('kind'),m.Sale.total_cents.label('amount')).join(m.Product).where(m.Sale.branch_id==f.branch,f.range(m.Sale.at),actor_condition(m.Sale.actor_id,f))
    if f.plan or f.type in ['membership','lesson']:sale=sale.where(literal(False))
    if f.category:sale=sale.where(m.Product.category==f.category)
    return union_all(select(q.c.at,q.c.kind,q.c.amount),sale).subquery()

def debt_rows(f):
    paid=select(m.Payment.invoice_id.label('id'),func.sum(m.Payment.amount_cents).label('paid')).where(m.Payment.branch_id==f.branch,m.Payment.at<f.cutoff).group_by(m.Payment.invoice_id).subquery()
    refunded=select(m.Payment.invoice_id.label('id'),func.sum(m.Refund.amount_cents).label('refunded')).join(m.Payment,m.Payment.id==m.Refund.payment_id).where(m.Refund.branch_id==f.branch,m.Payment.branch_id==f.branch,m.Refund.at<f.cutoff).group_by(m.Payment.invoice_id).subquery()
    inv=invoice_scope(f).where(m.Invoice.created_at<f.cutoff,valid_invoice(f.cutoff)).subquery()
    net=func.coalesce(paid.c.paid,0)-func.coalesce(refunded.c.refunded,0)
    return select(inv.c.id,inv.c.number,inv.c.member,inv.c.kind,inv.c.amount,net.label('paid'),func.greatest(0,inv.c.amount-net).label('remaining')).outerjoin(paid,paid.c.id==inv.c.id).outerjoin(refunded,refunded.c.id==inv.c.id).subquery()

def financial(f,export=False):
    require(f.type in ['', 'membership','lesson','product','debt','overdue'],'Finans işlem türü geçersiz.')
    event=ledger(f).subquery();d=debt_rows(f);a=accrual(f)
    value=rows(select(func.coalesce(func.sum(case((event.c.amount>=0,event.c.amount),else_=0)),0),-func.coalesce(func.sum(case((event.c.amount<0,event.c.amount),else_=0)),0)))[0]
    gross,refund=int(value[0]),int(value[1]);sales=int(scalar(select(func.coalesce(func.sum(a.c.amount),0))) or 0)
    part=select(m.Installment.invoice_id.label('id'),m.Installment.due.label('due'),m.Installment.amount_cents.label('amount'),func.sum(m.Installment.amount_cents).over(partition_by=m.Installment.invoice_id,order_by=[m.Installment.due,m.Installment.id]).label('cumulative')).where(m.Installment.branch_id==f.branch,m.Installment.archived.is_(False)).subquery()
    overdue=func.greatest(0,func.least(part.c.amount,part.c.cumulative-d.c.paid))
    overdue_query=select(part.c.due,d.c.number,d.c.member,overdue.label('remaining')).join(d,d.c.id==part.c.id).where(part.c.due<tz.localdate(f.cutoff),d.c.remaining>0)
    o=overdue_query.subquery();late=int(scalar(select(func.coalesce(func.sum(o.c.remaining),0))) or 0)
    remaining=int(scalar(select(func.coalesce(func.sum(d.c.remaining),0))) or 0)
    previous=ledger(f.previous()).subquery();old=int(scalar(select(func.coalesce(func.sum(previous.c.amount),0))) or 0)
    metrics=[metric('accrued','Tahakkuk eden satış',None if f.method else sales,'money'),metric('gross','Gerçek tahsilat',gross,'money'),metric('refund','İade',refund,'money'),metric('net','Net tahsilat',gross-refund,'money'),metric('remaining','Kalan alacak',None if f.method else remaining,'money','asof'),metric('overdue','Gecikmiş taksit',None if f.method else late,'money','asof'),metric('previous','Önceki dönem net',old,'money','previous'),metric('change','Önceki döneme göre',None if old==0 else (gross-refund-old)*100/abs(old),'percent')]
    charts=[chart('Net tahsilat',points(select(bucket(event.c.at,f),func.sum(event.c.amount)).group_by(bucket(event.c.at,f)).order_by(bucket(event.c.at,f)),filterKey='date'),'line','money'),chart('Ödeme yöntemleri',points(select(event.c.method,func.sum(event.c.amount)).group_by(event.c.method),filterKey='method'),'distribution','money'),chart('Gelir kaynakları',points(select(event.c.kind,func.sum(event.c.amount)).group_by(event.c.kind),filterKey='type'),'bar','money'),chart('Personel bazında net tahsilat',points(select(event.c.actor,func.sum(event.c.amount)).group_by(event.c.actor)),'bar','money')]
    if f.type=='debt':
        query=select(d.c.number,d.c.member,d.c.kind,d.c.amount,d.c.paid,d.c.remaining).where(d.c.remaining>0).order_by(d.c.remaining.desc(),d.c.number)
        columns=[('Satış no','text'),('Üye','text'),('Kaynak','text'),('Satış tutarı','money'),('Net tahsilat','money'),('Kalan','money')]
        metrics=[metric('remaining','Kalan alacak',remaining,'money','asof'),metric('overdue','Gecikmiş taksit',late,'money','asof')]
        charts=[chart('Kaynağa göre açık alacak',points(select(d.c.kind,func.sum(d.c.remaining)).where(d.c.remaining>0).group_by(d.c.kind)),'bar','money')]
    elif f.type=='overdue':
        query=overdue_query.where(overdue>0).order_by(part.c.due,d.c.number);columns=[('Vade','date'),('Satış no','text'),('Üye','text'),('Gecikmiş tutar','money')]
        metrics=[metric('overdue','Gecikmiş taksit',late,'money','asof')]
        charts=[chart('Vadesine göre gecikmiş alacak',points(select(o.c.due,func.sum(o.c.remaining)).where(o.c.remaining>0).group_by(o.c.due).order_by(o.c.due)),'bar','money')]
    else:
        query=select(event.c.number,event.c.kind,event.c.event,event.c.subject,event.c.member,event.c.at,event.c.method,event.c.amount,event.c.actor).order_by(event.c.at.desc(),event.c.number)
        columns=[('İşlem no','text'),('Kaynak','text'),('İşlem','text'),('Paket / ürün / ders','text'),('Müşteri','text'),('Tarih','datetime'),('Yöntem','text'),('Tutar','money'),('Personel','text')]
    return result(f,metrics,charts,query,columns,['Tahakkuk satış tarihine, tahsilat ve iade kendi işlem tarihine göre hesaplanır. Ürün satışı tek kez tahsilat olarak sayılır.','Alacak ve gecikmiş taksit, dönem sonunda kaydedilmiş satışların toplam bakiye durumudur; tahsilatı yapan kişi değil satışın bilinen işlem personeliyle filtrelenir.','Ödeme yöntemi seçiliyken tahakkuk gösterilmez: henüz tahsil edilmemiş satışın ödeme yöntemi yoktur. Gider kaydı olmadığı için net kâr hesaplanmaz.'],export)
