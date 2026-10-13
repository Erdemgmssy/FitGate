import uuid
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from app import models as m
from app.core import time as timezone
from app.db.session import get_session,SessionLocal,active_session
from app.services.business import execute,RuleError,cash_balance
from app.services.projection import snapshot
from tests_fastapi.support import TestCase

class StockTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Stock test')
        self.admin=m.User.objects.create_user(username='admin@stock.test',email='admin@stock.test',password='LongTest123!',full_name='Admin',role='admin',branch=self.branch)
        self.staff=m.User.objects.create_user(username='staff@stock.test',email='staff@stock.test',password='LongTest123!',full_name='Staff',role='staff',branch=self.branch)
        self.trainer=m.User.objects.create_user(username='trainer@stock.test',email='trainer@stock.test',password='LongTest123!',role='trainer',branch=self.branch)
        self.supplier=self.act('saveSupplier',{'name':'Supplier','phone':'05321112233','email':'supplier@test.com'})['result']['id']
        self.water=self.product('Water','W','1001',price='10.01',stock=5)
        self.bar=self.product('Bar','B','1002',price='20',stock=5)

    def act(self,action,p,user=None,key=None):return execute(action,p,user or self.admin,key or uuid.uuid4())
    def product(self,name,code,barcode,**kwargs):
        result=self.act('saveProduct',{'name':name,'code':code,'barcode':barcode,'price':'10','cost':'2','stock':0,'minimum':2,'supplierId':self.supplier,**kwargs})
        return m.Product.objects.get(pk=result['result']['id'])
    def checkout(self,items=None,**kwargs):
        return self.act('checkoutProducts',{'items':items or [{'productId':str(self.water.id),'quantity':2,'revision':self.water.revision},{'productId':str(self.bar.id),'quantity':1,'revision':self.bar.revision}],'method':'cash',**kwargs},self.staff)

    def test_create_update_uniqueness_and_price_snapshot(self):
        self.checkout();sale=m.Sale.objects.get(product=self.water)
        p=next(p for p in snapshot(self.admin)['products'] if p['id']==str(self.water.id))
        self.act('saveProduct',{**p,'price':'50','cost':'3','description':'Updated','active':False})
        self.assertEqual(sale.total_cents,2002);self.assertEqual(sale.unit_price_cents,1001);self.assertFalse(self.water.active)
        with self.assertRaises(RuleError):self.act('saveProduct',{**p,'price':'60'})
        with self.assertRaises(RuleError):self.product('Duplicate','W','new')
        with self.assertRaises(RuleError):self.product('Duplicate','NEW','1001')
        self.assertTrue(m.StockMovement.objects.filter(kind='cost_change',unit_cost_cents=300).exists())
        with self.assertRaises(RuleError):self.act('saveProduct',{**p,'revision':self.water.revision,'stock':999})

    def test_multi_product_guest_member_sales_and_exact_discount(self):
        self.checkout();rows=list(m.Sale.objects.all())
        self.assertEqual(len(rows),2);self.assertEqual(len({r.checkout_id for r in rows}),1);self.assertEqual(sum(r.total_cents for r in rows),4002)
        self.assertEqual(self.water.stock,3);self.assertEqual(self.bar.stock,4)
        member=m.Member.objects.create(branch=self.branch,name='Member',number='ONE',phone='one',normalized_phone='one',created_by=self.admin)
        self.act('saveRolePolicy',{'role':'staff','permissions':{'productDiscount':True}})
        self.checkout(memberId=str(member.id),discount='1.01',reason='Promotion')
        discounted=list(m.Sale.objects.filter(member=member))
        self.assertEqual(sum(r.discount_cents for r in discounted),101);self.assertEqual(sum(r.total_cents for r in discounted),3901)

    def test_receipt_loss_count_and_cost_history(self):
        p={'id':str(self.water.id),'kind':'receipt','quantity':4,'supplierId':self.supplier,'receivedCode':'DEL-1','cost':'3.50','reason':'Delivery'}
        self.act('stock',p);self.assertEqual(self.water.stock,9);self.assertEqual(self.water.cost, Decimal('3.50'))
        row=m.StockMovement.objects.get(kind='receipt');self.assertEqual(row.unit_cost_cents,350);self.assertEqual(row.actor_id,self.admin.id);self.assertEqual(str(row.supplier_id),self.supplier)
        self.act('stock',{'id':str(self.water.id),'kind':'loss','quantity':-2,'reason':'Broken'});self.assertEqual(self.water.stock,7)
        self.act('stock',{'id':str(self.water.id),'kind':'count','count':3,'reason':'Physical count'});self.assertEqual(self.water.stock,3)
        self.act('stock',{'id':str(self.water.id),'quantity':-1,'reason':'Adjustment'});self.assertEqual(self.water.stock,2)
        self.assertEqual(snapshot(self.admin)['stockSummary']['criticalCount'],1)
        with self.assertRaises(RuleError):self.act('stock',{**p,'receivedCode':''})
        with self.assertRaises(RuleError):self.act('stock',{'id':str(self.water.id),'quantity':-3,'reason':'Below zero'})

    def test_partial_full_return_and_damage_no_restock(self):
        self.checkout();sale=m.Sale.objects.get(product=self.water)
        self.act('returnSale',{'id':str(sale.id),'quantity':1,'restock':False,'reason':'Damaged'})
        self.assertEqual(self.water.stock,3);self.assertEqual(sale.returned_quantity,1);self.assertEqual(sale.refunded_cents,1001);self.assertFalse(sale.returned)
        self.act('returnSale',{'id':str(sale.id),'quantity':1,'restock':True,'reason':'Unopened'})
        self.assertEqual(self.water.stock,4);self.assertTrue(sale.returned);self.assertEqual(sale.refunded_cents,sale.total_cents)
        with self.assertRaises(RuleError):self.act('returnSale',{'id':str(sale.id),'quantity':1,'reason':'Twice'})
        self.assertEqual(m.StockMovement.objects.filter(kind='return').count(),2)

    def test_discounted_return_cumulative_rounding(self):
        self.act('checkoutProducts',{'items':[{'productId':str(self.water.id),'quantity':3,'revision':1}],'method':'bank','discount':'1.01','reason':'Promotion'})
        sale=m.Sale.objects.get();refunds=[]
        for _ in range(3):refunds.append(self.act('returnSale',{'id':str(sale.id),'quantity':1,'reason':'Return'})['result']['refundCents'])
        self.assertEqual(sum(refunds),2902);self.assertEqual(refunds,[967,967,968]);self.assertEqual(sale.refunded_cents,2902)

    def test_cash_finance_dashboard_consistency_and_period_refunds(self):
        self.act('openCash',{'amount':'100'});session=m.CashSession.objects.get()
        self.checkout();self.assertEqual(cash_balance(self.branch,session,timezone.now()),14002)
        self.act('checkoutProducts',{'items':[{'productId':str(self.bar.id),'quantity':1,'revision':1}],'method':'pos'})
        self.assertEqual(cash_balance(self.branch,session,timezone.now()),14002)
        sale=m.Sale.objects.get(product=self.water)
        self.act('returnSale',{'id':str(sale.id),'quantity':1,'restock':False,'reason':'Damaged'})
        db=snapshot(self.admin);self.assertEqual(db['finance']['cashCents'],3001);self.assertEqual(db['stockSummary']['todayNetCents'],5001)
        from app.services.dashboard import summary
        report=summary(self.admin,timezone.localdate());self.assertEqual(report['metrics']['dailyCents'],5001)
        self.act('closeCash',{'amount':'130.01'});self.assertEqual(session.expected_cents,13001)
        self.act('openCash',{'amount':'0'});new=m.CashSession.objects.get(closed_at__isnull=True)
        self.act('returnSale',{'id':str(sale.id),'quantity':1,'reason':'Later return'})
        self.assertEqual(session.expected_cents,13001);self.assertEqual(cash_balance(self.branch,new,timezone.now()),-1001)
        self.assertEqual(m.Payment.objects.count(),0)

    def test_idempotency_and_simultaneous_stock_cannot_oversell(self):
        get_session().commit();barrier=Barrier(2);user_id=self.staff.id;product_id=str(self.water.id)
        def attempt():
            with SessionLocal() as session:
                token=active_session.set(session)
                try:
                    user=session.get(m.User,user_id);barrier.wait(timeout=10)
                    execute('checkoutProducts',{'items':[{'productId':product_id,'quantity':3,'revision':1}],'method':'cash'},user,uuid.uuid4());session.commit();return 'ok'
                except RuleError:session.rollback();return 'rejected'
                finally:active_session.reset(token)
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(lambda _:attempt(),range(2)))
        self.assertEqual(sorted(outcomes),['ok','rejected']);get_session().expire_all();self.assertEqual(self.water.stock,2)
        key=uuid.uuid4();payload={'items':[{'productId':product_id,'quantity':1,'revision':1}],'method':'cash'}
        first=self.act('checkoutProducts',payload,self.staff,key);second=self.act('checkoutProducts',payload,self.staff,key)
        self.assertEqual(first,second);self.assertEqual(self.water.stock,1);self.assertEqual(m.Sale.objects.count(),2)

    def test_invalid_cart_rollback_and_staff_permissions(self):
        with self.assertRaises(RuleError):self.checkout(items=[{'productId':str(self.water.id),'quantity':1,'revision':1},{'productId':str(self.bar.id),'quantity':99,'revision':1}])
        self.assertEqual(self.water.stock,5);self.assertEqual(m.Sale.objects.count(),0)
        for p in [{'discount':'1','reason':'Discount'},{'discount':'0.001'},{'items':[{'productId':str(self.water.id),'quantity':1,'revision':99}]}]:
            with self.assertRaises(RuleError):self.checkout(**p)
        self.checkout();sale=m.Sale.objects.get(product=self.water)
        with self.assertRaises(RuleError):self.act('returnSale',{'id':str(sale.id),'quantity':1,'reason':'No authority'},self.staff)
        with self.assertRaises(RuleError):self.act('stock',{'id':str(self.water.id),'quantity':1,'reason':'No authority'},self.staff)
        self.act('saveRolePolicy',{'role':'staff','permissions':{'productSales':False}})
        with self.assertRaises(RuleError):self.checkout()
        with self.assertRaises(RuleError):self.act('sellProduct',{'productId':str(self.water.id),'quantity':1,'method':'cash'},self.trainer)

    def test_cross_branch_supplier_and_products(self):
        other=m.Branch.objects.create(name='Other');supplier=m.Supplier.objects.create(branch=other,name='Other')
        with self.assertRaises(RuleError):self.product('Cross','C','1003',supplierId=str(supplier.id))
        product=m.Product.objects.create(branch=other,name='Other',code='OTHER',price=10,cost=2,stock=5)
        with self.assertRaises(RuleError):self.checkout(items=[{'productId':str(product.id),'quantity':1,'revision':1}])
        self.assertEqual(product.stock,5)

    def test_expiry_and_inactive_guards(self):
        self.water.expires=timezone.localdate()-timedelta(days=1);self.water.save()
        with self.assertRaises(RuleError):self.checkout()
        self.water.expires=None;self.water.active=False;self.water.save()
        with self.assertRaises(RuleError):self.checkout()
        self.water.active=True;self.water.save();self.checkout();sale=m.Sale.objects.get(product=self.water)
        self.water.expires=timezone.localdate()-timedelta(days=1);self.water.save()
        with self.assertRaises(RuleError):self.act('returnSale',{'id':str(sale.id),'quantity':1,'restock':True,'reason':'Expired'})
        self.act('returnSale',{'id':str(sale.id),'quantity':1,'restock':False,'reason':'Expired'});self.assertEqual(self.water.stock,3)

    def test_reload_persistence_and_private_cost_fields(self):
        self.checkout();self.client.force_login(self.admin)
        a=self.client.get('/api/v1/state/').json()['db'];b=self.client.get('/api/v1/state/').json()['db']
        self.assertEqual(a['sales'],b['sales']);self.assertEqual(a['stockMovements'],b['stockMovements']);self.assertEqual(a['products'],b['products'])
        staff=snapshot(self.staff);self.assertNotIn('cost',staff['products'][0]);self.assertNotIn('unitCostCents',staff['sales'][0]);self.assertEqual(staff['suppliers'],[])
        self.assertEqual(staff['stockPermissions'],{'manage':False,'sell':True,'discount':False,'returns':False})

    def test_optin_member_maintenance_keeps_guest_sales(self):
        member=m.Member.objects.create(branch=self.branch,name='Member',number='ONE',phone='one',normalized_phone='one',created_by=self.admin)
        self.checkout(memberId=str(member.id));self.checkout()
        from app.services.maintenance import reset_members
        reset_members(str(self.branch.id),'fitgate_fastapi_test',True)
        self.assertEqual(m.Sale.objects.count(),2);self.assertEqual(self.water.stock,3)

    def test_supplier_validation_and_duplicate_names(self):
        for values in [{'name':'Supplier'},{'name':'supplier'},{'name':'New','email':'bad'},{'name':'New','phone':'bad'}]:
            with self.assertRaises(RuleError):self.act('saveSupplier',values)
        self.act('saveSupplier',{'id':self.supplier,'name':'Supplier renamed','active':False})
        with self.assertRaises(RuleError):self.act('stock',{'id':str(self.water.id),'kind':'receipt','quantity':1,'supplierId':self.supplier,'receivedCode':'DEL','reason':'Delivery'})

    def test_enabled_staff_return_discount_and_audit(self):
        self.act('saveRolePolicy',{'role':'staff','permissions':{'productReturns':True,'productDiscount':True}})
        self.checkout(discount='1',reason='Promotion');sale=m.Sale.objects.get(product=self.water)
        self.act('returnSale',{'id':str(sale.id),'quantity':1,'reason':'Refund'},self.staff)
        self.assertEqual(m.StockMovement.objects.get(kind='return').actor_id,self.staff.id)
        self.assertEqual(m.Audit.objects.filter(type='returnSale',actor=self.staff).count(),1)
