import uuid
from datetime import timedelta,datetime
from unittest.mock import patch
from app import models as m
from app.core import time as tz
from app.core.security import check_password,digest
from app.db.session import get_session
from app.services.business import execute,RuleError
from app.services.system_settings import state,open_for_entry,DEFAULT_NOTIFICATIONS
from app.services.notifications import sync
from app.services.projection import snapshot
from tests_fastapi.support import TestCase

class SystemSettingsTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Gym')
        self.admin=m.User.objects.create_user(branch=self.branch,username='settings@test.com',email='settings@test.com',role='admin',password='OldPassword123!')
        self.staff=m.User.objects.create_user(branch=self.branch,username='staff@test.com',email='staff@test.com',role='staff',password='StaffPassword123!')
        self.other=m.Branch.objects.create(name='Other')
    def action(self,action,p,user=None):return execute(action,p,user or self.admin,uuid.uuid4())
    def test_profile_validation_persistence_and_branch_scope(self):
        payload={'name':'Updated Gym','phone':'05321112233','email':'info@gym.test','address':'Address','logo':'','confirmed':True}
        self.action('saveBranchProfile',payload)
        get_session().refresh(self.branch);self.assertEqual(state(self.admin)['profile']['name'],'Updated Gym');self.assertEqual(self.other.name,'Other')
        with self.assertRaises(RuleError):self.action('saveBranchProfile',{**payload,'email':'broken'})
        with self.assertRaises(RuleError):self.action('saveBranchProfile',{**payload,'confirmed':False})
        with self.assertRaises(RuleError):self.action('saveBranchProfile',payload,self.staff)
        self.assertEqual(m.Audit.objects.filter(type='saveBranchProfile').count(),1)
    def test_overnight_days_closures_and_opt_in_schedule(self):
        at=tz.make_aware(datetime(2026,10,12,23,0)) # Monday
        self.assertTrue(open_for_entry(self.branch,at))
        self.action('saveOpeningHours',{'enforced':True,'from':'22:00','to':'02:00','days':[1],'closures':[],'confirmed':True})
        self.assertTrue(open_for_entry(self.branch,at));self.assertTrue(open_for_entry(self.branch,at+timedelta(hours=2)))
        self.assertFalse(open_for_entry(self.branch,at+timedelta(hours=3)))
        self.branch.configuration={**self.branch.configuration,'opening':{**self.branch.configuration['opening'],'closures':['2026-10-13']}};self.branch.save()
        self.assertFalse(open_for_entry(self.branch,at+timedelta(hours=2)))
        with self.assertRaises(RuleError):self.action('saveOpeningHours',{'enforced':True,'from':'22:00','to':'22:00','days':[1],'closures':[],'confirmed':True})
    def test_last_admin_protected_in_account_and_employee_flows(self):
        with self.assertRaises(RuleError):self.action('manageAccount',{'id':self.admin.id,'operation':'update','active':False,'role':'admin','reason':'Disable','confirmed':True})
        employee=m.Employee.objects.create(branch=self.branch,user=self.admin,name='Owner',role='admin')
        with self.assertRaises(RuleError):self.action('saveEmployee',{'id':str(employee.id),'role':'staff'})
        self.assertTrue(self.admin.is_active);self.assertEqual(self.admin.role,'admin')
    def test_account_status_role_link_and_session_revocation(self):
        employee=m.Employee.objects.create(branch=self.branch,user=self.staff,name='Staff',role='staff')
        session=m.AuthSession.objects.create(user=self.staff,refresh_hash=digest('session'),expires_at=tz.now()+timedelta(hours=2))
        self.action('manageAccount',{'id':self.staff.id,'operation':'update','active':False,'role':'trainer','reason':'Account lock','confirmed':True})
        get_session().refresh(employee);get_session().refresh(session)
        self.assertFalse(employee.active);self.assertEqual(employee.role,'trainer');self.assertTrue(session.revoked)
    def test_foreign_branch_account_and_staff_admin_operations_denied(self):
        other=m.User.objects.create_user(branch=self.other,username='foreign@test.com',email='foreign@test.com',role='staff')
        payload={'id':other.id,'operation':'update','active':False,'role':'staff','reason':'Disable','confirmed':True}
        with self.assertRaises(RuleError):self.action('manageAccount',payload)
        with self.assertRaises(RuleError):self.action('manageAccount',{**payload,'id':self.staff.id},self.staff)
        self.assertTrue(other.is_active)
    def test_password_reset_and_change_never_audit_password(self):
        self.action('manageAccount',{'id':self.staff.id,'operation':'resetPassword','password':'NewPassword123!','reason':'Verified identity','confirmed':True})
        self.assertTrue(check_password('NewPassword123!',self.staff.password))
        with self.assertRaises(RuleError):self.action('changePassword',{'currentPassword':'wrong','password':'AnotherPassword123!'},self.staff)
        self.action('changePassword',{'currentPassword':'NewPassword123!','password':'AnotherPassword123!'},self.staff)
        self.assertTrue(check_password('AnotherPassword123!',self.staff.password))
        for row in m.Audit.objects.all():self.assertNotIn('password',str(row.detail));self.assertIsNone(row.after)
        self.assertNotIn('password',str(state(self.admin)))
    def test_policy_update_preserves_existing_permission_and_revokes_sessions(self):
        self.action('saveRolePolicy',{'role':'staff','permissions':{'memberManagement':False,'collections':False,'cardManagement':False}})
        self.action('saveRolePolicy',{'role':'staff','permissions':{'requestLeave':False}})
        with self.assertRaises(RuleError):self.action('addMember',{'name':'Denied'},self.staff)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/api/v1/members/').status_code,403)
        self.action('saveRolePolicy',{'role':'staff','permissions':{'deviceRead':True}})
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code,401)
        self.assertEqual(snapshot(self.staff)['invoices'],[])
    def test_rates_require_confirmation_and_preserve_old_sales(self):
        employee=m.Employee.objects.create(branch=self.branch,name='Hourly',type='hourly',hourly_rate=100)
        with self.assertRaises(RuleError):self.action('saveRates',{'rates':{str(employee.id):'150'}})
        self.action('saveRates',{'rates':{str(employee.id):'150.25'},'confirmed':True})
        self.assertEqual(str(employee.hourly_rate),'150.25');self.assertEqual(m.Rate.objects.count(),1)
    def test_notification_preferences_enforce_role_caps_window_and_dedup(self):
        member=m.Member.objects.create(branch=self.branch,name='Member',number='S1',phone='1',created_by=self.admin)
        plan=m.Plan.objects.create(branch=self.branch,name='Plan',price=100)
        m.Subscription.objects.create(branch=self.branch,member=member,plan=plan,start=tz.localdate(),end=tz.localdate()+timedelta(days=10),plan_name='Plan',price_cents=100)
        self.assertEqual(sync(self.admin),[])
        prefs={'membershipDays':14,'enabled':dict(DEFAULT_NOTIFICATIONS['enabled']),'roles':{k:list(v) for k,v in DEFAULT_NOTIFICATIONS['roles'].items()},'confirmed':True}
        self.action('saveNotificationPreferences',prefs);first=sync(self.admin)[0]
        self.assertEqual(sync(self.admin)[0]['id'],first['id'])
        prefs['enabled']['membership']=False;self.action('saveNotificationPreferences',prefs);self.assertEqual(sync(self.admin),[])
        prefs['roles']['payment']=['staff']
        with self.assertRaises(RuleError):self.action('saveNotificationPreferences',prefs)
    def test_metadata_only_backup_state_and_real_database_connection(self):
        data=state(self.admin)['data'];self.assertEqual(data['database'],'connected')
        self.assertNotIn('database_url',str(data));self.assertNotIn('.dump',str(data));self.assertNotIn('refresh_hash',str(snapshot(self.admin)))

    def test_device_name_scoped_without_connection_or_hardware_changes(self):
        device=m.Device.objects.create(branch=self.branch,code='SETTINGS',name='Old',sensor='unknown',last_seen=None)
        self.action('saveDeviceName',{'id':str(device.id),'name':'New','confirmed':True})
        self.assertEqual(device.name,'New');self.assertIsNone(device.last_seen);self.assertEqual(device.sensor,'unknown')
        foreign=m.Device.objects.create(branch=self.other,code='FOREIGN',name='Foreign')
        with self.assertRaises(RuleError):self.action('saveDeviceName',{'id':str(foreign.id),'name':'Changed','confirmed':True})
    def test_session_logout_rate_limit_and_secure_hash(self):
        self.client.force_login(self.staff)
        response=self.client.post('/api/v1/auth/logout/')
        self.assertEqual(response.status_code,200);self.assertEqual(self.client.get('/api/v1/auth/me/').status_code,401)
        csrf=self.client.client.get('/api/v1/auth/csrf/').json()['csrfToken']
        for _ in range(5):self.client.client.post('/api/v1/auth/login/',json={'email':self.staff.email,'password':'wrong'},headers={'X-CSRFToken':csrf})
        self.assertEqual(self.client.client.post('/api/v1/auth/login/',json={'email':self.staff.email,'password':'StaffPassword123!'},headers={'X-CSRFToken':csrf}).status_code,429)
        self.assertTrue(self.staff.password.startswith('$argon2'))

    def test_closure_rejects_entry_but_allows_expired_open_visit_exit(self):
        plan=m.Plan.objects.create(branch=self.branch,name='All day',price=100,allowed_from='00:00',allowed_to='23:59',weekdays=list(range(7)))
        member=self.action('addMember',{'name':'Member','phone':'05329998877','consent':True,'planId':str(plan.id),'start':tz.localdate().isoformat()})['result']
        self.action('assignCard',{'memberId':member,'uid':'CLOSED-CARD'})
        device=m.Device.objects.create(branch=self.branch,code='CLOSED',simulated=False,sensor='ready',last_seen=tz.now(),direction='both')
        self.action('saveOpeningHours',{'enforced':True,'from':'00:00','to':'23:59','days':list(range(7)),'closures':[tz.localdate().isoformat()],'confirmed':True})
        result=execute('authorize',{'uid':'CLOSED-CARD','direction':'entry'},None,uuid.uuid4(),device=device)['result']
        self.assertFalse(result['approved']);self.assertEqual(result['reason'],'Salon çalışma takvimi dışında');self.assertEqual(m.Grant.objects.count(),0)
        person=m.Member.objects.get(pk=member);sub=m.Subscription.objects.get(member=person);sub.start=tz.localdate()-timedelta(days=30);sub.end=tz.localdate()-timedelta(days=1);sub.save()
        m.Visit.objects.create(branch=self.branch,member=person,device=device,entry=tz.now()-timedelta(hours=1))
        with patch('app.core.time.now',return_value=tz.now()+timedelta(seconds=11)):
            result=execute('authorize',{'uid':'CLOSED-CARD','direction':'exit'},None,uuid.uuid4(),device=device)['result']
        self.assertTrue(result['approved'])
