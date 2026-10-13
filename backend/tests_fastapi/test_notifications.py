import uuid
from datetime import timedelta
from unittest.mock import patch
from app import models as m
from app.core import time as tz
from app.db.session import get_session
from app.services.notifications import sync,read,compose
from app.services.business import execute,RuleError
from app.services.projection import snapshot
from tests_fastapi.support import TestCase

class NotificationTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Notification branch')
        self.admin=m.User.objects.create_user(branch=self.branch,role='admin',username='admin@n.test',email='admin@n.test')
        self.staff=m.User.objects.create_user(branch=self.branch,role='staff',username='staff@n.test',email='staff@n.test')
        self.trainer=m.User.objects.create_user(branch=self.branch,role='trainer',username='trainer@n.test',email='trainer@n.test')
        self.employee=m.Employee.objects.create(branch=self.branch,user=self.staff,name='Staff',type='hourly')
        self.coach=m.Employee.objects.create(branch=self.branch,user=self.trainer,name='Coach',type='fixed')
        self.now=tz.now();self.today=tz.localdate(self.now)
        self.member=m.Member.objects.create(branch=self.branch,name='Member',number='N1',phone='1',normalized_phone='1',created_by=self.admin)
        self.plan=m.Plan.objects.create(branch=self.branch,name='Plan',price=100,days=30)
        self.sub=m.Subscription.objects.create(branch=self.branch,member=self.member,plan=self.plan,plan_name='Plan',start=self.today-timedelta(days=20),end=self.today+timedelta(days=2),price_cents=10000)
        self.invoice=m.Invoice.objects.create(branch=self.branch,member=self.member,subscription=self.sub,number='N-I',total_cents=10000)
        self.part=m.Installment.objects.create(branch=self.branch,invoice=self.invoice,due=self.today-timedelta(days=1),amount_cents=10000)
        self.product=m.Product.objects.create(branch=self.branch,name='Water',code='N',stock=2,minimum=3,price=10,cost=5)
        self.cls=m.ClassSession.objects.create(branch=self.branch,name='Yoga',trainer_id=self.coach.id,at=self.now+timedelta(hours=2),duration=60,capacity=5)
        self.shift=m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.employee,actor=self.admin,start=self.now+timedelta(hours=3),end=self.now+timedelta(hours=11))
        self.device=m.Device.objects.create(branch=self.branch,code='N-D',name='Gate',last_seen=self.now,sensor='fault',simulated=False)
    def active(self,user=None,kind=None):return [n for n in sync(user or self.admin) if n['status']=='active' and (not kind or n['type']==kind)]

    def test_sources_severity_order_stable_identity_and_no_daily_duplicates(self):
        first=self.active();self.assertEqual({n['type'] for n in first},{'device','membership','payment','stock','class','shift'})
        self.assertEqual(first[0]['severity'],'critical')
        self.assertEqual({n['id'] for n in first},{n['id'] for n in self.active()})
        read(self.admin,next(n['id'] for n in first if n['type']=='payment'))
        with patch('app.core.time.now',return_value=self.now+timedelta(days=1)):
            payment=self.active(kind='payment')[0]
        self.assertTrue(payment['read']);self.assertEqual(payment['targetId'],str(self.invoice.id));self.assertEqual(payment['memberId'],str(self.member.id))

    def test_membership_freeze_cancel_sessions_and_expired_rules(self):
        self.assertEqual(len(self.active(kind='membership')),1)
        m.Freeze.objects.create(branch=self.branch,subscription=self.sub,start=self.today,end=self.today+timedelta(days=2),planned_end=self.today+timedelta(days=1),actor=self.admin)
        self.assertEqual(self.active(kind='membership'),[])
        m.Freeze.objects.all().delete();self.sub.status='cancelled';self.sub.save()
        self.assertEqual(self.active(kind='membership'),[])
        self.sub.status='active';self.sub.end=None;self.sub.save();self.assertEqual(self.active(kind='membership'),[])
        self.sub.end=self.today-timedelta(days=1);self.sub.save();self.assertIn('süresi dolmuş',self.active(kind='membership')[0]['message'])

    def test_debt_paid_cancelled_and_archived_installments_resolve(self):
        self.active();self.part.archived=True;self.part.save();self.assertEqual(self.active(kind='payment'),[])
        self.part.archived=False;self.part.save();self.active()
        m.Payment.objects.create(branch=self.branch,invoice=self.invoice,actor=self.admin,number='N-P',method='cash',amount_cents=10000)
        self.assertEqual(self.active(kind='payment'),[])
        self.invoice.status='cancelled';self.invoice.save();self.assertEqual(self.active(kind='payment'),[])

    def test_device_resolution_unknown_is_not_recovery_and_new_episode_unread(self):
        first=self.active(kind='device')[0];read(self.admin,first['id'])
        self.device.sensor='unknown';self.device.save()
        self.assertEqual(self.active(kind='device')[0]['id'],first['id'])
        self.device.sensor='ready';self.device.last_seen=tz.now();self.device.save()
        self.assertEqual(self.active(kind='device'),[])
        closed=next(n for n in sync(self.admin) if n['id']==first['id']);self.assertEqual(closed['status'],'resolved');self.assertIsNotNone(closed['resolvedAt'])
        self.device.sensor='fault';self.device.save();new=self.active(kind='device')[0]
        self.assertNotEqual(new['id'],first['id']);self.assertFalse(new['read'])

    def test_disabled_maintenance_simulated_and_never_connected_do_not_alert(self):
        first=self.active(kind='device')[0];self.device.enabled=False;self.device.save()
        self.assertEqual(self.active(kind='device'),[])
        self.assertEqual(next(n for n in sync(self.admin) if n['id']==first['id'])['status'],'inactive')
        for index,values in enumerate([{'enabled':False},{'mode':'maintenance'},{'simulated':True},{'last_seen':None}]):
            m.Device.objects.create(branch=self.branch,code=f'IGNORE-{index}',sensor='fault',last_seen=self.now-timedelta(minutes=5),**({'last_seen':None} if index==3 else values)) if index!=3 else m.Device.objects.create(branch=self.branch,code='IGNORE-3',sensor='fault',last_seen=None)
        self.assertEqual(self.active(kind='device'),[])

    def test_offline_evidence_and_component_fault_recovery(self):
        self.device.sensor='ready';self.device.last_seen=self.now-timedelta(minutes=5);self.device.save()
        alert=self.active(kind='device')[0];self.assertIn('bağlantı',alert['message'])
        self.device.last_seen=tz.now();self.device.telemetry={'rfid':'fault'};self.device.save()
        active=self.active(kind='device');self.assertEqual(len(active),1);self.assertIn('rfid',active[0]['message'])
        self.device.telemetry={'rfid':'ready'};self.device.save();self.assertEqual(self.active(kind='device'),[])

    def test_stock_disabled_restock_and_zero_stock_severity(self):
        self.assertEqual(self.active(kind='stock')[0]['severity'],'warning')
        self.product.stock=0;self.product.save();self.assertEqual(self.active(kind='stock')[0]['severity'],'critical')
        self.product.stock=10;self.product.save();self.assertEqual(self.active(kind='stock'),[])
        self.product.stock=0;self.product.active=False;self.product.save();self.assertEqual(self.active(kind='stock'),[])

    def test_bridge_retrying_with_cleared_last_seen_is_real_offline_evidence(self):
        self.device.last_seen=None;self.device.sensor='unknown';self.device.telemetry={'connection':'retrying'};self.device.save()
        first=self.active(kind='device')[0]
        self.assertIn('bağlantı',first['message']);self.assertEqual(self.active(kind='device')[0]['id'],first['id'])
        self.device.last_seen=tz.now();self.device.sensor='ready';self.device.telemetry={'connection':'connected'};self.device.save()
        self.assertEqual(self.active(kind='device'),[])
        self.assertEqual(next(n for n in sync(self.admin) if n['id']==first['id'])['status'],'resolved')

    def test_upcoming_class_cancellation_shift_leave_and_own_trainer_scope(self):
        self.assertEqual(len(self.active(self.trainer)),1)
        self.assertEqual(self.active(self.trainer)[0]['targetId'],str(self.cls.id))
        self.cls.cancelled=True;self.cls.save();self.assertEqual(self.active(kind='class'),[])
        leave=m.LeaveType.objects.create(branch_id=self.branch.id,name='Leave')
        m.LeaveRequest.objects.create(branch_id=self.branch.id,employee=self.employee,actor=self.admin,type_id=leave.id,start=self.today,end=self.today+timedelta(days=1),status='approved')
        self.assertEqual(self.active(kind='shift'),[])

    def test_branch_role_and_read_authorization_backend(self):
        admin=self.active();staff=self.active(self.staff)
        self.assertEqual({n['type'] for n in staff},{'membership','class','shift'})
        finance=next(n for n in admin if n['type']=='payment')
        with self.assertRaises(RuleError):read(self.staff,finance['id'])
        other=m.Branch.objects.create(name='Other');other_user=m.User.objects.create_user(branch=other,role='admin',username='other@n.test',email='other@n.test')
        self.assertEqual(sync(other_user),[])
        with self.assertRaises(RuleError):read(other_user,finance['id'])
        with self.assertRaises(RuleError):read(self.admin,'stock-virtual-id')
        self.assertFalse(any(n['type'] in ['payment','device','stock'] for n in snapshot(self.staff)['notices']))

    def test_read_idempotent_manual_dedup_and_staff_cannot_create_critical(self):
        notice=compose(self.staff,{'message':'Panel message','severity':'warning'})
        self.assertEqual(notice.id,compose(self.staff,{'message':'Panel message','severity':'warning'}).id)
        for _ in range(2):execute('readNotice',{'id':str(notice.id)},self.staff,uuid.uuid4())
        self.assertEqual(m.ReadNotice.objects.filter(user=self.staff,notice_id=str(notice.id)).count(),1)
        with self.assertRaises(RuleError):compose(self.staff,{'message':'Critical','severity':'critical'})
        self.assertEqual(compose(self.admin,{'message':'Critical','severity':'critical'}).details['severity'],'critical')

    def test_class_notice_reuses_existing_key_and_routes_to_own_class(self):
        from app.services.classes import notice
        for _ in range(2):notice(self.admin,self.branch,'Lesson reminder','class-reminder-test',class_id=self.cls.id)
        self.assertEqual(m.Notice.objects.filter(event_key='class-reminder-test').count(),1)
        item=m.Notice.objects.get(event_key='class-reminder-test');read(self.trainer,item.id)
        self.assertEqual(item.details['targetId'],str(self.cls.id))

    def test_snapshot_preserves_business_records_and_old_notice(self):
        old=m.Notice.objects.create(branch=self.branch,actor=self.staff,message='Existing message')
        before=(self.sub.price_cents,self.invoice.total_cents,self.product.stock,m.Subscription.objects.count(),m.Invoice.objects.count())
        for _ in range(3):snapshot(self.admin)
        get_session().refresh(old);self.assertEqual(old.message,'Existing message')
        self.assertEqual(before,(self.sub.price_cents,self.invoice.total_cents,self.product.stock,m.Subscription.objects.count(),m.Invoice.objects.count()))
