import uuid
from datetime import timedelta
from unittest.mock import patch
from app import models as m
from app.core import time as timezone
from app.services.business import execute, RuleError, member_debt
from app.services.membership import status, remaining_days, entry_sub
from app.services.projection import wire
from tests_fastapi.support import TestCase


class MembershipTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.branch = m.Branch.objects.create(name='Membership tests')
        self.admin = m.User.objects.create_user(username='admin@test.com', email='admin@test.com', password='LongTest123!', full_name='Admin', role='admin', branch=self.branch)
        self.staff = m.User.objects.create_user(username='staff@test.com', email='staff@test.com', password='LongTest123!', full_name='Staff', role='staff', branch=self.branch)
        self.plan = m.Plan.objects.create(branch=self.branch, name='Five sessions', price=1500, sessions=5, freeze_days=10, duration_value=30, weekdays=list(range(7)), allowed_from='00:00', allowed_to='23:59')
        self.act('addMember', {'name':'Member', 'phone':'05329998877', 'consent':True, 'planId':str(self.plan.id), 'uid':'TEST-CARD', 'paid':'500', 'method':'cash'})
        self.member = m.Member.objects.get()
        self.sub = m.Subscription.objects.get()
        self.device = m.Device.objects.create(branch=self.branch, name='Physical reader', code='REAL', sensor='ready', last_seen=timezone.now())

    def act(self, action, payload, user=None, key=None):
        return execute(action, payload, user or self.admin, key or uuid.uuid4())

    def scan(self, direction='entry'):
        return execute('authorize', {'uid':'TEST-CARD', 'deviceId':str(self.device.id), 'direction':direction}, None, uuid.uuid4(), device=self.device)['result']

    def confirm(self, grant, key=None):
        return execute('confirmPassage', {'id':grant['grantId'], 'eventId':str(uuid.uuid4())}, None, key or uuid.uuid4(), device=self.device)

    def freeze(self, start=None, end=None):
        return self.act('freeze', {'id':str(self.sub.id), 'start':str(start or self.today), 'end':str(end or self.today), 'reason':'Travel', 'actor':'Forged actor'})

    def test_session_snapshot_and_physical_confirmation_only(self):
        self.plan.sessions = 20
        self.plan.save()
        grant = self.scan()
        self.assertTrue(grant['approved'])
        self.assertEqual(wire(self.sub)['totalSessions'], 5)
        self.assertEqual(self.sub.remaining, 5)
        self.assertFalse(self.scan()['approved'])
        self.assertEqual(self.sub.remaining, 5)
        key = uuid.uuid4()
        payload = {'id':grant['grantId'], 'eventId':str(uuid.uuid4())}
        execute('confirmPassage', payload, None, key, device=self.device)
        execute('confirmPassage', payload, None, key, device=self.device)
        self.assertEqual(self.sub.remaining, 4)
        self.assertEqual(wire(self.sub)['usedSessions'], 1)
        self.assertEqual(m.Audit.objects.filter(type='sessionUsed').count(), 1)
        self.assertEqual(m.Visit.objects.count(), 1)

    def test_freeze_dates_quota_actor_and_automatic_end(self):
        first = self.today + timedelta(days=2)
        last = first + timedelta(days=2)
        old_end = self.sub.end
        self.freeze(first, last)
        self.assertEqual(self.sub.end, old_end+timedelta(days=3))
        self.assertEqual(self.sub.frozen_days, 3)
        self.assertEqual(status(self.sub, self.today), 'active')
        self.assertEqual(status(self.sub, first), 'frozen')
        self.assertEqual(status(self.sub, last), 'frozen')
        self.assertEqual(status(self.sub, last+timedelta(days=1)), 'active')
        self.assertEqual(remaining_days(self.sub, first), remaining_days(self.sub, last))
        self.assertEqual(remaining_days(self.sub, self.today), (old_end-self.today).days+1)
        self.assertEqual(m.Freeze.objects.get().actor_id, self.admin.id)
        self.assertEqual(m.Audit.objects.filter(type='freeze').count(), 1)
        with self.assertRaises(RuleError): self.freeze()

    def test_early_resume_restores_unused_quota(self):
        old_end = self.sub.end
        self.freeze(end=self.today+timedelta(days=4))
        with patch('app.services.business.timezone.localdate', return_value=self.today+timedelta(days=2)):
            self.act('resume', {'id':str(self.sub.id)})
        self.assertEqual(self.sub.end, old_end+timedelta(days=2))
        self.assertEqual(self.sub.frozen_days, 2)
        self.assertEqual(m.Freeze.objects.get().end, self.today+timedelta(days=2))

    def test_pending_freeze_can_be_cancelled_and_replaced(self):
        old_end = self.sub.end
        self.freeze(self.today+timedelta(days=2), self.today+timedelta(days=3))
        self.act('resume', {'id':str(self.sub.id)})
        self.assertEqual(self.sub.end, old_end)
        self.assertEqual(self.sub.frozen_days, 0)
        self.freeze()
        self.assertEqual(status(self.sub), 'frozen')

    def test_invalid_freeze_and_staff_permissions(self):
        for start, end in [(self.today-timedelta(days=1),self.today), (self.today,self.today-timedelta(days=1)), (self.today,self.today+timedelta(days=10))]:
            with self.subTest(start=start, end=end), self.assertRaises(RuleError): self.freeze(start,end)
        with self.assertRaises(RuleError): self.act('freeze', {'id':str(self.sub.id),'start':str(self.today),'end':str(self.today),'reason':' '})
        with self.assertRaises(RuleError): self.act('freeze', {'id':str(self.sub.id),'start':str(self.today),'end':str(self.today),'reason':'Travel'},self.staff)
        self.assertEqual(self.sub.frozen_days, 0)

    def test_cancel_requires_confirmation_and_preserves_finances(self):
        before = member_debt(self.member)
        invoice = m.Invoice.objects.get()
        for payload in [{'reason':'Travel'}, {'confirmed':True,'reason':' '}]:
            with self.assertRaises(RuleError): self.act('cancelSubscription', {'id':str(self.sub.id),**payload})
        self.act('cancelSubscription', {'id':str(self.sub.id),'confirmed':True,'reason':'Closed'})
        self.assertEqual(member_debt(self.member), before)
        self.assertNotEqual(invoice.status, 'cancelled')
        self.assertEqual(m.Payment.objects.count(), 1)
        self.assertEqual(m.Installment.objects.count(), 1)
        self.assertEqual(m.Audit.objects.filter(type='cancelSubscription').count(), 1)

    def test_renew_preserves_history_net_price_and_idempotency(self):
        old = wire(self.sub)
        key = uuid.uuid4()
        payload = {'memberId':str(self.member.id),'planId':str(self.plan.id),'start':str(self.sub.end+timedelta(days=1)), 'discount':'100', 'paid':'200', 'method':'pos','installments':2}
        self.act('renew',payload,key=key)
        self.act('renew',payload,key=key)
        self.assertEqual(m.Subscription.objects.count(), 2)
        self.assertEqual(wire(self.sub), old)
        new = m.Subscription.objects.exclude(pk=self.sub.pk).get()
        self.assertEqual(wire(new)['salePriceCents'], 140000)
        self.assertEqual(status(new), 'pending')
        self.assertEqual(m.Invoice.objects.count(), 2)
        self.assertEqual(m.Installment.objects.count(), 3)
        self.assertEqual(member_debt(self.member), 220000)
        self.assertEqual(m.Audit.objects.filter(type='renew').count(), 1)

    def test_multiple_packages_skip_exhausted_and_restricted(self):
        self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id),'start':str(self.today+timedelta(days=1))})
        other = m.Subscription.objects.exclude(pk=self.sub.pk).get()
        other.start = self.today
        other.save()
        self.assertEqual(entry_sub(self.member,timezone.now()).id,self.sub.id)
        self.sub.remaining = 0
        self.sub.save()
        self.assertEqual(entry_sub(self.member,timezone.now()).id,other.id)
        self.sub.remaining = 5
        self.sub.rules = {**self.sub.rules,'weekdays':[]}
        self.sub.save()
        self.assertEqual(entry_sub(self.member,timezone.now()).id,other.id)

    def test_any_frozen_package_blocks_entry_without_consuming_sessions(self):
        self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id)})
        self.freeze()
        self.assertFalse(self.scan()['approved'])
        self.assertEqual(self.sub.remaining,5)

    def test_freeze_after_permission_rolls_back_physical_event(self):
        grant = self.scan()
        self.freeze()
        with self.assertRaises(RuleError): self.confirm(grant)
        self.assertEqual(m.Visit.objects.count(),0)
        self.assertEqual(m.Passage.objects.count(),0)
        self.assertEqual(self.sub.remaining,5)

    def test_expired_frozen_cancelled_members_can_exit(self):
        for condition in ['expired','frozen','cancelled']:
            with self.subTest(condition=condition):
                visit=m.Visit.objects.create(branch=self.branch,member=self.member,device=self.device,entry=timezone.now()-timedelta(minutes=1))
                self.sub.status='active'
                self.sub.end=self.today+timedelta(days=30)
                if condition=='expired':
                    self.sub.start=self.today-timedelta(days=30)
                    self.sub.end=self.today-timedelta(days=1)
                elif condition=='frozen': self.sub.status='frozen'
                else: self.sub.status='cancelled'
                self.sub.save()
                m.Attempt.objects.all().update(at=timezone.now()-timedelta(seconds=20))
                grant=self.scan('exit')
                self.assertTrue(grant['approved'])
                self.confirm(grant)
                self.assertIsNotNone(visit.exit)
                self.assertEqual(self.sub.remaining,5)

    def test_date_and_session_limits_are_independent(self):
        self.sub.start=self.today-timedelta(days=30)
        self.sub.end=self.today-timedelta(days=1)
        self.sub.save()
        self.assertFalse(self.scan()['approved'])
        self.assertEqual(self.sub.remaining,5)
        self.sub.end=self.today+timedelta(days=1)
        self.sub.remaining=0
        self.sub.save()
        m.Attempt.objects.all().update(at=timezone.now()-timedelta(seconds=20))
        self.assertIn('Seans',self.scan()['reason'])

    def test_unlimited_and_legacy_freeze(self):
        self.sub.remaining=None
        self.sub.total_sessions=None
        self.sub.save()
        self.assertIsNone(wire(self.sub)['usedSessions'])
        self.confirm(self.scan())
        self.assertIsNone(self.sub.remaining)
        old_end=self.sub.end
        self.sub.status='frozen'
        self.sub.frozen_at=self.today-timedelta(days=2)
        self.sub.save()
        m.Freeze.objects.create(branch=self.branch,subscription=self.sub,start=self.sub.frozen_at,reason='Legacy',actor=self.admin)
        self.act('resume',{'id':str(self.sub.id)})
        self.assertEqual(self.sub.end,old_end+timedelta(days=2))
