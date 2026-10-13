import uuid
from datetime import timedelta
from app import models as m
from app.services.business import execute,RuleError,debt
from app.services.projection import snapshot
from app.core import time as tz
from tests_fastapi.support import TestCase

class PanelAccessTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Panel access')
        self.admin=m.User.objects.create_user(branch=self.branch,username='admin@panel.test',email='admin@panel.test',role='admin',password='AdminPassword123!')
        self.staff=m.User.objects.create_user(branch=self.branch,username='staff@panel.test',email='staff@panel.test',role='staff',password='StaffPassword123!')
        self.plan=m.Plan.objects.create(branch=self.branch,name='Plan',price=100)
        self.member=m.Member.objects.create(branch=self.branch,name='Member',number='PA1',phone='1',created_by=self.admin)
        self.sub=m.Subscription.objects.create(branch=self.branch,member=self.member,plan=self.plan,plan_name='Plan',price_cents=10000,start=tz.localdate(),end=tz.localdate()+timedelta(days=30))
        self.invoice=m.Invoice.objects.create(branch=self.branch,member=self.member,subscription=self.sub,number='PA-I1',total_cents=10000)
    def action(self,name,p,user=None,key=None):return execute(name,p,user or self.staff,key or uuid.uuid4())
    def test_own_payment_history_keeps_complete_member_balance(self):
        self.action('collect',{'invoiceId':str(self.invoice.id),'amount':'30','method':'cash'},self.admin)
        self.action('collect',{'invoiceId':str(self.invoice.id),'amount':'20','method':'bank'})
        data=snapshot(self.staff)
        self.assertEqual(len(data['payments']),1);self.assertEqual(data['payments'][0]['actorId'],self.staff.id)
        self.assertEqual(data['invoices'][0]['netPaidCents'],5000);self.assertEqual(debt(self.invoice),5000)
        self.assertEqual(len(snapshot(self.admin)['payments']),2);self.assertIn('finance',snapshot(self.admin))
        self.assertNotIn('finance',data)
    def test_default_staff_can_operate_but_not_manage(self):
        member=self.action('addMember',{'name':'New member','phone':'05329998877','consent':True})['result']
        self.action('assignCard',{'memberId':member,'uid':'PA-CARD'})
        self.action('renew',{'memberId':member,'planId':str(self.plan.id),'start':tz.localdate().isoformat()})
        product=m.Product.objects.create(branch=self.branch,name='Water',code='PA-W',price=10,cost=5,stock=10)
        self.action('checkoutProducts',{'items':[{'productId':str(product.id),'quantity':1,'revision':product.revision}],'method':'cash'})
        for action,p in [('savePlan',{'id':str(self.plan.id)}),('saveRates',{'confirmed':True}),('saveSettings',{'capacity':1}),('saveEmployee',{'name':'Denied'}),('saveSupplier',{'name':'Denied'}),('stock',{'id':str(product.id),'quantity':1}),('refund',{'paymentId':'none','amount':1,'reason':'Denied'}),('cancelInvoice',{'invoiceId':str(self.invoice.id),'reason':'Denied'})]:
            with self.subTest(action=action),self.assertRaises(RuleError):self.action(action,p)
        self.assertTrue(m.Audit.objects.filter(actor=self.staff,type='addMember').exists());self.assertTrue(m.Audit.objects.filter(actor=self.staff,type='checkoutProducts').exists())
    def test_technical_api_and_snapshot_are_admin_only(self):
        m.Device.objects.create(branch=self.branch,name='Device',code='PA-D',telemetry={'firmware':'6','outsideCm':10,'port':'COM6'})
        self.client.force_login(self.staff)
        for path in ['sensors/measurements/','diagnostics/events/','admin/dashboard/','finance/export/']:
            self.assertEqual(self.client.get('/api/v1/'+path).status_code,403)
        device=snapshot(self.staff)['devices'][0]
        self.assertNotIn('telemetry',device);self.assertNotIn('sensor',device)
        self.client.force_login(self.admin);self.assertEqual(self.client.get('/api/v1/sensors/measurements/').status_code,200)
    def test_special_stock_return_right_is_preserved_and_cost_private(self):
        product=m.Product.objects.create(branch=self.branch,name='Water',code='PA-W',price=10,cost=5,stock=10,supplier='Private supplier')
        self.action('checkoutProducts',{'items':[{'productId':str(product.id),'quantity':1,'revision':product.revision}],'method':'cash'},self.admin)
        data=snapshot(self.staff);self.assertEqual(data['sales'],[]);self.assertNotIn('supplier',data['products'][0]);self.assertNotIn('cost',data['products'][0])
        self.action('saveRolePolicy',{'role':'staff','permissions':{'productReturns':True}},self.admin)
        data=snapshot(self.staff);self.assertTrue(data['stockPermissions']['returns']);self.assertEqual(len(data['sales']),1)
        self.action('returnSale',{'id':data['sales'][0]['id'],'quantity':1,'reason':'Authorized return'})
    def test_no_payment_permission_cannot_bypass_with_member_sale(self):
        self.action('saveRolePolicy',{'role':'staff','permissions':{'collections':False}},self.admin)
        with self.assertRaises(RuleError):self.action('addMember',{'name':'Denied paid member','phone':'05329998877','consent':True,'planId':str(self.plan.id),'start':tz.localdate().isoformat(),'paid':'10','method':'cash'})
        self.assertEqual(m.Member.objects.count(),1);self.assertEqual(m.Payment.objects.count(),0)
    def test_receipt_status_is_account_scoped_and_no_mutation(self):
        key=uuid.uuid4();self.action('collect',{'invoiceId':str(self.invoice.id),'amount':'10','method':'cash'},key=key)
        self.client.force_login(self.staff);self.assertEqual(self.client.get(f'/api/v1/actions/status/{key}/').json()['status'],'completed')
        self.client.force_login(self.admin);self.assertEqual(self.client.get(f'/api/v1/actions/status/{key}/').json()['status'],'not_found')
        self.assertEqual(self.client.get('/api/v1/actions/status/not-a-uuid/').status_code,400);self.assertEqual(m.Payment.objects.count(),1)
