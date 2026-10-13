from sqlalchemy import select,func,case,literal,and_,or_,exists,union_all,cast,String
from sqlalchemy.orm import aliased
from app import models as m
from .common import *

def sub_status(sub,day,cutoff=None):
    freeze=exists(select(m.Freeze.id).where(m.Freeze.subscription_id==sub.id,m.Freeze.branch_id==sub.branch_id,m.Freeze.start<=day,or_(m.Freeze.end.is_(None),m.Freeze.end>day)))
    legacy=and_(sub.status=='frozen',~exists(select(m.Freeze.id).where(m.Freeze.subscription_id==sub.id,m.Freeze.planned_end.is_not(None))))
    cancelled=sub.status=='cancelled'
    if cutoff is not None:cancelled=and_(cancelled,~exists(select(m.Audit.id).where(m.Audit.branch_id==sub.branch_id,m.Audit.type=='cancelSubscription',m.Audit.entity_id==cast(sub.id,String),m.Audit.at>=cutoff)))
    return case((cancelled,'cancelled'),(sub.start>day,'pending'),(or_(freeze,legacy),'frozen'),(and_(sub.end.is_not(None),sub.end<day),'expired'),else_='active')

def memberships(f,export=False):
    require(f.type in ['', 'active','expired','frozen','cancelled','pending','renewal'],'Üyelik durum filtresi geçersiz.')
    status=sub_status(m.Subscription,min(f.last,tz.localdate()),f.cutoff)
    older=aliased(m.Subscription)
    renewed=exists(select(older.id).where(older.branch_id==f.branch,older.member_id==m.Subscription.member_id,or_(older.created_at<m.Subscription.created_at,and_(older.created_at==m.Subscription.created_at,cast(older.id,String)<cast(m.Subscription.id,String)))))
    base=[m.Subscription.branch_id==f.branch,m.Subscription.created_at<f.cutoff]
    if f.plan:base.append(m.Subscription.plan_id==f.plan)
    if f.actor is not None:base.append(subscription_actor(m.Subscription,f.actor,f.branch))
    elif f.employee is not None:base.append(literal(False))
    if f.type and f.type!='renewal':base.append(status==f.type)
    if f.type=='renewal':base.append(renewed)
    asof=select(m.Subscription.id.label('id'),m.Subscription.member_id.label('member'),status.label('state')).where(*base).subquery()
    counts={row[0]:int(row[1]) for row in rows(select(asof.c.state,func.count()).group_by(asof.c.state))}
    current=select(func.count(func.distinct(m.Member.id))).join(m.Subscription,m.Subscription.member_id==m.Member.id).where(*base,m.Member.active.is_(True),status=='active')
    new=select(func.count()).select_from(m.Member).where(m.Member.branch_id==f.branch,f.range(m.Member.created_at),actor_condition(m.Member.created_by_id,f))
    if f.plan:new=new.where(exists(select(m.Subscription.id).where(m.Subscription.member_id==m.Member.id,m.Subscription.plan_id==f.plan,m.Subscription.created_at<f.cutoff)))
    if f.type:new=new.where(exists(select(m.Subscription.id).where(*base,m.Subscription.member_id==m.Member.id)))
    sold=select(func.count()).select_from(m.Subscription).where(*base,f.range(m.Subscription.created_at))
    renew=select(func.count()).select_from(m.Subscription).where(*base,f.range(m.Subscription.created_at),renewed)
    expiry=[*base,m.Subscription.end>=f.first,m.Subscription.end<=f.last,m.Subscription.status!='cancelled']
    newer=aliased(m.Subscription)
    replacement=exists(select(newer.id).where(newer.branch_id==f.branch,newer.member_id==m.Subscription.member_id,newer.status!='cancelled',newer.created_at>m.Subscription.created_at,newer.created_at<f.cutoff,newer.start>m.Subscription.end))
    denominator=int(scalar(select(func.count(func.distinct(m.Subscription.member_id))).where(*expiry)) or 0)
    numerator=int(scalar(select(func.count(func.distinct(m.Subscription.member_id))).where(*expiry,replacement)) or 0)
    remaining=int(scalar(select(func.coalesce(func.sum(m.Subscription.remaining),0)).where(*base,status=='active')) or 0)
    used=select(func.count()).select_from(m.Passage).join(m.Grant,m.Grant.id==m.Passage.grant_id).join(m.Device,m.Device.id==m.Passage.device_id).join(m.Subscription,m.Subscription.id==m.Grant.subscription_id).where(m.Passage.branch_id==f.branch,m.Grant.confirmed.is_(True),m.Grant.direction=='entry',m.Device.simulated.is_(False),m.Subscription.total_sessions.is_not(None),f.range(m.Passage.occurred_at),*base)
    metrics=[metric('active','Aktif üye',int(scalar(current) or 0),'count','asof'),metric('new','Yeni üye kaydı',int(scalar(new) or 0)),metric('sold','Yeni üyelik satışı',int(scalar(sold) or 0)),metric('renew','Yenilenen üyelik',int(scalar(renew) or 0)),metric('expired','Süresi dolmuş üyelik',counts.get('expired',0),'count','asof'),metric('frozen','Dondurulmuş üyelik',counts.get('frozen',0),'count','asof'),metric('cancelled','İptal üyelik',counts.get('cancelled',0),'count','asof'),metric('renewRate','Yenileme oranı',numerator*100/denominator if denominator else None,'percent'),metric('used','Kullanılan giriş seansı',int(scalar(used) or 0)),metric('remaining','Mevcut kalan seans',remaining,'count','current')]
    kind=func.coalesce(m.Subscription.rules['kind'].as_string(),case((m.Subscription.total_sessions.is_(None),'timed'),else_='hybrid'))
    charts=[chart('En çok satılan paketler',points(select(m.Subscription.plan_name,func.count()).where(*base,f.range(m.Subscription.created_at)).group_by(m.Subscription.plan_name).order_by(func.count().desc()).limit(12)),'bar'),chart('Satış anındaki paket türleri',points(select(kind,func.count()).where(*base,f.range(m.Subscription.created_at)).group_by(kind)),'distribution'),chart('Üyelik durumları',[{'label':key,'value':value,'filter':{'type':key}} for key,value in counts.items()],'distribution')]
    invoice=aliased(m.Invoice)
    query=select(m.Member.number,m.Member.name,m.Subscription.plan_name,status,m.Subscription.start,m.Subscription.end,m.Subscription.created_at,invoice.total_cents,m.Subscription.total_sessions,m.Subscription.remaining).join(m.Member,m.Member.id==m.Subscription.member_id).outerjoin(invoice,invoice.subscription_id==m.Subscription.id).where(*base,f.range(m.Subscription.created_at) if not f.type else literal(True)).order_by(m.Subscription.created_at.desc(),m.Subscription.id)
    return result(f,metrics,charts,query,[('Üye no','text'),('Üye','text'),('Paket (satış anı)','text'),('Durum','text'),('Başlangıç','date'),('Bitiş','date'),('Satış tarihi','datetime'),('Satış tutarı','money'),('Toplam seans','count'),('Mevcut kalan seans','count')],['Yeni üye kayıt tarihi ile üyelik satın alma tarihi farklı metriklerdir. Durumlar dönem sonuna, kalan seans mevcut kayıtlı bakiyeye göre gösterilir.','Yenileme oranı: dönemde biten üyeliği olan üyelerden, dönem sonuna kadar sonraki başlangıç tarihli bir üyelik satın alanların oranı. Payda sıfırsa oran yoktur.','Satış personeli geçmiş denetim kayıtlarından doğrulanır; kayıt bulunmayan eski satışlar personel filtresine dahil edilmez. Geçmiş paket adı/fiyatı/türü korunur.'],export)

def lessons(f,export=False):
    require(f.type in ['', 'group','private','booked','waiting','attended','late','absent','cancelled','excused'],'Ders filtresi geçersiz.')
    base=[m.ClassSession.branch_id==f.branch,f.range(m.ClassSession.at)]
    if f.employee:base.append(m.ClassSession.trainer_id==f.employee)
    elif f.actor is not None:base.append(literal(False))
    if f.type in ['group','private']:base.append(m.ClassSession.kind==f.type)
    if f.type not in ['', 'group','private']:base.append(exists(select(m.Booking.id).where(m.Booking.branch_id==f.branch,m.Booking.class_session_id==m.ClassSession.id,m.Booking.status==f.type).correlate(m.ClassSession)))
    if f.plan:base.append(exists(select(m.Booking.id).join(m.Subscription,m.Subscription.id==m.Booking.subscription_id).where(m.Booking.class_session_id==m.ClassSession.id,m.Subscription.plan_id==f.plan).correlate(m.ClassSession)))
    bookings=select(m.Booking.id.label('id'),m.Booking.status.label('status'),m.Booking.class_session_id.label('class')).join(m.ClassSession,m.ClassSession.id==m.Booking.class_session_id).where(*base,m.Booking.branch_id==f.branch)
    if f.plan:bookings=bookings.join(m.Subscription,m.Subscription.id==m.Booking.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.type not in ['', 'group','private']:bookings=bookings.where(m.Booking.status==f.type)
    b=bookings.subquery();counts={r[0]:int(r[1]) for r in rows(select(b.c.status,func.count()).group_by(b.c.status))}
    attended=counts.get('attended',0)+counts.get('late',0);absent=counts.get('absent',0);denominator=attended+absent
    capacity=int(scalar(select(func.coalesce(func.sum(m.ClassSession.capacity),0)).where(*base,m.ClassSession.cancelled.is_(False),m.ClassSession.outcome!='notheld')) or 0)
    occupied=sum(counts.get(key,0) for key in ['booked','attended','late','absent'])
    metrics=[metric('classes','Ders sayısı',int(scalar(select(func.count()).select_from(m.ClassSession).where(*base)) or 0)),metric('bookings','Rezervasyon kaydı',count(bookings)),metric('attended','Gerçek katılım',attended),metric('absent','Gelmedi',absent),metric('waiting','Bekleme listesi',counts.get('waiting',0)),metric('cancel','İptal / mazeret',counts.get('cancelled',0)+counts.get('excused',0)),metric('occupancy','Kontenjan doluluğu',occupied*100/capacity if capacity else None,'percent'),metric('attendanceRate','Kayıtlı yoklamada katılım',attended*100/denominator if denominator else None,'percent'),metric('noShowRate','Kayıtlı yoklamada gelmeme',absent*100/denominator if denominator else None,'percent')]
    from .finance import valid_invoice
    invoices=select(m.Invoice.id).where(m.Invoice.branch_id==f.branch,m.Invoice.booking_id.in_(select(b.c.id)))
    lesson_sales=scalar(select(func.coalesce(func.sum(m.Invoice.total_cents),0)).where(m.Invoice.id.in_(invoices),valid_invoice(f.cutoff),f.range(m.Invoice.created_at)))
    collections=scalar(select(func.coalesce(func.sum(m.Payment.amount_cents),0)).where(m.Payment.branch_id==f.branch,m.Payment.invoice_id.in_(invoices),f.range(m.Payment.at)))
    refunds=scalar(select(func.coalesce(func.sum(m.Refund.amount_cents),0)).join(m.Payment,m.Payment.id==m.Refund.payment_id).where(m.Refund.branch_id==f.branch,m.Payment.invoice_id.in_(invoices),f.range(m.Refund.at)))
    metrics+=[metric('lessonSales','Seçili derslerin dönem satışı',int(lesson_sales or 0),'money'),metric('lessonCollections','Seçili derslerin net tahsilatı',int(collections or 0)-int(refunds or 0),'money'),metric('lessonRefunds','Seçili derslerin dönem iadesi',int(refunds or 0),'money')]
    charts=[chart('Ders takvimi',points(select(bucket(m.ClassSession.at,f),func.count()).where(*base).group_by(bucket(m.ClassSession.at,f)).order_by(bucket(m.ClassSession.at,f)),filterKey='date'),'bar'),chart('Antrenör başına ders',points(select(m.ClassSession.trainer,func.count()).where(*base).group_by(m.ClassSession.trainer)),'bar'),chart('Katılım / rezervasyon durumları',[{'label':k,'value':v,'filter':{'type':k}} for k,v in counts.items()],'distribution'),chart('En çok tercih edilen dersler',points(select(m.ClassSession.name,func.count(b.c.id)).join(b,b.c['class']==m.ClassSession.id).where(*base).group_by(m.ClassSession.name).order_by(func.count(b.c.id).desc()).limit(12)),'bar')]
    query=select(m.ClassSession.name,m.ClassSession.kind,m.ClassSession.trainer,m.ClassSession.room,m.ClassSession.at,m.ClassSession.capacity,m.Member.name,m.Booking.status,m.Booking.right_state).join(m.Booking,m.Booking.class_session_id==m.ClassSession.id).join(m.Member,m.Member.id==m.Booking.member_id).where(*base,m.Booking.id.in_(select(b.c.id))).order_by(m.ClassSession.at.desc(),m.Booking.id)
    return result(f,metrics,charts,query,[('Ders','text'),('Tür','text'),('Antrenör','text'),('Salon','text'),('Ders tarihi','datetime'),('Kontenjan','count'),('Üye','text'),('Rezervasyon / katılım','text'),('Ders hakkı','text')],['Ders kayıtları ders başlangıç tarihine göre seçilir. Rezervasyon katılım sayılmaz; katılım ve gelmeme oranları yalnızca kaydedilmiş yoklamanın paydasını kullanır.','Personel filtresi atanmış antrenörü seçer. Ücretli ders tahakkuk/tahsilatları Finans sekmesindeki ders kaynağından izlenir.'],export)

def product_events(f):
    known=exists(select(m.StockMovement.id).where(m.StockMovement.sale_id==m.Sale.id,m.StockMovement.branch_id==f.branch,m.StockMovement.kind=='sale').correlate(m.Sale))
    sales=select(m.Sale.product_id.label('product'),m.Sale.at.label('at'),m.Sale.quantity.label('units'),m.Sale.total_cents.label('amount'),(m.Sale.unit_cost_cents*m.Sale.quantity).label('cost'),known.label('known'),literal(False).label('refund')).join(m.Product,m.Product.id==m.Sale.product_id).where(m.Sale.branch_id==f.branch,f.range(m.Sale.at),actor_condition(m.Sale.actor_id,f))
    returns=select(m.Sale.product_id.label('product'),m.StockMovement.at.label('at'),(-m.StockMovement.returned_units).label('units'),(-m.StockMovement.refund_cents).label('amount'),(-case((m.StockMovement.restocked.is_(True),m.Sale.unit_cost_cents*m.StockMovement.returned_units),else_=0)).label('cost'),known.label('known'),literal(True).label('refund')).select_from(m.StockMovement).join(m.Sale,m.Sale.id==m.StockMovement.sale_id).join(m.Product,m.Product.id==m.Sale.product_id).where(m.StockMovement.branch_id==f.branch,m.StockMovement.returned_units>0,f.range(m.StockMovement.at),actor_condition(m.StockMovement.actor_id,f))
    if f.category:sales=sales.where(m.Product.category==f.category);returns=returns.where(m.Product.category==f.category)
    if f.method:sales=sales.where(m.Sale.method==f.method);returns=returns.where(m.StockMovement.method==f.method)
    if f.type=='sale':returns=returns.where(literal(False))
    if f.type=='return':sales=sales.where(literal(False))
    if f.type=='critical':
        condition=and_(m.Product.active.is_(True),m.Product.stock>0,m.Product.stock<=m.Product.minimum);sales=sales.where(condition);returns=returns.where(condition)
    if f.type=='empty':
        condition=and_(m.Product.active.is_(True),m.Product.stock==0);sales=sales.where(condition);returns=returns.where(condition)
    return union_all(sales,returns).subquery()

def stock(f,export=False):
    require(f.type in ['', 'sale','return','critical','empty','movements'],'Stok rapor filtresi geçersiz.')
    events=product_events(f);s=rows(select(func.coalesce(func.sum(events.c.amount),0),func.coalesce(func.sum(case((events.c.refund.is_(False),events.c.units),else_=0)),0),-func.coalesce(func.sum(case((events.c.refund.is_(True),events.c.units),else_=0)),0),func.sum(case((events.c.known.is_(True),events.c.amount-events.c.cost),else_=None)),func.count().filter(events.c.known.is_(True))))[0]
    base=[m.Product.branch_id==f.branch]
    if f.category:base.append(m.Product.category==f.category)
    critical=and_(m.Product.active.is_(True),m.Product.stock>0,m.Product.stock<=m.Product.minimum)
    empty=and_(m.Product.active.is_(True),m.Product.stock==0)
    if f.type=='critical':base.append(critical)
    if f.type=='empty':base.append(empty)
    valuation=scalar(select(func.coalesce(func.sum(m.Product.stock*m.Product.cost*100),0)).where(*base))
    metrics=[metric('net','Net ürün satışı',int(s[0]),'money'),metric('sold','Satılan ürün miktarı',int(s[1])),metric('returned','İade miktarı',int(s[2])),metric('returnRate','İade / satış miktarı',float(s[2])*100/float(s[1]) if s[1] else None,'percent'),metric('profit','Desteklenen brüt ürün marjı',int(s[3]) if s[4] else None,'money'),metric('supported','Maliyet snapshot olayları',int(s[4])),metric('value','Mevcut stok değerlemesi',int(valuation),'money','current'),metric('critical','Kritik stok',int(scalar(select(func.count()).select_from(m.Product).where(*base,critical)) or 0),'count','current'),metric('empty','Tükenen ürün',int(scalar(select(func.count()).select_from(m.Product).where(*base,empty)) or 0),'count','current')]
    by_product=select(events.c.product,func.sum(events.c.amount).label('amount'),func.sum(events.c.units).label('units')).group_by(events.c.product).subquery()
    charts=[chart('Net ürün satışları',points(select(bucket(events.c.at,f),func.sum(events.c.amount)).group_by(bucket(events.c.at,f)).order_by(bucket(events.c.at,f)),filterKey='date'),'line','money'),chart('En çok satılan ürünler',points(select(m.Product.name,by_product.c.units).join(by_product,by_product.c.product==m.Product.id).order_by(by_product.c.units.desc()).limit(12)),'bar'),chart('Kategori bazında net satış',points(select(m.Product.category,func.sum(events.c.amount)).join(events,events.c.product==m.Product.id).group_by(m.Product.category),filterKey='category'),'distribution','money')]
    if f.type=='movements':
        query=select(m.StockMovement.at,m.Product.name,m.StockMovement.kind,m.StockMovement.quantity,m.StockMovement.reason,m.User.full_name,m.StockMovement.unit_cost_cents,m.StockMovement.refund_cents).join(m.Product,m.Product.id==m.StockMovement.product_id).outerjoin(m.User,m.User.id==m.StockMovement.actor_id).where(m.StockMovement.branch_id==f.branch,f.range(m.StockMovement.at),actor_condition(m.StockMovement.actor_id,f))
        if f.category:query=query.where(m.Product.category==f.category)
        query=query.order_by(m.StockMovement.at.desc(),m.StockMovement.id);columns=[('Tarih','datetime'),('Ürün','text'),('Hareket','text'),('Miktar','count'),('Gerekçe','text'),('Personel','text'),('Birim alış','money'),('İade tutarı','money')]
    else:
        query=select(m.Product.name,m.Product.category,m.Product.stock,m.Product.minimum,m.Product.price*100,m.Product.cost*100,func.coalesce(by_product.c.units,0),func.coalesce(by_product.c.amount,0)).outerjoin(by_product,by_product.c.product==m.Product.id).where(*base).order_by(func.coalesce(by_product.c.amount,0).desc(),m.Product.id)
        if f.type in ['sale','return']:query=query.where(by_product.c.product.is_not(None))
        columns=[('Ürün','text'),('Kategori','text'),('Mevcut stok','count'),('Kritik sınır','count'),('Mevcut satış fiyatı','money'),('Mevcut alış fiyatı','money'),('Dönem net miktarı','count'),('Dönem net satış','money')]
    return result(f,metrics,charts,query,columns,['Net satış satış ve iadenin kendi işlem tarihini kullanır. İade oranı geçmiş dönem satışlarının iadeleri nedeniyle %100 üzerinde olabilir.','Brüt ürün marjı yalnızca alış maliyeti satış anında doğrulanmış kayıtlarda hesaplanır. Satılabilir iade maliyeti geri alır, hasarlı iadede maliyet korunur. İşletme gideri ve net kâr hesaplanmaz.','Stok değerlemesi mevcut kayıtlı birim alış fiyatı × mevcut stoktur; FIFO/parti değerlemesi değildir. Kategoriler mevcut ürün kategorisidir.'],export)
