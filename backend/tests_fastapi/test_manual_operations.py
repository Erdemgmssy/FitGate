import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from app.db.session import get_session, SessionLocal, active_session
from app import models as m
from app.core import time as tz
from app.core.config import settings
from app.services.business import execute, RuleError
from app.services.dashboard import summary
from app.services.reports import build
from app.services.personnel import milliseconds
from tests_fastapi.support import TestCase

class ManualOperationsTests(TestCase):
    def setUp(self):
        self.now=tz.make_aware(datetime(2026,10,13,12))
        self.branch=m.Branch.objects.create(name='Manual synthetic test')
        self.admin=m.User.objects.create_user(username='admin@example.test',email='admin@example.test',branch=self.branch,role='admin',full_name='Test admin')
        self.staff=m.User.objects.create_user(username='staff@example.test',email='staff@example.test',branch=self.branch,role='staff',full_name='Test staff')
        self.member=m.Member.objects.create(branch=self.branch,name='Synthetic member',number='MAN-1',created_by=self.admin)
        self.plan=m.Plan.objects.create(branch=self.branch,name='Test sessions',kind='sessions',sessions=3,price=100,
            weekdays=list(range(7)),allowed_from='00:00',allowed_to='23:59')
        self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id),'start':'2026-10-13'})
        self.sub=m.Subscription.objects.get()
        self.employee=m.Employee.objects.create(branch=self.branch,user=self.staff,name='Synthetic employee')
        self.other=m.Employee.objects.create(branch=self.branch,name='Other synthetic employee')
        self.act('saveRolePolicy',{'role':'staff','permissions':{'manualVisits':True,'manualAttendance':True}})
        self.device=m.Device.objects.create(branch=self.branch,code='MANUAL-TEST',sensor='ready',last_seen=self.now)
        m.Card.objects.create(branch=self.branch,member=self.member,uid='FA000001')

    def act(self,action,p=None,user=None,seconds=0,key=None,device=None):
        with patch('app.core.time.now',return_value=self.now+timedelta(seconds=seconds)):
            return execute(action,p or {},None if device else user or self.admin,key or uuid.uuid4(),device)

    def member_action(self,action='manualMemberEntry',seconds=0,user=None,**extra):
        return self.act(action,{'memberId':str(self.member.id),'confirmed':True,'reason':'Human verified test',**extra},user,seconds)

    def plan_shift(self,start=None,end=None):
        return m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.employee,
            start=start or self.now-timedelta(hours=1),end=end or self.now+timedelta(hours=8),actor=self.admin)

    def personnel(self,operation,seconds=0,user=None,employee=None,**extra):
        return self.act('manualPersonnelOperation',{'employeeId':str((employee or self.employee).id),
            'operation':operation,'confirmed':True,'reason':'Device unavailable test',**extra},user or self.staff,seconds)

    def test_offline_entry_and_exit_are_human_only_and_single_session(self):
        self.device.enabled=False; self.device.save()
        self.member_action(user=self.staff)
        visit=m.Visit.objects.get(); self.assertIsNone(visit.device_id); self.assertIsNone(visit.entry_event_id)
        self.assertEqual(visit.method,'MANUAL'); self.assertEqual(visit.entry_actor_id,self.staff.id)
        self.assertEqual(self.sub.remaining,2)
        with self.assertRaises(RuleError): self.member_action()
        self.sub.status='cancelled';self.sub.save()
        self.member_action('manualMemberExit',1,user=self.staff)
        self.assertEqual(visit.exit_method,'MANUAL'); self.assertEqual(self.sub.remaining,2)
        with self.assertRaises(RuleError): self.member_action('manualMemberExit',2)
        self.assertEqual(m.Passage.objects.count(),0);self.assertEqual(m.DeviceCommand.objects.count(),0)
        self.assertEqual(m.Attempt.objects.count(),0)

    def test_confirmation_reason_and_role_are_required(self):
        for p in [{'confirmed':False},{'reason':''},{'reason':'x'*601}]:
            with self.subTest(p=list(p)),self.assertRaises(RuleError): self.member_action(**p)
        self.act('saveRolePolicy',{'role':'staff','permissions':{'manualVisits':False}})
        with self.assertRaises(RuleError): self.member_action(user=self.staff)
        with self.assertRaises(RuleError): self.member_action('adminManualEntryOverride',user=self.staff,acknowledgeException=True)
        self.assertEqual(self.sub.remaining,3)

    def test_invalid_frozen_blocked_and_missing_membership_rejected(self):
        for value in ['cancelled','frozen']:
            self.sub.status=value; self.sub.save()
            with self.subTest(status=value),self.assertRaises(RuleError):self.member_action()
        self.sub.status='active';self.sub.start=tz.localdate(self.now)-timedelta(days=10);self.sub.end=tz.localdate(self.now)-timedelta(days=1);self.sub.save()
        with self.assertRaises(RuleError):self.member_action()
        self.sub.end=None;self.sub.save();self.member.blocked=True;self.member.save()
        with self.assertRaises(RuleError):self.member_action()
        self.member.blocked=False;self.member.save();self.sub.start=tz.localdate(self.now)+timedelta(days=1);self.sub.save()
        with self.assertRaises(RuleError):self.member_action()
        self.assertEqual(m.Visit.objects.count(),0);self.assertEqual(self.sub.remaining,3)

    def test_daily_limit_hours_debt_and_capacity_apply(self):
        self.sub.rules={**self.sub.rules,'dailyLimit':1};self.sub.save()
        self.member_action();self.member_action('manualMemberExit',1)
        with self.assertRaisesRegex(RuleError,'Günlük'):self.member_action(seconds=20)
        self.sub.rules={**self.sub.rules,'dailyLimit':None,'from':'13:00','to':'14:00'};self.sub.save()
        with self.assertRaises(RuleError):self.member_action(seconds=20)
        self.sub.rules={**self.sub.rules,'from':'00:00','to':'23:59'};self.sub.save()
        self.branch.debt_block=True;self.branch.save()
        with self.assertRaisesRegex(RuleError,'Borç'):self.member_action(seconds=20)
        self.branch.debt_block=False;self.branch.capacity=0;self.branch.save()
        with self.assertRaisesRegex(RuleError,'Kapasite'):self.member_action(seconds=20)

    def test_admin_exception_is_explicit_without_activating_subscription(self):
        self.sub.status='cancelled';self.sub.save();self.member.blocked=True;self.member.save()
        with self.assertRaises(RuleError):self.member_action('adminManualEntryOverride')
        self.member_action('adminManualEntryOverride',acknowledgeException=True)
        self.assertEqual(self.sub.status,'cancelled');self.assertEqual(self.sub.remaining,3)
        self.assertIsNone(m.Visit.objects.get().subscription_id)
        self.assertTrue(m.Audit.objects.get(type='adminManualEntryOverride').detail['exception'])

    def test_idempotency_preserves_visit_session_and_audit(self):
        p={'memberId':str(self.member.id),'confirmed':True,'reason':'Repeat test'};key=uuid.uuid4()
        first=self.act('manualMemberEntry',p,key=key)
        self.assertEqual(self.act('manualMemberEntry',p,key=key),first)
        self.assertEqual(m.Visit.objects.count(),1);self.assertEqual(self.sub.remaining,2)
        self.assertEqual(m.Audit.objects.filter(type='manualMemberEntry').count(),1)
        with self.assertRaises(RuleError):self.act('manualMemberEntry',{**p,'reason':'Changed'},key=key)

    def test_unlimited_and_no_subscription(self):
        other=m.Member.objects.create(branch=self.branch,name='No package',number='MAN-2',normalized_phone='12025550102',created_by=self.admin)
        with self.assertRaises(RuleError):self.member_action(memberId=str(other.id))
        self.sub.remaining=None;self.sub.total_sessions=None;self.sub.save()
        self.member_action();self.assertIsNone(self.sub.remaining)
        self.assertFalse(m.Audit.objects.filter(type='sessionUsed').exists())

    def test_pending_rfid_blocks_manual_and_later_exit_can_be_manual(self):
        grant=self.act('authorize',{'uid':'FA000001','direction':'entry'},device=self.device)['result']
        self.assertTrue(grant['approved'],grant)
        with self.assertRaisesRegex(RuleError,'Bekleyen'):self.member_action()
        self.act('confirmPassage',{'id':grant['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':(self.now+timedelta(seconds=1)).isoformat()},seconds=1,device=self.device)
        self.member_action('manualMemberExit',2)
        self.assertEqual(m.Visit.objects.count(),1);self.assertEqual(self.sub.remaining,2)
        self.assertEqual(m.Visit.objects.get().exit_method,'MANUAL')

    def test_manual_first_duplicate_scan_and_real_exit_after_reconnect(self):
        self.member_action()
        denied=self.act('authorize',{'uid':'FA000001','direction':'auto'},device=self.device)['result']
        self.assertFalse(denied['approved'])
        attempt=m.Attempt.objects.get();attempt.at=self.now;attempt.save()
        self.sub.status='cancelled';self.sub.save()
        grant=self.act('authorize',{'uid':'FA000001','direction':'auto'},seconds=11,device=self.device)['result']
        self.assertTrue(grant['approved'],grant);self.assertEqual(grant['direction'],'exit')
        self.act('confirmPassage',{'id':grant['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':(self.now+timedelta(seconds=12)).isoformat()},seconds=12,device=self.device)
        self.assertEqual(m.Visit.objects.get().exit_method,'RFID');self.assertEqual(self.sub.remaining,2)

    def test_prototype_recognizes_authorized_manual_open_visit(self):
        self.member_action();self.device.telemetry={'firmware':'7','validationMode':'single_sensor_prototype'};self.device.save()
        with patch.multiple(settings,allow_single_sensor_prototype=True,single_sensor_prototype_device_code=self.device.code,environment='development'):
            grant=self.act('authorize',{'uid':'FA000001','direction':'auto','validationMode':'single_sensor_prototype'},seconds=11,device=self.device)['result']
            self.assertTrue(grant['approved'],grant);self.assertEqual(grant['direction'],'exit')

    def test_manual_correction_preserves_audit_and_balance(self):
        self.member_action();visit=m.Visit.objects.get()
        original=visit.entry
        p={'id':str(visit.id),'confirmed':True,'reason':'Correct clock','entry':(original-timedelta(minutes=1)).isoformat(),'exit':None}
        with self.assertRaises(RuleError):self.act('correctManualVisit',p,user=self.staff)
        self.act('correctManualVisit',p)
        self.assertEqual(visit.method,'ADMIN_CORRECTION');self.assertEqual(self.sub.remaining,2)
        audit=m.Audit.objects.get(type='correctManualVisit');self.assertEqual(audit.before['entry'],original.isoformat())
        with self.assertRaises(RuleError):self.act('correctManualVisit',{**p,'entry':(original+timedelta(hours=1)).isoformat()})

    def test_dashboard_and_reports_keep_physical_statistics_separate(self):
        self.member_action()
        with patch('app.core.time.now',return_value=self.now+timedelta(minutes=1)):
            data=summary(self.admin,tz.localdate(self.now));self.assertEqual(data['metrics']['inside'],1)
            self.assertEqual(data['metrics']['entries'],0);self.assertEqual(data['metrics']['manualEntries'],1)
            self.assertEqual(data['events'][0]['kind'],'manual')
            data=build(self.admin,{'tab':'visits','from':'2026-10-13','to':'2026-10-13','type':'manual'})
            self.assertEqual(data['table']['count'],1)
            values={r['key']:r['value'] for r in data['metrics']};self.assertEqual(values['manualEntry'],1)
            self.assertEqual(values['manualInside'],1)

    def test_personnel_four_steps_night_shift_and_unpaid_break(self):
        self.now=tz.make_aware(datetime(2026,10,13,23))
        self.plan_shift(end=self.now+timedelta(hours=7))
        self.personnel('start');shift=m.Shift.objects.get()
        with self.assertRaises(RuleError):self.personnel('start',1)
        self.personnel('break',3600)
        with self.assertRaises(RuleError):self.personnel('break',3601)
        self.personnel('resume',5400);self.personnel('finish',10800)
        self.assertEqual(milliseconds(shift,self.now,self.now+timedelta(hours=3)),9000000)
        self.assertEqual(m.AttendanceEvent.objects.filter(source='MANUAL_PERSONNEL').count(),4)
        self.assertEqual(m.PersonnelVisit.objects.count(),0);self.assertEqual(m.Passage.objects.count(),0)
        self.assertEqual(shift.source,'MANUAL_PERSONNEL')

    def test_personnel_no_plan_foreign_record_and_permissions(self):
        with self.assertRaises(RuleError):self.personnel('start')
        self.plan_shift()
        with self.assertRaises(RuleError):self.personnel('start',employee=self.other)
        self.personnel('start')
        self.act('saveRolePolicy',{'role':'staff','permissions':{'manualAttendance':False}})
        with self.assertRaises(RuleError):self.personnel('finish',1)

    def test_personnel_paid_break_and_report_agree(self):
        self.plan_shift();self.branch.attendance_rules={'paidBreaks':True};self.branch.save()
        self.personnel('start');self.personnel('break',3600);self.personnel('resume',5400);self.personnel('finish',10800)
        with patch('app.core.time.now',return_value=self.now+timedelta(hours=4)):
            data=build(self.admin,{'tab':'personnel','from':'2026-10-13','to':'2026-10-13'})
        values={r['key']:r['value'] for r in data['metrics']};self.assertEqual(values['hours'],3)
        self.assertTrue(m.ShiftBreak.objects.get().paid)

    def test_manual_correction_cannot_overlap_or_replace_device_history(self):
        self.member_action();visit=m.Visit.objects.get()
        visit.exit=self.now+timedelta(seconds=1);visit.exit_method='MANUAL';visit.save()
        other=m.Visit.objects.create(branch=self.branch,member=self.member,entry=self.now+timedelta(seconds=2),method='MANUAL',entry_actor=self.admin)
        p={'id':str(visit.id),'confirmed':True,'reason':'Overlap test','entry':visit.entry.isoformat(),'exit':None}
        with self.assertRaises(RuleError):self.act('correctManualVisit',p,seconds=5)
        self.assertIsNotNone(visit.exit);self.assertIsNone(other.exit)

    def test_manual_finish_device_shift_closes_break_not_physical_presence(self):
        shift=m.Shift.objects.create(branch=self.branch,employee=self.employee,entry=self.now-timedelta(hours=1),source='device')
        self.personnel('break');self.personnel('finish',60)
        self.assertIsNotNone(shift.exit);self.assertIsNotNone(m.ShiftBreak.objects.get().end)
        self.assertEqual(shift.source,'device');self.assertEqual(m.PersonnelVisit.objects.count(),0)

    def test_cross_branch_and_api_permissions(self):
        branch=m.Branch.objects.create(name='Other branch')
        other=m.Member.objects.create(branch=branch,name='Other member',number='O-1',created_by=self.admin)
        with self.assertRaises(RuleError):self.member_action(memberId=str(other.id))
        self.client.force_login(self.staff)
        response=self.client.post('/api/v1/actions/manualMemberEntry/',{'payload':{'memberId':str(self.member.id),'confirmed':False,'reason':'Test'}},HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertIn(response.status_code,[400,422]);self.assertEqual(m.Visit.objects.count(),0)

    def test_migration_downgrade_refuses_to_discard_new_provenance(self):
        import importlib.util
        from pathlib import Path
        path=Path(__file__).resolve().parents[1]/'alembic/versions/b821d74ea39c_manual_operations.py'
        spec=importlib.util.spec_from_file_location('manual_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        self.member_action()
        with patch.object(migration.op,'get_bind',return_value=get_session().connection()),self.assertRaises(RuntimeError):
            migration.downgrade()
        self.assertEqual(m.Visit.objects.count(),1);self.assertEqual(self.sub.remaining,2)

    def test_http_entry_reload_and_exit_provenance(self):
        self.client.force_login(self.staff)
        p={'payload':{'memberId':str(self.member.id),'confirmed':True,'reason':'HTTP operator confirmation'}}
        response=self.client.post('/api/v1/actions/manualMemberEntry/',p,HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200,response.text)
        visit=response.json()['db']['visits'][0]
        self.assertEqual(visit['method'],'MANUAL');self.assertEqual(visit['entryActor'],'Test staff')
        state=self.client.get('/api/v1/state/');self.assertEqual(state.status_code,200)
        self.assertEqual(state.json()['db']['visits'][0]['id'],visit['id'])
        response=self.client.post('/api/v1/actions/manualMemberExit/',p,HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['db']['visits'][0]['exitMethod'],'MANUAL')
        self.assertEqual(self.sub.remaining,2)

    def test_concurrent_rfid_and_manual_entry_serialized_by_branch(self):
        self.device.last_seen=tz.now();self.device.save()
        get_session().commit();gate=Barrier(2)
        user_id=self.admin.id;device_id=self.device.id;member_id=str(self.member.id)
        def attempt(kind):
            with SessionLocal() as session:
                token=active_session.set(session)
                try:
                    user=session.get(m.User,user_id);device=session.get(m.Device,device_id);gate.wait(timeout=10)
                    if kind=='manual':
                        response=execute('manualMemberEntry',{'memberId':member_id,'confirmed':True,'reason':'Concurrent test'},user,uuid.uuid4())
                    else:
                        response=execute('authorize',{'uid':'FA000001','direction':'entry'},None,uuid.uuid4(),device)
                    session.commit()
                    return response['result'].get('approved',True)
                except RuleError:session.rollback();return False
                finally:active_session.reset(token)
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(attempt,['manual','rfid']))
        self.assertEqual(sorted(outcomes),[False,True]);get_session().expire_all()
        self.assertLessEqual(m.Visit.objects.filter(exit__isnull=True).count(),1)
        self.assertEqual(m.Visit.objects.count()+m.Grant.objects.filter(confirmed=False).count(),1)
        self.assertIn(self.sub.remaining,[2,3])
