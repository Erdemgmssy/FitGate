"""One stock/sale ledger, exact cents and existing branch-scoped action transactions."""
import uuid
from datetime import datetime
from decimal import Decimal
from app import models as m
from app.core import time as timezone
from app.schemas.member import normalize_phone,normalize_email
from .business import require,get,integer,amount,parse_day,validate_photo,RuleError
from .projection import wire

ACTIONS={'saveProduct','saveSupplier','stock','sellProduct','checkoutProducts','returnSale'}

def permissions(user):
    if user.role=='admin':return {'manage':True,'sell':True,'discount':True,'returns':True}
    policy=m.RolePolicy.objects.filter(branch_id=user.branch_id,role=user.role).first()
    rules=policy.permissions if policy else {}
    return {'manage':False,'sell':user.role=='staff' and rules.get('productSales',True),'discount':user.role=='staff' and rules.get('productDiscount',False),'returns':user.role=='staff' and rules.get('productReturns',False)}

def text(p,key,maximum,required=False):
    value=p.get(key,'')
    require(isinstance(value,str) and len(value.strip())<=maximum and (not required or value.strip()),f'{key}: geçerli metin gerekiyor.')
    return value.strip()

def audit(action,obj,user,branch,p,before=None):
    detail={key:value for key,value in p.items() if key!='image'}
    after=wire(obj);after.pop('image',None)
    if before:before.pop('image',None)
    m.Audit.objects.create(branch=branch,actor=user,type=action,entity_id=str(obj.id),detail=detail,before=before,after=after)

def movement(branch,product,user,**values):
    return m.StockMovement.objects.create(branch=branch,product=product,actor_id=user.id,**values)

def allocate(discount,lines):
    total=sum(value for _,_,value in lines)
    shares=[discount*value//total if total else 0 for _,_,value in lines]
    rest=discount-sum(shares)
    for index in range(len(shares)):
        if rest and shares[index]<lines[index][2]:shares[index]+=1;rest-=1
    require(rest==0,'İndirim dağıtımı tamamlanamadı.')
    return shares

def apply(action,p,user,branch):
    require(user is not None and user.role in ['admin','staff'],'Ürün işlemleri için personel yetkisi gerekli.')
    rights=permissions(user)
    if action in ['saveProduct','saveSupplier','stock']:require(rights['manage'],'Ürün/stok yönetimi için admin yetkisi gerekli.')
    if action in ['sellProduct','checkoutProducts']:require(rights['sell'],'Ürün satışı yetkisi gerekli.')
    if action=='returnSale':require(rights['returns'],'Ürün iadesi yetkisi gerekli.')
    if action=='saveSupplier':
        obj=get(m.Supplier,p['id'],branch) if p.get('id') else m.Supplier(branch=branch)
        before=wire(obj) if p.get('id') else None;name=text(p,'name',120,True)
        require(not any(other.id!=obj.id and other.name.casefold()==name.casefold() for other in m.Supplier.objects.filter(branch=branch)),'Bu tedarikçi zaten kayıtlı.')
        try:phone=normalize_phone(p['phone']) if p.get('phone') else '';email=normalize_email(p['email']) if p.get('email') else ''
        except ValueError as error:raise RuleError(str(error)) from None
        require(type(p.get('active',True)) is bool,'Aktif durumu geçersiz.')
        obj.name=name;obj.phone=phone;obj.email=email;obj.contact=text(p,'contact',600);obj.active=p.get('active',True);obj.save()
        m.Product.objects.filter(supplier_id=obj.id).update(supplier=name)
        audit(action,obj,user,branch,p,before);return {'id':str(obj.id)}
    if action=='saveProduct':
        obj=get(m.Product,p['id'],branch) if p.get('id') else m.Product(branch=branch)
        before=wire(obj) if p.get('id') else None
        if p.get('id'):require(integer(p.get('revision'),1)==obj.revision,'Ürün değişmiş; güncel ürün bilgilerini tekrar açın.')
        name=text(p,'name',120,True);code=text(p,'code',40,True).upper();barcode=text(p,'barcode',80)
        for other in m.Product.objects.all():
            if other.id==obj.id:continue
            require(other.code.upper()!=code,'Ürün kodu zaten kullanılıyor.')
            require(not barcode or other.barcode!=barcode,'Barkod zaten kullanılıyor.')
        supplier=get(m.Supplier,p['supplierId'],branch) if p.get('supplierId') else None
        require(not supplier or supplier.active,'Pasif tedarikçi seçilemez.')
        require(type(p.get('active',True)) is bool,'Aktif durumu geçersiz.')
        price=amount(p.get('price'));cost=amount(p.get('cost'));minimum=integer(p.get('minimum',0));stock=integer(p.get('stock',0)) if not p.get('id') else obj.stock
        require(not p.get('id') or 'stock' not in p or integer(p['stock'])==obj.stock,'Mevcut stok yalnızca stok hareketiyle değiştirilebilir.')
        old_cost=amount(obj.cost) if p.get('id') else None
        obj.name=name;obj.code=code;obj.barcode=barcode;obj.category=text(p,'category',80);obj.description=text(p,'description',600);obj.unit=text(p,'unit',30) or 'adet'
        obj.price=Decimal(price)/100;obj.cost=Decimal(cost)/100;obj.minimum=minimum;obj.stock=stock;obj.supplier_id=supplier.id if supplier else None;obj.supplier=supplier.name if supplier else text(p,'supplier',120)
        obj.active=p.get('active',True);obj.image=validate_photo(p.get('image',''));obj.expires=parse_day(p['expires']) if p.get('expires') else None
        obj.revision=obj.revision+1 if p.get('id') else 1;obj.save()
        if not p.get('id') and stock:movement(branch,obj,user,quantity=stock,reason='Açılış stoğu',kind='opening',supplier_id=obj.supplier_id,unit_cost_cents=cost)
        if old_cost is not None and old_cost!=cost:movement(branch,obj,user,quantity=0,reason='Ürün alış fiyatı güncellendi',kind='cost_change',supplier_id=obj.supplier_id,unit_cost_cents=cost)
        audit(action,obj,user,branch,p,before);return {'id':str(obj.id)}
    if action=='stock':
        obj=get(m.Product,p.get('id'),branch);before=wire(obj);kind=p.get('kind','adjustment');require(kind in ['receipt','loss','adjustment','count'],'Stok hareket türü geçersiz.')
        reason=text(p,'reason',1500,True)
        quantity=integer(p.get('count'),0)-obj.stock if kind=='count' else integer(p.get('quantity'),-100000,100000)
        require(kind=='count' or quantity!=0,'Stok miktarı sıfır olamaz.')
        require(kind!='receipt' or quantity>0,'Mal kabul miktarı pozitif olmalı.')
        require(kind!='loss' or quantity<0,'Hasar/kayıp miktarı negatif olmalı.')
        require(0<=obj.stock+quantity<=100000,'Stok negatif olamaz veya üst sınırı aşamaz.')
        supplier=get(m.Supplier,p['supplierId'],branch) if p.get('supplierId') else None
        received=text(p,'receivedCode',80)
        if kind=='receipt':require(supplier and supplier.active and received,'Mal kabul için aktif tedarikçi ve teslimat referansı gerekli.')
        cost=amount(p.get('cost',obj.cost)) if kind=='receipt' else None
        obj.stock+=quantity
        if kind=='receipt':obj.cost=Decimal(cost)/100;obj.supplier_id=supplier.id;obj.supplier=supplier.name;obj.revision+=1
        obj.save();movement(branch,obj,user,quantity=quantity,reason=reason,kind=kind,supplier_id=supplier.id if supplier else None,received_code=received,unit_cost_cents=cost)
        audit(action,obj,user,branch,p,before);return {'id':str(obj.id)}
    if action in ['sellProduct','checkoutProducts']:
        items=p.get('items') if action=='checkoutProducts' else [{'productId':p.get('productId'),'quantity':p.get('quantity'),'revision':p.get('revision')}]
        require(isinstance(items,list) and 1<=len(items)<=100,'Sepet 1-100 ürün içermeli.')
        require(p.get('method') in ['cash','pos','bank','mixed'],'Ödeme yöntemi geçersiz.')
        member=get(m.Member,p['memberId'],branch) if p.get('memberId') else None
        lines=[];seen=set()
        for row in items:
            require(isinstance(row,dict),'Sepet satırı geçersiz.');product=get(m.Product,row.get('productId'),branch);quantity=integer(row.get('quantity'),1)
            require(product.id not in seen,'Aynı ürünü tek sepet satırında birleştirin.');seen.add(product.id)
            require(product.active and quantity<=product.stock,'Ürün pasif veya stok yetersiz.')
            require(not product.expires or product.expires>=timezone.localdate(),'Son kullanma tarihi geçmiş ürün satılamaz.')
            if action=='checkoutProducts' or row.get('revision') is not None:require(integer(row.get('revision'),1)==product.revision,'Ürün fiyatı/koşulları değişmiş; sepeti güncelleyin.')
            lines.append((product,quantity,amount(product.price)*quantity))
        total=sum(value for _,_,value in lines);require(total<=999999999999,'Satış tutarı sınırı aşıyor.')
        discount=amount(p.get('discount',0));require(discount<=total and (not discount or rights['discount']),'İndirim tutarı veya yetkisi geçersiz.')
        if discount:text(p,'reason',1500,True)
        shares=allocate(discount,lines);checkout=uuid.uuid4();number=f'URN-{checkout.hex.upper()}';at=timezone.now()
        ids=[]
        for (product,quantity,subtotal),share in zip(lines,shares):
            sale=m.Sale.objects.create(branch=branch,product=product,member=member,quantity=quantity,total_cents=subtotal-share,product_name=product.name,method=p['method'],actor=user,at=at,checkout_id=checkout,number=number,unit_price_cents=amount(product.price),unit_cost_cents=amount(product.cost),discount_cents=share,unit=product.unit)
            product.stock-=quantity;product.save();movement(branch,product,user,quantity=-quantity,kind='sale',reason='Ürün satışı',sale_id=sale.id,method=p['method'],at=at)
            audit(action,sale,user,branch,p);ids.append(str(sale.id))
        return {'checkoutId':str(checkout),'number':number,'saleIds':ids,'totalCents':total-discount}
    if action=='returnSale':
        sale=get(m.Sale,p.get('id'),branch);before=wire(sale);quantity=integer(p.get('quantity',sale.quantity-sale.returned_quantity),1)
        require(quantity<=sale.quantity-sale.returned_quantity,'İade miktarı kalan satışı aşamaz.')
        reason=text(p,'reason',1500,True);restock=p.get('restock',True);require(type(restock) is bool,'İade stok durumu geçersiz.')
        if restock:require(not sale.product.expires or sale.product.expires>=timezone.localdate(),'Son kullanma tarihi geçmiş iade satılabilir stoğa alınamaz.')
        cumulative=sale.total_cents*(sale.returned_quantity+quantity)//sale.quantity
        refund=cumulative-sale.refunded_cents
        sale.returned_quantity+=quantity;sale.refunded_cents=cumulative;sale.returned=sale.returned_quantity==sale.quantity;sale.returned_at=timezone.now();sale.save()
        if restock:sale.product.stock+=quantity;sale.product.save()
        movement(branch,sale.product,user,quantity=quantity if restock else 0,kind='return',reason=reason,sale_id=sale.id,returned_units=quantity,refund_cents=refund,restocked=restock,method=sale.method,at=sale.returned_at)
        audit(action,sale,user,branch,p,before);return {'id':str(sale.id),'refundCents':refund}

def summary(db):
    today=timezone.localdate().isoformat();month=today[:7]
    def day(row):return timezone.localdate(datetime.fromisoformat(row['at'])).isoformat()
    returns=[row for row in db.get('stockMovements',[]) if row.get('returnedUnits',0)>0]
    def net(prefix):return sum(row['totalCents'] for row in db['sales'] if day(row).startswith(prefix))-sum(row.get('refundCents',0) for row in returns if day(row).startswith(prefix))
    return {'productCount':len(db['products']),'criticalCount':sum(row['active'] and 0<row['stock']<=row['minimum'] for row in db['products']),'emptyCount':sum(row['active'] and row['stock']==0 for row in db['products']),'todayNetCents':net(today),'monthNetCents':net(month),'returnedUnits':sum(row.get('returnedUnits',0) for row in returns),'refundCents':sum(row.get('refundCents',0) for row in returns)}
