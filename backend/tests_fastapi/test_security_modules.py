import base64
import hashlib
import uuid
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from app.main import app
from app import models as m
from app.core import time as timezone
from app.core.security import hash_password, check_password
from app.db.session import get_session
from app.services.business import execute, RuleError, member_debt
from tests_fastapi.support import TestCase


class SecurityModuleTests(TestCase):
    def setUp(self):
        self.branch = m.Branch.objects.create(name='Isolated test')
        self.admin = m.User.objects.create_user(username='admin@test.com', email='admin@test.com', password='LongTest123!', full_name='Admin', role='admin', branch=self.branch)
        self.staff = m.User.objects.create_user(username='staff@test.com', email='staff@test.com', password='LongTest123!', full_name='Staff', role='staff', branch=self.branch)
        self.plan = m.Plan.objects.create(branch=self.branch, name='Monthly', price=1500, freeze_days=10, weekdays=list(range(7)), allowed_from='00:00', allowed_to='23:59')

    def action(self, name, payload, user=None):
        return execute(name, payload, user or self.admin, uuid.uuid4())

    def member(self):
        result = self.action('addMember', {'name':'Member','phone':'05329998877','consent':True,'planId':str(self.plan.id),'start':timezone.localdate().isoformat(),'paid':'500','method':'cash'})
        return m.Member.objects.get(pk=result['result'])

    def test_refresh_rotation_logout_and_cookie_security(self):
        client = TestClient(app)
        csrf = client.get('/api/v1/auth/csrf/').json()['csrfToken']
        headers = {'X-CSRFToken':csrf}
        login = client.post('/api/v1/auth/login/', json={'email':'admin@test.com','password':'LongTest123!'}, headers=headers)
        self.assertEqual(login.status_code, 200)
        self.assertIn('HttpOnly', login.headers.get_list('set-cookie')[1])
        old_refresh = client.cookies.get('fitgate_refresh')
        access = client.cookies.get('fitgate_access')
        self.assertEqual(client.post('/api/v1/auth/refresh/', headers=headers).status_code, 200)
        self.assertNotEqual(old_refresh, client.cookies.get('fitgate_refresh'))
        replay = TestClient(app)
        replay.cookies.set('fitgate_csrf', csrf)
        replay.cookies.set('fitgate_refresh', old_refresh, path='/api/v1/auth/')
        self.assertEqual(replay.post('/api/v1/auth/refresh/', headers=headers).status_code, 401)
        self.assertEqual(client.post('/api/v1/auth/logout/', headers=headers).status_code, 200)
        self.assertEqual(client.get('/api/v1/state/', headers={'Authorization':'Bearer '+access}).status_code, 401)

    def test_legacy_password_upgrade_and_login_throttle(self):
        salt='test-salt'
        encoded=base64.b64encode(hashlib.pbkdf2_hmac('sha256',b'LongTest123!',salt.encode(),260000)).decode()
        self.admin.password=f'pbkdf2_sha256$260000${salt}${encoded}'
        self.admin.save()
        self.assertTrue(check_password('LongTest123!', self.admin.password))
        client=TestClient(app)
        csrf=client.get('/api/v1/auth/csrf/').json()['csrfToken']
        headers={'X-CSRFToken':csrf}
        self.assertEqual(client.post('/api/v1/auth/login/',json={'email':'admin@test.com','password':'LongTest123!'},headers=headers).status_code,200)
        self.assertTrue(self.admin.password.startswith('$argon2'))
        for _ in range(5):
            self.assertEqual(client.post('/api/v1/auth/login/',json={'email':'staff@test.com','password':'wrong'},headers=headers).status_code,401)
        self.assertEqual(client.post('/api/v1/auth/login/',json={'email':'staff@test.com','password':'LongTest123!'},headers=headers).status_code,429)

    def test_schema_origin_and_device_validation(self):
        self.client.force_login(self.admin)
        client=self.client.client
        self.assertEqual(client.post('/api/v1/actions/notice/',json={'payload':{},'unexpected':1},headers={'X-CSRFToken':self.client.csrf}).status_code,400)
        self.assertEqual(client.post('/api/v1/auth/logout/',headers={'X-CSRFToken':self.client.csrf,'Origin':'https://untrusted.example'}).status_code,403)
        self.assertEqual(client.post('/api/v1/device/heartbeat/',json={'sensor':'ready'}).status_code,401)
        self.assertEqual(client.get('/docs').status_code,200)
        self.assertEqual(client.get('/api/v1/health/').json()['database'],'postgresql')

    def test_membership_edit_freeze_renew_refund_and_cancel(self):
        member=self.member()
        sub=m.Subscription.objects.get()
        self.action('editMember',{'id':str(member.id),'name':'Updated','active':False},self.staff)
        self.assertFalse(member.active)
        self.action('editMember',{'id':str(member.id),'active':True},self.staff)
        self.action('freeze',{'id':str(sub.id),'reason':'Travel','start':timezone.localdate().isoformat(),'end':timezone.localdate().isoformat()})
        from app.services.membership import status
        self.assertEqual(status(sub),'frozen')
        self.action('resume',{'id':str(sub.id)})
        self.assertEqual(sub.status,'active')
        invoice=m.Invoice.objects.get()
        self.action('collect',{'invoiceId':str(invoice.id),'amount':'1000','method':'pos'},self.staff)
        self.assertEqual(member_debt(member),0)
        payment=m.Payment.objects.filter(method='pos').get()
        self.action('refund',{'paymentId':str(payment.id),'amount':'100','reason':'Correction'})
        self.assertEqual(member_debt(member),10000)
        with self.assertRaises(RuleError):
            self.action('refund',{'paymentId':str(payment.id),'amount':'1000','reason':'Too much'})
        self.action('cancelSubscription',{'id':str(sub.id),'reason':'Closed','confirmed':True})
        self.assertEqual(member_debt(member),10000)
        self.action('renew',{'memberId':str(member.id),'planId':str(self.plan.id),'start':timezone.localdate().isoformat()})
        self.assertEqual(m.Subscription.objects.count(),2)

    def test_products_stock_returns_cash_and_notices(self):
        self.action('openCash',{'amount':'100'})
        self.action('saveProduct',{'name':'Water','code':'W','price':'20','cost':'5','stock':3})
        product=m.Product.objects.get()
        self.action('stock',{'id':str(product.id),'quantity':2,'reason':'Delivery'})
        self.action('sellProduct',{'productId':str(product.id),'quantity':2,'method':'cash'},self.staff)
        sale=m.Sale.objects.get()
        self.action('returnSale',{'id':str(sale.id),'reason':'Return'})
        self.assertEqual(product.stock,5)
        self.action('closeCash',{'amount':'100'})
        cash=m.CashSession.objects.get()
        self.assertEqual(cash.expected_cents,10000)
        self.assertIsNotNone(cash.closed_at)
        self.action('notice',{'message':'Test notice'},self.staff)
        notice=m.Notice.objects.get(message='Test notice')
        self.action('readNotice',{'id':str(notice.id)},self.staff)
        self.assertEqual(m.ReadNotice.objects.count(),1)

    def test_class_booking_and_cancellation(self):
        member=self.member()
        trainer=m.Employee.objects.create(branch=self.branch,name='Trainer',role='trainer',type='fixed',hourly_rate=0)
        self.action('saveClass',{'name':'Pilates','trainerId':str(trainer.id),'room':'A','at':(timezone.now()+timedelta(days=1)).isoformat(),'duration':60,'capacity':1})
        cls=m.ClassSession.objects.get()
        result=self.action('book',{'classId':str(cls.id),'memberId':str(member.id)},self.staff)
        self.assertEqual(result['result'],'booked')
        booking=m.Booking.objects.get()
        with self.assertRaises(RuleError): self.action('bookingStatus',{'id':str(booking.id),'status':'attended'},self.staff)
        self.action('cancelClass',{'id':str(cls.id),'reason':'Trainer unavailable'})
        self.assertEqual(booking.status,'excused')
        self.assertTrue(cls.cancelled)

    def test_employee_shift_rate_device_settings_and_plan(self):
        self.action('addEmployee',{'name':'Worker','card':'STAFF-1','type':'hourly','hourlyRate':'180'})
        employee=m.Employee.objects.get()
        employee.user=self.staff; employee.save()
        self.action('saveRolePolicy',{'role':'staff','permissions':{'simulateAttendance':True}})
        self.action('scanEmployee',{'uid':'STAFF-1'},self.staff)
        shift=m.Shift.objects.get()
        shift.entry=timezone.now()-timedelta(hours=2); shift.save()
        self.action('correctShift',{'id':str(shift.id),'exit':(timezone.now()-timedelta(minutes=1)).isoformat(),'reason':'Correction'})
        self.assertIsNotNone(shift.exit)
        self.action('employeeStatus',{'id':str(employee.id),'active':False})
        self.action('saveRates',{'confirmed':True,'rates':{str(employee.id):200},'plans':[{'id':str(self.plan.id),'revision':self.plan.revision,'price':1700}]})
        self.assertEqual(m.Rate.objects.count(),2)
        self.assertEqual(self.plan.price,1700)
        self.action('saveSettings',{'capacity':50,'debtBlock':True})
        device=m.Device.objects.create(branch=self.branch,code='OFFLINE',name='Offline')
        self.action('deviceMode',{'id':str(device.id),'mode':'maintenance'})
        self.assertEqual(device.mode,'maintenance')
        self.action('savePlan',{'id':str(self.plan.id),'confirmed':True,'revision':self.plan.revision,'name':'Updated','durationUnit':'month','durationValue':1,'price':1800,'from':'06:00','to':'23:00','weekdays':[1,2,3],'freezeDays':5})
        self.assertEqual(self.plan.price,1800)

    def test_database_nonnegative_and_open_visit_uniqueness(self):
        member=self.member()
        device=m.Device.objects.create(branch=self.branch,code='GATE',name='Gate')
        m.Visit.objects.create(branch=self.branch,member=member,device=device,entry=timezone.now())
        with self.assertRaises(IntegrityError):
            with get_session().begin_nested():
                m.Visit.objects.create(branch=self.branch,member=member,device=device,entry=timezone.now())
        with self.assertRaises(IntegrityError):
            with get_session().begin_nested():
                m.Product.objects.create(branch=self.branch,name='Invalid',code='INVALID',price=1,cost=1,stock=-1)

    def test_reset_utility_is_explicit_and_preserves_other_branch(self):
        from app.services.maintenance import reset_members
        self.member()
        other=m.Branch.objects.create(name='Other')
        kept=m.Member.objects.create(branch=other,number='OTHER',name='Other',phone='123',normalized_phone='123',created_by=self.admin)
        device=m.Device.objects.create(branch=self.branch,code='KEPT',name='Kept')
        with self.assertRaises(ValueError):
            reset_members(str(self.branch.id),'wrong-database',True)
        self.assertTrue(reset_members(str(self.branch.id),'fitgate_fastapi_test')['dryRun'])
        self.assertEqual(m.Member.objects.count(),2)
        reset_members(str(self.branch.id),'fitgate_fastapi_test',True)
        self.assertEqual(m.Member.objects.count(),1)
        self.assertTrue(m.Member.objects.filter(pk=kept.pk).exists())
        self.assertEqual(m.User.objects.count(),2)
        self.assertTrue(m.Plan.objects.filter(pk=self.plan.pk).exists())
        self.assertTrue(m.Device.objects.filter(pk=device.pk).exists())
        self.assertEqual(m.Payment.objects.count(),0)

    def test_member_sale_http_contract_and_retry(self):
        self.client.force_login(self.staff)
        payload={'name':'Member','phone':'05329998877','consent':True,'planId':str(self.plan.id),'start':timezone.localdate().isoformat(),'paid':'500','method':'cash'}
        key=str(uuid.uuid4())
        for _ in range(2):
            response=self.client.post('/api/v1/actions/addMember/',data={'payload':payload},HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.json()['db']['members']),1)
        self.assertEqual(m.Payment.objects.count(),1)
        self.assertEqual(self.client.get('/api/v1/members/?q=Member').json()['count'],1)
