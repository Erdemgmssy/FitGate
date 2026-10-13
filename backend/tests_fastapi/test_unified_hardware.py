import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from app import models as m
from app.core import time as timezone
from app.services.business import execute, RuleError
from app.services.personnel import state
from app.services.dashboard import summary
from app.services.projection import snapshot
from tests_fastapi.support import TestCase


class UnifiedHardwareTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Unified hardware fixture')
        self.admin=m.User.objects.create_user(username='uh-admin@test.com',email='uh-admin@test.com',role='admin',branch=self.branch)
        self.worker=m.User.objects.create_user(username='uh-worker@test.com',email='uh-worker@test.com',role='staff',branch=self.branch)
        self.employee=m.Employee.objects.create(branch=self.branch,name='Fixture employee',user=self.worker,card='11223344')
        m.EmployeeCard.objects.create(branch_id=self.branch.id,employee=self.employee,uid='11223344')
        self.now=timezone.make_aware(datetime(2026,10,12,9,0))
        self.device=m.Device.objects.create(branch=self.branch,code='UH-TEST',purpose='mixed',sensor='ready',last_seen=self.now,telemetry={'firmware':'5','outsideCm':40,'insideCm':40},telemetry_at=self.now)
        self.plan=m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.employee,start=self.now,end=self.now+timedelta(hours=8),actor=self.admin)

    def act(self,action,payload,at=None,user=None,device=None,key=None):
        with patch('app.services.business.timezone.now',return_value=at or self.now):
            return execute(action,payload,user,key or uuid.uuid4(),device)

    def scan(self,direction,seconds=0):
        at=self.now+timedelta(seconds=seconds)
        self.device.last_seen=at; self.device.save()
        result=self.act('authorize',{'uid':'11223344','direction':direction},at,device=self.device)['result']
        self.assertTrue(result['approved'],result.get('reason'))
        return result

    def complete(self,result,seconds=1,key=None,event=None):
        at=self.now+timedelta(seconds=seconds)
        return self.act('confirmPassage',{'id':result['grantId'],'eventId':event or str(uuid.uuid4()),'direction':result['direction'],'occurredAt':at.isoformat()},at,device=self.device,key=key)['result']

    def intent(self,value,seconds=2):
        return self.act('physicalAttendanceIntent',{'intent':value},self.now+timedelta(seconds=seconds),self.worker)

    def test_one_scan_only_starts_shift_after_physical_entry(self):
        result=self.scan('entry')
        self.assertEqual(result['subjectType'],'employee'); self.assertEqual(m.Shift.objects.count(),0)
        self.assertEqual(m.PersonnelVisit.objects.count(),0)
        outcome=self.complete(result)
        self.assertEqual(outcome['message'],'MESAI BASLADI')
        self.assertEqual(m.Shift.objects.count(),1); self.assertEqual(m.Visit.objects.count(),0)
        event=m.AttendanceEvent.objects.get(); self.assertIsNotNone(event.passage_id)
        self.assertEqual(m.Shift.objects.get().planned_id,self.plan.id)

    def test_auto_personnel_direction_comes_from_open_visit(self):
        result=self.act('authorize',{'uid':'11223344','direction':'auto'},device=self.device)['result']
        self.assertTrue(result['approved']); self.assertEqual(result['direction'],'entry')
        self.complete(result)
        at=self.now+timedelta(seconds=15); self.device.last_seen=at; self.device.save()
        result=self.act('authorize',{'uid':'11223344','direction':'auto'},at,device=self.device)['result']
        self.assertTrue(result['approved']); self.assertEqual(result['direction'],'exit')
        self.assertIsNone(m.PersonnelVisit.objects.get().exit)
        self.complete(result,16)
        self.assertIsNotNone(m.PersonnelVisit.objects.get().exit)

    def test_servo_diagnostic_twenty_cm_is_occupied(self):
        self.device.telemetry['outsideCm']=20; self.device.save()
        with self.assertRaises(RuleError):
            self.act('queueDeviceDiagnostic',{'deviceId':str(self.device.id),'action':'servo','confirmed':True},user=self.admin)

    def test_break_exit_return_and_finish_only_on_confirmed_exit(self):
        self.complete(self.scan('entry')); shift=m.Shift.objects.get()
        self.intent('break',2); self.assertEqual(m.ShiftBreak.objects.count(),0)
        result=self.scan('exit',15); self.assertIsNone(shift.exit)
        self.assertEqual(self.complete(result,16)['message'],'MOLAYA CIKILDI')
        pause=m.ShiftBreak.objects.get(); self.assertIsNone(shift.exit)
        self.assertEqual(pause.start,self.now+timedelta(seconds=16))
        self.complete(self.scan('entry',30),31); pause.refresh_from_db(); self.assertEqual(pause.end,self.now+timedelta(seconds=31))
        self.intent('finish',32); self.assertIsNone(shift.exit)
        result=self.scan('exit',45); self.assertIsNone(shift.exit)
        self.assertEqual(self.complete(result,46)['message'],'MESAI BITTI')
        shift.refresh_from_db(); self.assertEqual(shift.exit,self.now+timedelta(seconds=46))
        self.assertEqual(m.Shift.objects.count(),1); self.assertEqual(m.PersonnelVisit.objects.count(),2)

    def test_timeout_does_not_start_shift_or_consume_finish_intent(self):
        self.scan('entry')
        self.assertEqual(m.Shift.objects.count(),0); self.assertEqual(m.PersonnelVisit.objects.count(),0)

    def test_finish_choice_without_passage_does_not_close_work(self):
        self.complete(self.scan('entry')); self.intent('finish',2); self.scan('exit',15)
        self.assertIsNone(m.Shift.objects.get().exit)
        self.assertIsNone(m.PersonnelVisit.objects.get().exit)
        self.assertEqual(self.employee.passage_intent['action'],'finish')
        result=self.scan('exit',60); self.complete(result,61)
        self.assertIsNotNone(m.Shift.objects.get().exit)

    def test_ambiguous_card_requires_explicit_context(self):
        member=m.Member.objects.create(branch=self.branch,name='Legacy dual profile',number='DUAL',phone='05329991122',normalized_phone='5329991122',created_by=self.admin)
        m.Card.objects.create(branch=self.branch,member=member,uid='11223344')
        with self.assertRaises(RuleError): self.scan('entry')
        self.device.credential_context='employee'; self.device.save()
        self.assertEqual(self.scan('entry')['subjectType'],'employee')

    def test_outside_schedule_presence_is_not_work(self):
        self.plan.start=self.now+timedelta(hours=1); self.plan.end=self.now+timedelta(hours=9); self.plan.save()
        self.complete(self.scan('entry'))
        self.assertEqual(m.PersonnelVisit.objects.count(),1); self.assertEqual(m.Shift.objects.count(),0)
        with self.assertRaises(RuleError): self.intent('start')

    def test_manual_start_when_auto_start_is_disabled(self):
        self.plan.auto_start=False; self.plan.save()
        self.complete(self.scan('entry')); self.assertEqual(m.Shift.objects.count(),0)
        self.intent('start'); self.assertEqual(m.Shift.objects.count(),1)

    def test_manual_presence_is_not_sensor_confirmation(self):
        self.act('correctPersonnelPresence',{'employeeId':str(self.employee.id),'deviceId':str(self.device.id),'direction':'entry','reason':'Forgotten card'},user=self.admin)
        with self.assertRaises(RuleError): self.intent('start')
        self.assertEqual(m.Shift.objects.count(),0)

    def test_legacy_attendance_cannot_bypass_firmware_five_passage(self):
        from app.services.personnel import record_attendance
        self.device.purpose='attendance'; self.device.save()
        with patch('app.services.personnel.timezone.now',return_value=self.now), self.assertRaises(RuleError):
            record_attendance('deviceAttendance',{'uid':'11223344'},None,self.branch,self.device)
        self.assertEqual(m.Shift.objects.count(),0)

    def test_other_personnel_attempts_are_not_exposed_to_worker(self):
        other=m.Employee.objects.create(branch=self.branch,name='Other employee',card='99887766')
        m.Attempt.objects.create(branch=self.branch,employee=other,device=self.device,card='99887766',status='rejected',reason='Fixture')
        self.assertEqual(len(snapshot(self.admin)['attempts']),1)
        self.assertEqual(len(snapshot(self.worker)['attempts']),0)

    def test_duplicate_event_and_second_scan_do_not_duplicate_shift(self):
        result=self.scan('entry'); key=uuid.uuid4(); event=str(uuid.uuid4())
        self.complete(result,key=key,event=event); self.complete(result,key=key,event=event)
        self.assertEqual(m.Passage.objects.count(),1); self.assertEqual(m.AttendanceEvent.objects.count(),1)
        self.assertEqual(m.Shift.objects.count(),1)
        result=self.act('authorize',{'uid':'11223344','direction':'entry'},self.now+timedelta(seconds=2),device=self.device)['result']
        self.assertFalse(result['approved'])

    def test_one_active_turnstile_operation_and_wrong_direction_rejected(self):
        result=self.scan('entry')
        response=self.act('authorize',{'uid':'55667788','direction':'entry'},device=self.device)['result']
        self.assertFalse(response['approved'])
        with self.assertRaises(RuleError):
            self.act('confirmPassage',{'id':result['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':self.now.isoformat(),'direction':'exit'},device=self.device)
        self.assertEqual(m.Passage.objects.count(),0)

    def test_return_to_same_finished_shift_does_not_start_again(self):
        self.complete(self.scan('entry')); self.intent('finish',2); self.complete(self.scan('exit',15),16)
        self.complete(self.scan('entry',30),31)
        self.assertEqual(m.Shift.objects.count(),1); self.assertIsNotNone(m.Shift.objects.get().exit)

    def test_unmarked_exit_becomes_absence_break_not_paid_work(self):
        self.branch.attendance_rules={'paidBreaks':True};self.branch.save()
        self.complete(self.scan('entry')); self.complete(self.scan('exit',15),16)
        self.assertEqual(m.ShiftBreak.objects.count(),1); self.assertFalse(m.ShiftBreak.objects.get().paid)
        self.assertIsNone(m.Shift.objects.get().exit)

    def test_explicit_paid_break_starts_only_on_physical_exit(self):
        self.branch.attendance_rules={'paidBreaks':True};self.branch.save()
        self.complete(self.scan('entry'));self.intent('break',2)
        self.assertEqual(m.ShiftBreak.objects.count(),0)
        self.complete(self.scan('exit',15),16)
        self.assertTrue(m.ShiftBreak.objects.get().paid)

    def test_dashboard_and_employee_scope_accept_personnel_events(self):
        self.complete(self.scan('entry'))
        with patch('app.services.business.timezone.now',return_value=self.now+timedelta(seconds=3)):
            self.assertEqual(summary(self.admin,self.now.date())['events'][0]['name'],self.employee.name)
            self.assertEqual(summary(self.admin,self.now.date())['metrics']['inside'],0)
            self.assertEqual(len(state(self.worker)['personnelVisits']),1)
            self.assertEqual(snapshot(self.admin)['devices'][0]['lastAttendance'],'MESAI BASLADI')
        with self.assertRaises(RuleError): self.act('correctPersonnelPresence',{'employeeId':str(self.employee.id),'direction':'exit','reason':'Other door'},self.now+timedelta(seconds=5),self.worker)
        self.act('correctPersonnelPresence',{'employeeId':str(self.employee.id),'direction':'exit','reason':'Other door'},self.now+timedelta(seconds=5),self.admin)
        self.assertIsNotNone(m.PersonnelVisit.objects.get().exit)

    def test_diagnostics_do_not_create_passage_or_attendance(self):
        result=self.act('queueDeviceDiagnostic',{'deviceId':str(self.device.id),'action':'lcd','confirmed':True},user=self.admin)['result']
        self.assertIsNotNone(result['id']); self.assertEqual(m.Passage.objects.count(),0); self.assertEqual(m.Shift.objects.count(),0)
        result=self.act('authorize',{'uid':'11223344','direction':'entry'},device=self.device)['result']
        self.assertFalse(result['approved'])

    def test_servo_diagnostic_requires_clear_fresh_sensors_and_admin(self):
        self.device.telemetry['outsideCm']=None; self.device.save()
        for user in [self.worker,self.admin]:
            with self.assertRaises(RuleError): self.act('queueDeviceDiagnostic',{'deviceId':str(self.device.id),'action':'servo','confirmed':True},user=user)
        self.assertEqual(m.DeviceCommand.objects.count(),0)
