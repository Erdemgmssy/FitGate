import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError
from app import models as m
from app.core import time as timezone
from app.core.security import check_password
from app.db.session import get_session
from app.services.business import execute, RuleError
from app.services.personnel import state, milliseconds
from app.services.projection import snapshot
from tests_fastapi.support import TestCase


class PersonnelTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Personnel test')
        self.admin=m.User.objects.create_user(username='admin@test.com',email='admin@test.com',password='LongTest123!',full_name='Admin',role='admin',branch=self.branch)
        self.staff=m.User.objects.create_user(username='staff@test.com',email='staff@test.com',password='LongTest123!',full_name='Staff',role='staff',branch=self.branch)
        self.act('saveEmployee',{'name':'Own employee','email':'staff@test.com','userId':str(self.staff.id),'role':'staff','type':'fixed','card':'OWN-CARD','startDate':'2020-01-01'})
        self.employee=m.Employee.objects.get()
        self.act('saveEmployee',{'name':'Other employee','role':'trainer','card':'OTHER-CARD','email':'other@test.com','createAccount':True,'password':'NewWorker123!','startDate':'2020-01-01'})
        self.other=m.Employee.objects.exclude(pk=self.employee.pk).get()
        self.act('saveRolePolicy',{'role':'staff','permissions':{'manualAttendance':True,'simulateAttendance':True}})

    def act(self,action,payload,user=None,key=None):
        return execute(action,payload,user or self.admin,key or uuid.uuid4())

    def at(self,hour,minute=0):
        return timezone.make_aware(datetime(2026,10,12,hour,minute))

    def attendance(self,direction,at,user=None,employee=None):
        with patch('app.services.personnel.timezone.now',return_value=at):
            return self.act('manualAttendance',{'employeeId':str((employee or self.employee).id),'direction':direction,'reason':'Test clock'},user or self.staff)['result']

    def test_account_creation_hash_and_branch_scope(self):
        self.assertTrue(check_password('NewWorker123!',self.other.user.password))
        self.assertTrue(self.other.user.password.startswith('$argon2'))
        self.assertEqual(self.other.user.role,'trainer')
        self.assertNotIn('NewWorker123!',json.dumps(snapshot(self.admin),default=str))
        self.assertNotIn('NewWorker123!',json.dumps([a.detail for a in m.Audit.objects.all()]))
        with self.assertRaises(RuleError): self.act('saveEmployee',{'name':'Weak','createAccount':True,'email':'weak@test.com','password':'short'})
        with self.assertRaises(RuleError): self.act('saveEmployee',{'name':'Other branch','branchId':str(uuid.uuid4())})

    def test_staff_only_own_records_and_admin_api_protection(self):
        self.attendance('entry',self.at(9))
        self.attendance('entry',self.at(9),self.admin,self.other)
        data=snapshot(self.staff)
        self.assertEqual([row['id'] for row in data['employees']],[str(self.employee.id)])
        self.assertEqual([row['employeeId'] for row in data['shifts']],[str(self.employee.id)])
        self.assertEqual(data['personnel']['accounts'],[])
        self.assertNotIn('hourlyRate',data['employees'][0])
        with self.assertRaises(RuleError): self.attendance('exit',self.at(18),self.staff,self.other)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post('/api/v1/actions/saveEmployee/',{'payload':{'name':'Forbidden'}},HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).status_code,403)
        self.assertEqual(len(self.client.get('/api/v1/personnel/').json()['shiftMetrics']),1)

    def test_role_permissions_and_trainer_login(self):
        self.act('saveRolePolicy',{'role':'staff','permissions':{'manualAttendance':False}})
        with self.assertRaises(RuleError): self.attendance('entry',self.at(9))
        with self.assertRaises(RuleError): self.act('saveRolePolicy',{'role':'staff','permissions':{'manageAllPersonnel':True}})
        with self.assertRaises(RuleError): self.act('saveRolePolicy',{'role':'admin','permissions':{}})
        self.client.force_login(self.other.user)
        self.assertEqual(self.client.get('/api/v1/personnel/').status_code,200)
        self.assertEqual(self.client.get('/api/v1/members/').status_code,403)
        with self.assertRaises(RuleError): self.act('addMember',{'name':'No'},self.other.user)

    def test_duplicate_scans_and_simulation_separation(self):
        at=self.at(9)
        with patch('app.services.personnel.timezone.now',return_value=at):
            key=uuid.uuid4(); payload={'uid':'OWN-CARD'}
            result=self.act('simulateAttendance',payload,self.staff,key)
            self.act('simulateAttendance',payload,self.staff,key)
            self.assertTrue(result['result']['approved'])
            self.assertFalse(self.act('simulateAttendance',payload,self.staff)['result']['approved'])
        self.assertEqual(m.Shift.objects.count(),1)
        self.assertTrue(m.Shift.objects.get().simulated)
        with patch('app.services.personnel.timezone.now',return_value=at+timedelta(hours=1)):
            self.assertFalse(self.act('manualAttendance',{'direction':'exit','reason':'Cannot mix'},self.staff)['result']['approved'])
            self.assertTrue(self.act('simulateAttendance',payload,self.staff)['result']['approved'])
        self.assertIsNotNone(m.Shift.objects.get().exit)
        with patch('app.services.personnel.settings.allow_device_simulation',False), self.assertRaises(RuleError): self.act('simulateAttendance',payload,self.staff)

    def test_unknown_revoked_and_member_cards_are_rejected(self):
        with patch('app.services.personnel.timezone.now',return_value=self.at(9)):
            self.assertFalse(self.act('simulateAttendance',{'uid':'UNKNOWN'},self.staff)['result']['approved'])
            card=m.EmployeeCard.objects.filter(employee=self.employee).get()
            self.act('employeeCardStatus',{'id':str(card.id),'status':'cancelled'})
            self.assertFalse(self.act('simulateAttendance',{'uid':'OWN-CARD'},self.staff)['result']['approved'])
        self.assertEqual(m.Shift.objects.count(),0)
        with self.assertRaises(RuleError): self.act('assignEmployeeCard',{'employeeId':str(self.other.id),'uid':'OWN-CARD'})
        with self.assertRaises(RuleError): self.act('assignCard',{'memberId':'none','uid':'OTHER-CARD'})
        self.assertEqual(m.AttendanceEvent.objects.count(),2)

    def test_night_shift_breaks_and_period_clipping(self):
        start=self.at(22); end=start+timedelta(hours=8)
        self.act('savePlannedShift',{'employeeId':str(self.employee.id),'start':start.isoformat(),'end':end.isoformat()})
        self.attendance('entry',start)
        with patch('app.services.personnel.timezone.now',return_value=start+timedelta(hours=2)):
            self.act('attendanceBreak',{'direction':'start'},self.staff)
            with self.assertRaises(RuleError): self.act('attendanceBreak',{'direction':'start'},self.staff)
        with patch('app.services.personnel.timezone.now',return_value=start+timedelta(hours=2,minutes=30)):
            self.act('attendanceBreak',{'direction':'end'},self.staff)
        self.attendance('exit',end)
        shift=m.Shift.objects.get()
        self.assertEqual(milliseconds(shift,start,end,end),7.5*3600000)
        midnight=start+timedelta(hours=2)
        self.assertEqual(milliseconds(shift,midnight,end,end),5.5*3600000)

    def test_plan_overlap_recurrence_and_absence(self):
        payload={'employeeId':str(self.employee.id),'start':self.at(9).isoformat(),'end':self.at(18).isoformat(),'repeatUntil':'2026-10-14','weekdays':[1,2,3]}
        result=self.act('savePlannedShift',payload)
        self.assertEqual(result['result']['count'],3)
        with self.assertRaises(RuleError): self.act('savePlannedShift',payload)
        with patch('app.services.personnel.timezone.now',return_value=self.at(19)):
            self.assertEqual(state(self.admin)['scheduleStatus'][0]['status'],'absent')
        self.assertEqual(m.PlannedShift.objects.count(),3)

    def test_late_overtime_and_missing_exit_use_rules(self):
        self.act('savePlannedShift',{'employeeId':str(self.employee.id),'start':self.at(9).isoformat(),'end':self.at(17).isoformat()})
        self.attendance('entry',self.at(9,10))
        self.attendance('exit',self.at(17,30))
        metric=state(self.admin)['shiftMetrics'][0]
        self.assertEqual(metric['lateMinutes'],5)
        self.assertEqual(metric['overtimeMinutes'],5)
        self.attendance('entry',self.at(18))
        with patch('app.services.personnel.timezone.now',return_value=self.at(18)+timedelta(hours=17)):
            self.assertTrue(any(row['missingExit'] for row in state(self.admin)['shiftMetrics']))

    def test_correction_audit_overlap_and_open_unique(self):
        self.attendance('entry',self.at(9))
        shift=m.Shift.objects.get()
        with self.assertRaises(IntegrityError), get_session().begin_nested():
            m.Shift.objects.create(branch=self.branch,employee=self.employee,entry=self.at(10))
        with self.assertRaises(RuleError): self.act('correctAttendance',{'id':str(shift.id),'exit':self.at(12).isoformat(),'reason':' '})
        self.act('correctAttendance',{'id':str(shift.id),'exit':self.at(12).isoformat(),'reason':'Forgot scan'})
        self.assertEqual(shift.exit,self.at(12))
        correction=m.Audit.objects.filter(type='correctAttendance').get()
        self.assertEqual(correction.actor_id,self.admin.id)
        self.assertIsNone(correction.before['exit'])
        self.assertEqual(correction.detail['reason'],'Forgot scan')

    def test_leave_quota_approval_history_and_scope(self):
        today=timezone.localdate(); first=today+timedelta(days=1)
        self.act('saveLeaveType',{'name':'Configured annual leave','annualDays':2,'serviceMonths':12,'weekdays':list(range(7))})
        kind=m.LeaveType.objects.get()
        self.act('requestLeave',{'typeId':str(kind.id),'start':str(first),'end':str(first+timedelta(days=1)),'reason':'Travel'},self.staff)
        leave=m.LeaveRequest.objects.get()
        with self.assertRaises(RuleError): self.act('reviewLeave',{'id':str(leave.id),'status':'approved','reason':'Yes'},self.staff)
        self.act('reviewLeave',{'id':str(leave.id),'status':'approved','reason':'Coverage arranged'})
        self.assertEqual(leave.status,'approved')
        self.assertEqual(leave.reviewer_id,self.admin.id)
        with self.assertRaises(RuleError): self.act('requestLeave',{'typeId':str(kind.id),'start':str(first+timedelta(days=3)),'end':str(first+timedelta(days=3)),'reason':'Extra'},self.staff)
        with self.assertRaises(RuleError): self.act('requestLeave',{'employeeId':str(self.other.id),'typeId':str(kind.id),'start':str(first),'end':str(first),'reason':'Not mine'},self.staff)
        with self.assertRaises(RuleError): self.act('savePlannedShift',{'employeeId':str(self.employee.id),'start':str(first)+'T09:00:00+03:00','end':str(first)+'T17:00:00+03:00'})
        self.assertEqual(len(state(self.staff)['leaveRequests']),1)

    def test_passive_employee_blocks_account_and_new_entry(self):
        self.attendance('entry',self.at(9))
        self.act('saveEmployee',{'id':str(self.employee.id),'active':False})
        self.assertFalse(self.staff.is_active)
        self.assertTrue(self.attendance('exit',self.at(18),self.admin)['approved'])
        self.assertFalse(self.attendance('entry',self.at(19),self.admin)['approved'])
        with self.assertRaises(RuleError): self.act('saveEmployee',{'name':'Self','role':'admin','userId':str(self.admin.id),'active':False})

    def test_legacy_device_without_firmware_cannot_create_unconfirmed_work(self):
        device=m.Device.objects.create(branch=self.branch,name='Test fixture device',code='ATT-TEST',purpose='attendance',last_seen=timezone.now())
        at=timezone.now()
        with self.assertRaises(RuleError):execute('scanEmployee',{'uid':'OWN-CARD','occurredAt':at.isoformat(),'direction':'entry'},None,uuid.uuid4(),device)
        self.assertEqual(m.Shift.objects.count(),0);self.assertEqual(m.AttendanceEvent.objects.count(),0)
