import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from app import models as m
from app.core import time as tz
from app.core.config import settings
from app.services.business import execute, RuleError
from app.services.dashboard import summary
from tests_fastapi.support import TestCase


class SingleSensorPrototypeTests(TestCase):
    def setUp(self):
        self.now=tz.now()
        self.branch=m.Branch.objects.create(name='Synthetic prototype fixture')
        self.admin=m.User.objects.create_user(username='prototype@example.com',email='prototype@example.com',role='admin',branch=self.branch)
        self.member=m.Member.objects.create(branch=self.branch,name='Synthetic member',number='PROTO-1',phone='+12025550101',normalized_phone='12025550101',created_by=self.admin)
        m.Card.objects.create(branch=self.branch,member=self.member,uid='FA000001')
        self.plan=m.Plan.objects.create(branch=self.branch,name='Synthetic seans',kind='sessions',sessions=3,price=1000,weekdays=list(range(7)),allowed_from='00:00',allowed_to='23:59')
        self.device=m.Device.objects.create(branch=self.branch,code='PROTO-TEST',purpose='mixed',sensor='ready',last_seen=self.now,
            telemetry={'firmware':'7','validationMode':'single_sensor_prototype'})
        self.flags=patch.multiple(settings,allow_single_sensor_prototype=True,single_sensor_prototype_device_code='PROTO-TEST',environment='development')
        self.flags.start(); self.addCleanup(self.flags.stop)
        self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id),'start':tz.localdate(self.now).isoformat()},user=self.admin)

    def act(self,action,p,seconds=0,user=None,key=None):
        with patch('app.services.business.timezone.now',return_value=self.now+timedelta(seconds=seconds)):
            return execute(action,p,user,key or uuid.uuid4(),self.device if user is None else None)['result']

    def scan(self,uid='FA000001',seconds=0):
        return self.act('authorize',{'uid':uid,'direction':'auto','validationMode':'single_sensor_prototype'},seconds)

    def event(self,grant,seconds=1,**overrides):
        return {'id':grant['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':(self.now+timedelta(seconds=seconds)).isoformat(),
                'direction':grant['direction'],'validationMode':'single_sensor_prototype','triggeringSensor':1,**overrides}

    def test_permission_environment_device_and_auto_direction_guards(self):
        for changes in [{'allow_single_sensor_prototype':False},{'environment':'production'},{'single_sensor_prototype_device_code':'OTHER'}]:
            with self.subTest(changes=changes),patch.multiple(settings,**changes),self.assertRaises(RuleError): self.scan()
        with self.assertRaises(RuleError): self.act('authorize',{'uid':'FA000001','direction':'entry','validationMode':'single_sensor_prototype'})
        self.assertEqual(m.Grant.objects.count(),0)

    def test_grant_only_then_either_sensor_duplicate_and_safe_exit_after_expiry(self):
        grant=self.scan(); self.assertEqual(grant['direction'],'entry')
        self.assertEqual(m.Visit.objects.count(),0)
        sub=m.Subscription.objects.get(); self.assertEqual(sub.remaining,3)
        payload=self.event(grant); key=uuid.uuid4()
        result=self.act('confirmPassage',payload,1,key=key)
        self.act('confirmPassage',payload,1,key=key)
        self.assertFalse(result['physicalVerified']); self.assertEqual(m.Passage.objects.count(),1)
        self.assertEqual(sub.remaining,2); self.assertEqual(m.Visit.objects.get().method,'Tek sensor prototipi')
        with self.assertRaises(RuleError): self.act('confirmPassage',self.event(grant),1)
        sub.status='cancelled'; sub.save()
        grant=self.scan(seconds=15); self.assertEqual(grant['direction'],'exit')
        self.assertTrue(grant['approved'],grant.get('reason'))
        self.act('confirmPassage',self.event(grant,16,triggeringSensor=0),16)
        self.assertIsNotNone(m.Visit.objects.get().exit); self.assertEqual(sub.remaining,2)

    def test_missing_sensor_mode_mismatch_timeout_and_no_grant_do_not_consume(self):
        grant=self.scan()
        for overrides in [{'triggeringSensor':None},{'triggeringSensor':True},{'validationMode':'two_sensor'},{'id':str(uuid.uuid4())}]:
            with self.subTest(fields=list(overrides)),self.assertRaises(RuleError):
                self.act('confirmPassage',self.event(grant,**overrides),1)
        with self.assertRaises(RuleError): self.act('confirmPassage',self.event(grant,31),31)
        self.assertEqual(m.Visit.objects.count(),0); self.assertEqual(m.Passage.objects.count(),0)
        self.assertEqual(m.Subscription.objects.get().remaining,3)

    def test_unknown_card_and_ambiguous_legacy_visit_denied(self):
        self.assertFalse(self.scan('FA000099')['approved'])
        m.Visit.objects.create(branch=self.branch,member=self.member,device=self.device,entry=self.now)
        with self.assertRaises(RuleError): self.scan()

    def test_authenticated_api_preserves_explicit_prototype_evidence_and_idempotency(self):
        from app.core.security import hash_password
        secret='synthetic-prototype-device-key'
        self.device.token_hash=hash_password(secret); self.device.save()
        headers={'HTTP_X_DEVICE_CODE':self.device.code,'HTTP_X_DEVICE_KEY':secret}
        response=self.client.post('/api/v1/device/access/authorize/',
            {'credential':'FA000001','direction':'auto','validationMode':'single_sensor_prototype'},
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),**headers)
        self.assertEqual(response.status_code,200)
        result=response.json()['result']; self.assertTrue(result['approved'])
        event={'grantId':result['grantId'],'eventId':str(uuid.uuid4()),'direction':result['direction'],
               'occurredAt':(datetime.fromisoformat(result['serverTime'])+timedelta(milliseconds=300)).isoformat(),
               'validationMode':'single_sensor_prototype','triggeringSensor':0}
        key=str(uuid.uuid4())
        for _ in range(2):
            response=self.client.post('/api/v1/device/passage-events/',event,HTTP_IDEMPOTENCY_KEY=key,**headers)
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()['result']['physicalVerified'])
        self.assertEqual(m.Passage.objects.count(),1); self.assertEqual(m.Subscription.objects.get().remaining,2)

    def test_prototype_is_not_labeled_full_physical_or_reported_as_such(self):
        grant=self.scan(); self.act('confirmPassage',self.event(grant),1)
        with patch('app.services.dashboard.timezone.now',return_value=self.now+timedelta(seconds=2)):
            data=summary(self.admin,tz.localdate(self.now))
        self.assertEqual(data['events'][0]['kind'],'prototype')
        from app.services.reports.operations import physical
        from app.services.reports.common import Filters, midnight
        from app.db.session import get_session
        day=tz.localdate(self.now)
        f=Filters(self.branch.id,day,day,midnight(day),midnight(day+timedelta(days=1)),self.now+timedelta(seconds=2),'visits')
        self.assertEqual(list(get_session().execute(physical(f))),[])
        # The dashboard evidence label is also stored immutably on Grant.
        self.assertEqual(m.Grant.objects.get().context['validationMode'],'single_sensor_prototype')

    def test_personnel_shift_break_return_and_finish_keep_business_rules(self):
        worker=m.User.objects.create_user(username='worker.prototype@example.com',email='worker.prototype@example.com',role='staff',branch=self.branch)
        employee=m.Employee.objects.create(branch=self.branch,user=worker,name='Synthetic worker',card='FB000001')
        m.EmployeeCard.objects.create(branch_id=self.branch.id,employee=employee,uid='FB000001')
        m.PlannedShift.objects.create(branch_id=self.branch.id,employee=employee,start=self.now,end=self.now+timedelta(hours=8),actor=self.admin)
        def complete(seconds):
            grant=self.scan('FB000001',seconds); self.act('confirmPassage',self.event(grant,seconds+1),seconds+1)
        complete(0); self.assertEqual(m.Shift.objects.count(),1)
        self.act('physicalAttendanceIntent',{'intent':'break'},2,user=worker)
        complete(15); self.assertEqual(m.ShiftBreak.objects.count(),1)
        complete(30); self.assertIsNotNone(m.ShiftBreak.objects.get().end)
        self.act('physicalAttendanceIntent',{'intent':'finish'},32,user=worker)
        complete(45); self.assertIsNotNone(m.Shift.objects.get().exit)
        self.assertTrue(all('prototipi' in row.message for row in m.AttendanceEvent.objects.all()))
