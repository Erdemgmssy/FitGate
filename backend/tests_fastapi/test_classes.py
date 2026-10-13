import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from app import models as m
from app.core import time as timezone
from app.db.session import get_session,SessionLocal,active_session
from app.services.business import execute,RuleError,debt
from app.services.classes import state,lesson_usage
from app.services.projection import snapshot
from tests_fastapi.support import TestCase

class ClassTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Lessons test')
        self.admin=m.User.objects.create_user(username='admin@classes.test',email='admin@classes.test',password='LongTest123!',role='admin',branch=self.branch)
        self.staff=m.User.objects.create_user(username='staff@classes.test',email='staff@classes.test',password='LongTest123!',role='staff',branch=self.branch)
        self.trainer_user=m.User.objects.create_user(username='trainer@classes.test',email='trainer@classes.test',password='LongTest123!',role='trainer',branch=self.branch)
        self.trainer=m.Employee.objects.create(branch=self.branch,name='Trainer',role='trainer',type='fixed',hourly_rate=0,user=self.trainer_user)
        self.other_trainer=m.Employee.objects.create(branch=self.branch,name='Other',role='trainer',type='fixed',hourly_rate=0)
        self.plan=m.Plan.objects.create(branch=self.branch,name='Lessons',price=100,weekdays=list(range(7)),lesson_types=['group','private'],lesson_sessions=2)
        self.member=self.make_member('ONE')
        self.other=self.make_member('TWO')

    def act(self,name,p,user=None,key=None): return execute(name,p,user or self.admin,key or uuid.uuid4())
    def make_member(self,number):
        member=m.Member.objects.create(branch=self.branch,name=number,number=number,phone=number,normalized_phone=number,created_by=self.admin)
        self.act('renew',{'memberId':str(member.id),'planId':str(self.plan.id)})
        return member
    def create(self,**overrides):
        p={'name':'Pilates','trainerId':str(self.trainer.id),'room':'A','at':(timezone.now()+timedelta(days=2)).isoformat(),'duration':60,'capacity':1,'requireLesson':True,**overrides}
        result=self.act('saveClass',p)
        return m.ClassSession.objects.get(pk=result['result']['id'])
    def book(self,cls,member=None):
        self.act('book',{'classId':str(cls.id),'memberId':str((member or self.member).id)},self.staff)
        return m.Booking.objects.filter(class_session=cls,member=member or self.member).order_by('-at').first()

    def test_create_recurring_edit_future_and_past_status(self):
        cls=self.create(repeatCount=3)
        self.assertEqual(m.ClassSession.objects.count(),3)
        first=m.ClassSession.objects.order_by('at').first()
        self.act('saveClass',{**snapshot(self.admin)['classes'][0],'id':str(first.id),'at':(first.at+timedelta(hours=1)).isoformat(),'price':'0','scope':'future','room':'B'})
        self.assertTrue(all(row.room=='B' for row in m.ClassSession.objects.all()))
        cls.at=timezone.now()-timedelta(hours=2);cls.save();self.assertEqual(state(cls),'completed')
        self.act('classOutcome',{'id':str(cls.id),'reason':'Trainer sick'});self.assertEqual(state(cls),'notheld')

    def test_trainer_room_member_overlaps_and_boundaries(self):
        cls=self.create()
        with self.assertRaises(RuleError):self.create(room='B')
        with self.assertRaises(RuleError):self.create(trainerId=str(self.other_trainer.id))
        other=self.create(trainerId=str(self.other_trainer.id),room='B');self.book(cls)
        with self.assertRaises(RuleError):self.book(other)
        adjacent=self.create(at=(cls.at+timedelta(hours=1)).isoformat());self.book(adjacent)

    def test_leave_and_shift_availability(self):
        cls=self.create();cls.cancelled=True;cls.save()
        kind=m.LeaveType.objects.create(branch_id=self.branch.id,name='Leave')
        day=timezone.localdate(cls.at)
        m.LeaveRequest.objects.create(branch_id=self.branch.id,employee=self.trainer,type_id=kind.id,start=day,end=day,status='approved',actor=self.admin)
        with self.assertRaises(RuleError):self.create()
        m.LeaveRequest.objects.all().update(status='rejected')
        m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.trainer,start=cls.at+timedelta(hours=3),end=cls.at+timedelta(hours=8),actor=self.admin)
        with self.assertRaises(RuleError):self.create()

    def test_waitlist_promotion_duplicate_and_deadline(self):
        cls=self.create();first=self.book(cls);waiting=self.book(cls,self.other)
        self.assertEqual(waiting.status,'waiting')
        with self.assertRaises(RuleError):self.book(cls)
        self.act('bookingStatus',{'id':str(first.id),'status':'cancelled','reason':'Schedule changed'},self.staff)
        self.assertEqual(waiting.status,'booked');self.assertEqual(first.right_state,'released')
        self.assertTrue(m.Audit.objects.filter(type='waitlistPromotion').exists())
        cls.booking_minutes=10080;cls.save()
        with self.assertRaises(RuleError):self.book(cls)

    def test_attendance_consumes_separate_rights_once_and_correction(self):
        cls=self.create();b=self.book(cls);sub=b.subscription;gym_remaining=sub.remaining
        self.assertEqual(lesson_usage(sub),1)
        with self.assertRaises(RuleError):self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        cls.at=timezone.now()-timedelta(minutes=5);cls.save()
        key=uuid.uuid4();p={'id':str(b.id),'status':'late'}
        self.act('bookingStatus',p,self.trainer_user,key);self.act('bookingStatus',p,self.trainer_user,key)
        self.assertEqual(b.right_state,'consumed');self.assertEqual(lesson_usage(sub),1);self.assertEqual(sub.remaining,gym_remaining)
        with self.assertRaises(RuleError):self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        self.act('bookingStatus',{'id':str(b.id),'status':'excused','reason':'Medical correction'},self.trainer_user)
        self.assertEqual(lesson_usage(sub),0)

    def test_lesson_limit_and_sale_contract_not_current_plan(self):
        cls=self.create();self.book(cls)
        other=self.create(at=(cls.at+timedelta(days=1)).isoformat());self.book(other)
        last=self.create(at=(cls.at+timedelta(days=2)).isoformat())
        self.plan.lesson_sessions=20;self.plan.save()
        with self.assertRaises(RuleError):self.book(last)
        self.assertEqual(self.member.id,m.Subscription.objects.filter(member=self.member).first().member_id)

    def test_late_cancel_no_show_policies_and_no_double_charge(self):
        cls=self.create(cancelMinutes=10080);b=self.book(cls)
        self.act('bookingStatus',{'id':str(b.id),'status':'cancelled','reason':'Late cancellation'},self.staff)
        self.assertEqual(b.right_state,'consumed')
        with self.assertRaises(RuleError):self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.staff)
        cls2=self.create(at=(cls.at+timedelta(days=1)).isoformat(),noShowConsumes=False);b2=self.book(cls2)
        cls2.at=timezone.now()-timedelta(hours=2);cls2.save()
        self.act('bookingStatus',{'id':str(b2.id),'status':'absent'},self.staff)
        self.assertEqual(b2.right_state,'released')

    def test_cancellation_keeps_invoice_payment_and_right_snapshot(self):
        cls=self.create(kind='private',price='150.25');b=self.book(cls)
        invoice=m.Invoice.objects.get(booking_id=b.id)
        self.act('collect',{'invoiceId':str(invoice.id),'amount':'100','method':'pos'},self.staff)
        self.act('cancelClass',{'id':str(cls.id),'reason':'Class cancelled'})
        self.assertEqual(b.right_state,'released');self.assertEqual(debt(invoice),5025)
        self.assertEqual(m.Payment.objects.count(),1);self.assertEqual(invoice.total_cents,15025)
        payment=m.Payment.objects.get()
        self.act('refund',{'paymentId':str(payment.id),'amount':'100','reason':'Lesson refund'})
        self.act('cancelInvoice',{'invoiceId':str(invoice.id),'reason':'Lesson sale void','confirmed':True})
        self.assertEqual(debt(invoice),0);self.assertEqual(m.Refund.objects.count(),1)

    def test_private_without_membership_and_full_capacity(self):
        cls=self.create(kind='private',requireMembership=False,requireLesson=False,price='100')
        m.Subscription.objects.filter(member=self.member).update(status='cancelled')
        b=self.book(cls);self.assertIsNone(b.subscription_id)
        with self.assertRaises(RuleError):self.book(cls,self.other)
        self.assertEqual(m.Invoice.objects.filter(booking_id=b.id).count(),1)

    def test_time_change_keeps_booking_price_and_constraints(self):
        cls=self.create(price='200');b=self.book(cls)
        payload=snapshot(self.admin)['classes'][0]
        self.act('saveClass',{**payload,'id':str(cls.id),'at':(cls.at+timedelta(hours=1)).isoformat(),'price':'300'})
        self.assertEqual(b.terms['priceCents'],20000);self.assertEqual(m.Invoice.objects.get(booking_id=b.id).total_cents,20000)
        self.assertTrue(m.Notice.objects.filter(message__icontains='güncellendi').exists())

    def test_permissions_and_trainer_minimal_projection(self):
        cls=self.create();b=self.book(cls)
        with self.assertRaises(RuleError):self.act('cancelClass',{'id':str(cls.id),'reason':'No'},self.staff)
        with self.assertRaises(RuleError):self.act('book',{'classId':str(cls.id),'memberId':str(self.other.id)},self.trainer_user)
        db=snapshot(self.trainer_user)
        self.assertEqual(len(db['classes']),1);self.assertEqual(set(db['members'][0]),{'id','name','number'});self.assertEqual(db['payments'],[])
        cls.trainer_id=self.other_trainer.id;cls.at=timezone.now()-timedelta(minutes=5);cls.save()
        with self.assertRaises(RuleError):self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        m.RolePolicy.objects.create(branch_id=self.branch.id,role='staff',permissions={'classBooking':False})
        with self.assertRaises(RuleError):self.book(cls,self.other)

    def test_reminders_once_and_reload_persistence(self):
        cls=self.create(at=(timezone.now()+timedelta(hours=12)).isoformat());self.book(cls)
        self.assertEqual(self.act('classReminders',{})['result']['count'],1)
        self.assertEqual(self.act('classReminders',{})['result']['count'],0)
        self.client.force_login(self.admin)
        first=self.client.get('/api/v1/state/').json()['db'];second=self.client.get('/api/v1/state/').json()['db']
        self.assertEqual(first['bookings'],second['bookings']);self.assertEqual(first['classes'],second['classes'])
        self.assertTrue(all(n.channel=='panel' for n in m.Notice.objects.all()))

    def test_simultaneous_last_seat_is_one_booked_one_waiting(self):
        cls=self.create();get_session().commit();gate=Barrier(2);user_id=self.staff.id;cls_id=str(cls.id)
        def attempt(member_id):
            with SessionLocal() as session:
                token=active_session.set(session)
                try:
                    user=session.get(m.User,user_id);gate.wait(timeout=10)
                    response=execute('book',{'classId':cls_id,'memberId':member_id},user,uuid.uuid4());session.commit();return response['result']
                finally:active_session.reset(token)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[str(self.member.id),str(self.other.id)]))
        self.assertEqual(sorted(results),['booked','waiting']);get_session().expire_all()
        self.assertEqual(m.Booking.objects.filter(class_session=cls,status='booked').count(),1)

    def test_invalid_fields_and_all_series_rollback(self):
        for fields in [{'kind':'bad'},{'kind':'private','capacity':2},{'duration':0},{'requireMembership':False,'requireLesson':True},{'price':'0.001'}]:
            with self.assertRaises(RuleError):self.create(**fields)
        self.create(at=(timezone.now()+timedelta(days=9)).isoformat())
        with self.assertRaises(RuleError):self.create(repeatCount=3)
        self.assertEqual(m.ClassSession.objects.count(),1)

    def test_frozen_blocked_and_invalid_lesson_type(self):
        cls=self.create();sub=m.Subscription.objects.filter(member=self.member).first()
        sub.status='frozen';sub.save()
        with self.assertRaises(RuleError):self.book(cls)
        sub.status='active';sub.rules={**sub.rules,'lessonTypes':['private']};sub.save()
        with self.assertRaises(RuleError):self.book(cls)
        sub.rules={**sub.rules,'lessonTypes':['group']};sub.save();self.member.blocked=True;self.member.save()
        with self.assertRaises(RuleError):self.book(cls)

    def test_exhausted_gym_sessions_do_not_exhaust_lesson_rights(self):
        cls=self.create();sub=m.Subscription.objects.filter(member=self.member).first()
        sub.remaining=0;sub.total_sessions=10;sub.save()
        b=self.book(cls);self.assertEqual(b.right_state,'reserved');self.assertEqual(sub.remaining,0)

    def test_attendance_pending_and_excused_corrections_preserve_usage(self):
        cls=self.create();b=self.book(cls);cls.at=timezone.now()-timedelta(minutes=5);cls.save()
        self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        self.act('bookingStatus',{'id':str(b.id),'status':'excused','reason':'Medical reason'},self.trainer_user)
        self.act('bookingStatus',{'id':str(b.id),'status':'booked','reason':'Wrong selection'},self.trainer_user)
        self.assertEqual(b.right_state,'reserved');self.assertEqual(lesson_usage(b.subscription),1)
        self.act('bookingStatus',{'id':str(b.id),'status':'attended','reason':'Attendance verified'},self.trainer_user)
        self.assertEqual(lesson_usage(b.subscription),1)

    def test_attended_class_cannot_be_notheld_and_cancelled_membership_denies_attendance(self):
        cls=self.create();b=self.book(cls);cls.at=timezone.now()-timedelta(minutes=5);cls.save()
        b.subscription.status='cancelled';b.subscription.save()
        with self.assertRaises(RuleError):self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        b.subscription.status='active';b.subscription.save()
        self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        with self.assertRaises(RuleError):self.act('classOutcome',{'id':str(cls.id),'reason':'Not held'})
        self.assertEqual(b.status,'attended')

    def test_class_policy_and_member_endpoint_permissions_on_http(self):
        self.client.force_login(self.trainer_user)
        self.assertEqual(self.client.get('/api/v1/members/').status_code,403)
        cls=self.create();b=self.book(cls);cls.at=timezone.now()-timedelta(minutes=5);cls.save()
        self.act('saveRolePolicy',{'role':'trainer','permissions':{'classAttendance':False}})
        with self.assertRaises(RuleError):self.act('bookingStatus',{'id':str(b.id),'status':'attended'},self.trainer_user)
        self.act('saveRolePolicy',{'role':'staff','permissions':{'classBooking':False}})
        with self.assertRaises(RuleError):self.book(cls,self.other)

    def test_paid_lesson_optin_maintenance_order_and_dryrun(self):
        cls=self.create(price='25');b=self.book(cls)
        from app.services.maintenance import reset_members
        self.assertTrue(reset_members(str(self.branch.id),'fitgate_fastapi_test')['dryRun'])
        self.assertTrue(m.Invoice.objects.filter(booking_id=b.id).exists())
        reset_members(str(self.branch.id),'fitgate_fastapi_test',True)
        self.assertEqual(m.Booking.objects.count(),0);self.assertEqual(m.Invoice.objects.count(),0)
        self.assertTrue(m.ClassSession.objects.filter(pk=cls.id).exists())
