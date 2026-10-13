import uuid
from unittest.mock import patch
from datetime import timedelta
from app.core.security import hash_password as make_password
from datetime import date, datetime
from tests_fastapi.support import TestCase, Client
from app.core.config import settings
from app.core import time as timezone
from app import models as m
from app.services.business import execute, end_for, RuleError
from app.services.projection import snapshot


class ServiceTests(TestCase):
    def setUp(self):
        self.branch = m.Branch.objects.create(name='Test')
        self.admin = m.User.objects.create_user(username='admin@test.com', email='admin@test.com', password='LongTest123!', full_name='Admin', role='admin', branch=self.branch)
        self.staff = m.User.objects.create_user(username='staff@test.com', email='staff@test.com', password='LongTest123!', full_name='Staff', role='staff', branch=self.branch)
        self.plan = m.Plan.objects.create(branch=self.branch, name='Monthly', price=1500, duration_value=1, duration_unit='month', weekdays=list(range(7)), allowed_from='00:00', allowed_to='23:59')

    def add(self, key=None):
        return execute('addMember', {'name':'Test Member','phone':'05329998877','consent':True,'planId':str(self.plan.id),'start':timezone.localdate().isoformat(),'paid':'500','method':'cash'}, self.admin, key or uuid.uuid4())

    def test_calendar_end(self):
        self.assertEqual(end_for(self.plan, date(2026,1,31)), date(2026,2,27))

    def test_dashboard_admin_only_date_and_branch_validation(self):
        self.assertNotEqual(self.client.get('/api/v1/admin/dashboard/').status_code,200)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/api/v1/admin/dashboard/').status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/v1/admin/dashboard/?date=bad').status_code,400)
        self.assertEqual(self.client.get('/api/v1/admin/dashboard/?date=9999-12-31').status_code,400)
        self.assertEqual(self.client.get('/api/v1/admin/dashboard/?branch='+str(uuid.uuid4())).status_code,403)

    def test_dashboard_collection_periods_refunds_sales_and_receivables(self):
        self.add()
        def at(day): return timezone.make_aware(datetime(2026,5,day,12))
        initial=m.Payment.objects.get()
        m.Payment.objects.filter(pk=initial.pk).update(at=at(14))
        second=m.Payment.objects.create(branch=self.branch,invoice=initial.invoice,number='SECOND',amount_cents=20000,method='cash',actor=self.admin)
        m.Payment.objects.filter(pk=second.pk).update(at=at(13))
        refund=m.Refund.objects.create(branch=self.branch,payment=initial,amount_cents=10000,reason='Test',actor=self.admin)
        m.Refund.objects.filter(pk=refund.pk).update(at=at(14))
        product=m.Product.objects.create(branch=self.branch,name='Water',code='W',price=10,cost=5)
        sale=m.Sale.objects.create(branch=self.branch,product=product,product_name='Water',quantity=1,total_cents=1000,method='cash',actor=self.admin)
        m.Sale.objects.filter(pk=sale.pk).update(at=at(20))
        self.client.force_login(self.admin)
        result=self.client.get('/api/v1/admin/dashboard/?date=2026-05-14').json()['metrics']
        self.assertEqual(result['dailyCents'],40000)
        self.assertEqual(result['weeklyCents'],60000)
        self.assertEqual(result['monthlyCents'],61000)
        self.assertEqual(result['debtCents'],90000)

    def test_dashboard_physical_event_date_live_inside_and_rejected_unknown_cards(self):
        device=self.device_fixture(); member=m.Member.objects.get(); sub=m.Subscription.objects.get()
        stamp=timezone.make_aware(datetime(2026,5,14,10,30))
        attempt=m.Attempt.objects.create(branch=self.branch,member=member,card='FA000001',device=device,direction='entry',status='confirmed',reason='Done')
        grant=m.Grant.objects.create(branch=self.branch,attempt=attempt,member=member,subscription=sub,device=device,direction='entry',confirmed=True,expires_at=stamp+timedelta(seconds=30))
        event=m.Passage.objects.create(branch=self.branch,grant=grant,device=device,event_key=uuid.uuid4(),occurred_at=stamp)
        m.Visit.objects.create(branch=self.branch,member=member,device=device,entry_event=event,entry=stamp,exit=stamp+timedelta(hours=1))
        simulated=m.Device.objects.create(branch=self.branch,code='DASH-SIM',name='Simulated',simulated=True)
        fake_attempt=m.Attempt.objects.create(branch=self.branch,member=member,card='FA000001',device=simulated,direction='entry',status='confirmed',reason='Simulation')
        fake_grant=m.Grant.objects.create(branch=self.branch,attempt=fake_attempt,member=member,subscription=sub,device=simulated,direction='entry',confirmed=True,expires_at=stamp+timedelta(seconds=30))
        fake_event=m.Passage.objects.create(branch=self.branch,grant=fake_grant,device=simulated,event_key=uuid.uuid4(),occurred_at=stamp+timedelta(minutes=2))
        m.Visit.objects.create(branch=self.branch,member=member,device=simulated,entry_event=fake_event,entry=fake_event.occurred_at,exit=stamp+timedelta(hours=1))
        live_at=timezone.now()-timedelta(hours=1)
        live_attempt=m.Attempt.objects.create(branch=self.branch,member=member,card='FA000001',device=device,direction='entry',status='confirmed',reason='Done')
        live_grant=m.Grant.objects.create(branch=self.branch,attempt=live_attempt,member=member,subscription=sub,device=device,direction='entry',confirmed=True,expires_at=live_at+timedelta(seconds=30))
        live_event=m.Passage.objects.create(branch=self.branch,grant=live_grant,device=device,event_key=uuid.uuid4(),occurred_at=live_at)
        m.Visit.objects.create(branch=self.branch,member=member,device=device,entry_event=live_event,entry=live_at)
        unverified=m.Member.objects.create(branch=self.branch,number='UNVERIFIED',name='Unverified',phone='1234567890',normalized_phone='1234567890',created_by=self.admin)
        m.Visit.objects.create(branch=self.branch,member=unverified,device=device,entry=live_at)
        simulated_member=m.Member.objects.create(branch=self.branch,number='SIMULATED',name='Simulated',phone='1234567891',normalized_phone='1234567891',created_by=self.admin)
        m.Visit.objects.create(branch=self.branch,member=simulated_member,device=simulated,entry=live_at)
        unknown=m.Attempt.objects.create(branch=self.branch,member=None,card='UNKNOWN',device=device,direction='entry',status='rejected',reason='Unknown')
        m.Attempt.objects.filter(pk=unknown.pk).update(at=stamp+timedelta(minutes=1))
        self.client.force_login(self.admin)
        data=self.client.get('/api/v1/admin/dashboard/?date=2026-05-14').json()
        self.assertEqual(data['metrics']['entries'],1)
        self.assertEqual(data['metrics']['inside'],1)
        self.assertEqual(data['metrics']['rejectedEntries'],1)
        self.assertEqual(next(h['count'] for h in data['hourly'] if h['hour']==10),1)
        self.assertEqual(data['events'][0]['kind'],'physical')
        self.assertEqual(len(data['events']),1)
        empty=self.client.get('/api/v1/admin/dashboard/?date=2026-05-13').json()
        self.assertEqual(empty['metrics']['entries'],0)
        self.assertEqual(empty['metrics']['inside'],1)

    def test_dashboard_device_heartbeat_simulation_and_other_branch_scope(self):
        device=self.device_fixture()
        m.Device.objects.create(branch=self.branch,name='Simulator',code='SIMULATION',simulated=True,last_seen=timezone.now(),sensor='ready')
        other=m.Branch.objects.create(name='Private')
        m.Device.objects.create(branch=other,name='Hidden',code='HIDDEN')
        self.client.force_login(self.admin)
        result=self.client.get('/api/v1/admin/dashboard/').json()
        self.assertEqual(len(result['devices']),2)
        self.assertEqual(next(d for d in result['devices'] if d['id']==str(device.id))['rfid'],'unknown')
        self.assertEqual(next(d for d in result['devices'] if d['code']=='SIMULATION')['state'],'simulated')
        m.Device.objects.filter(pk=device.pk).update(last_seen=timezone.now()-timedelta(minutes=2))
        result=self.client.get('/api/v1/admin/dashboard/').json()
        self.assertEqual(next(d for d in result['devices'] if d['id']==str(device.id))['state'],'offline')
        self.assertTrue(any(n['target']=='devices' for n in result['attention']))

    def test_dashboard_permissions_are_not_physical_passages_and_exit_closes_visit(self):
        self.device_fixture()
        entry=self.device_post('access/authorize',{'credential':'FA000001','direction':'entry'}).json()['result']
        self.client.force_login(self.admin)
        data=self.client.get('/api/v1/admin/dashboard/').json()
        self.assertEqual(data['events'],[]); self.assertEqual(data['inside'],[])
        self.assertEqual(self.device_post('passage-events',{'grantId':entry['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':timezone.now().isoformat(),'direction':'entry'}).status_code,200)
        data=self.client.get('/api/v1/admin/dashboard/').json()
        self.assertEqual(len(data['inside']),1); self.assertEqual(data['events'][0]['direction'],'entry')
        m.Attempt.objects.update(at=timezone.now()-timedelta(seconds=11))
        exit_grant=self.device_post('access/authorize',{'credential':'FA000001','direction':'exit'}).json()['result']
        self.assertTrue(exit_grant['approved'])
        self.assertEqual(self.device_post('passage-events',{'grantId':exit_grant['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':timezone.now().isoformat(),'direction':'exit'}).status_code,200)
        data=self.client.get('/api/v1/admin/dashboard/').json()
        self.assertEqual(data['inside'],[])
        self.assertEqual([row['direction'] for row in data['events']],['exit','entry'])

    def test_dashboard_measurements_require_fresh_real_device_data(self):
        device=self.device_fixture()
        device.telemetry={'outsideCm':14,'insideCm':40}; device.telemetry_at=timezone.now(); device.save()
        self.client.force_login(self.admin)
        row=self.client.get('/api/v1/admin/dashboard/').json()['devices'][0]
        self.assertEqual(row['measurements']['outsideCm'],14)
        self.assertEqual(row['measurements']['insideCm'],40)
        self.assertEqual(row['rfid'],'unknown'); self.assertEqual(row['servo'],'unknown')
        device.telemetry_at=timezone.now()-timedelta(seconds=5); device.save()
        row=self.client.get('/api/v1/admin/dashboard/').json()['devices'][0]
        self.assertIsNone(row['measurements']['outsideCm'])
        device.telemetry_at=timezone.now(); device.simulated=True; device.save()
        row=self.client.get('/api/v1/admin/dashboard/').json()['devices'][0]
        self.assertEqual(row['state'],'simulated'); self.assertIsNone(row['measurements']['insideCm'])

    def test_atomic_member_sale(self):
        self.add()
        self.assertEqual(m.Member.objects.count(),1)
        self.assertEqual(m.Payment.objects.get().amount_cents,50000)
        self.assertEqual(m.Invoice.objects.get().total_cents,150000)

    def test_idempotent_retry(self):
        key=uuid.uuid4()
        self.assertEqual(self.add(key),self.add(key))
        self.assertEqual(m.Payment.objects.count(),1)

    def test_key_cannot_be_reused_for_different_payload(self):
        key=uuid.uuid4(); self.add(key)
        with self.assertRaises(RuleError): execute('notice',{'message':'Other'},self.admin,key)

    def test_stock_sale_and_retry(self):
        product=m.Product.objects.create(branch=self.branch,name='Water',code='WATER',price=25,cost=10,stock=2)
        key=uuid.uuid4(); payload={'productId':str(product.id),'quantity':2,'method':'cash'}
        execute('sellProduct',payload,self.staff,key)
        execute('sellProduct',payload,self.staff,key)
        product.refresh_from_db(); self.assertEqual(product.stock,0)
        self.assertEqual(m.Sale.objects.count(),1)
        with self.assertRaises(RuleError): execute('sellProduct',payload,self.staff,uuid.uuid4())

    def test_rate_history_preserved(self):
        employee=m.Employee.objects.create(branch=self.branch,name='Worker',type='hourly',card='STAFF-Y',hourly_rate=180)
        m.Rate.objects.create(branch=self.branch,employee=employee,rate=180,effective_at=timezone.now())
        execute('saveRates',{'rates':{str(employee.id):200},'confirmed':True},self.admin,uuid.uuid4())
        self.assertEqual(m.Rate.objects.filter(employee=employee).count(),2)

    def test_invalid_sale_rolls_back(self):
        with self.assertRaises(RuleError):
            execute('addMember', {'name':'Test','phone':'05329998877','consent':True,'planId':str(uuid.uuid4()),'start':'2026-10-10'},self.admin,uuid.uuid4())
        self.assertEqual(m.Member.objects.count(),0)

    def test_staff_cannot_change_prices(self):
        with self.assertRaises(RuleError): execute('saveSettings',{'capacity':20},self.staff,uuid.uuid4())

    def test_staff_private_data_hidden(self):
        m.Employee.objects.create(branch=self.branch,name='Worker',type='hourly',card='STAFF-X',hourly_rate=200)
        data=snapshot(self.staff)
        self.assertEqual(data['employees'],[])
        self.assertEqual(data['shifts'],[])
        self.assertEqual(data['audit'],[])

    def test_auth_and_csrf(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.get('/api/v1/state/').status_code,401)
        self.assertEqual(client.post('/api/v1/auth/login/',data={'email':'admin@test.com','password':'LongTest123!'},content_type='application/json').status_code,403)
        token=client.get('/api/v1/auth/csrf/').json()['csrfToken']
        response=client.post('/api/v1/auth/login/',data={'email':'admin@test.com','password':'LongTest123!'},content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200)
        self.assertEqual(client.get('/api/v1/state/').status_code,200)

    def test_foreign_branch_edit_denied(self):
        result=self.add()
        other=m.Branch.objects.create(name='Other')
        self.staff.branch=other; self.staff.save()
        with self.assertRaises(RuleError): execute('editMember',{'id':result['result'],'name':'Changed'},self.staff,uuid.uuid4())

    def test_grant_does_not_count_visit(self):
        result=self.add()
        execute('assignCard',{'memberId':result['result'],'uid':'CARD-X'},self.staff,uuid.uuid4())
        device=m.Device.objects.create(branch=self.branch,code='SIM',name='Sim',simulated=True,last_seen=timezone.now(),direction='both')
        response=execute('authorize',{'uid':'CARD-X','deviceId':str(device.id),'direction':'entry'},self.staff,uuid.uuid4())
        self.assertTrue(response['result']['approved'])
        self.assertEqual(m.Visit.objects.count(),0)
        key=uuid.uuid4()
        execute('confirmPassage',{'id':response['result']['grantId']},self.staff,key)
        execute('confirmPassage',{'id':response['result']['grantId']},self.staff,key)
        self.assertEqual(m.Visit.objects.count(),1)

    def device_fixture(self):
        result=self.add()
        execute('assignCard',{'memberId':result['result'],'uid':'FA000001'},self.staff,uuid.uuid4())
        return m.Device.objects.create(branch=self.branch,code='UNO-TEST',name='USB test',sensor='ready',last_seen=timezone.now(),token_hash=make_password('a'*48),direction='both')

    def device_post(self,path,payload,key=None,secret='a'*48):
        return self.client.post('/api/v1/device/'+path+'/',data=payload,content_type='application/json',HTTP_X_DEVICE_CODE='UNO-TEST',HTTP_X_DEVICE_KEY=secret,HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()))

    def test_real_device_auto_direction_and_one_sensor_event(self):
        self.device_fixture()
        response=self.device_post('access/authorize',{'credential':'FA000001','direction':'auto'})
        self.assertEqual(response.status_code,200)
        result=response.json()['result']; self.assertTrue(result['approved']); self.assertEqual(result['direction'],'entry')
        self.assertEqual(m.Visit.objects.count(),0)
        event={'grantId':result['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':timezone.now().isoformat(),'direction':'entry'}
        key=uuid.uuid4()
        self.assertEqual(self.device_post('passage-events',event,key).status_code,200)
        self.assertEqual(self.device_post('passage-events',event,key).status_code,200)
        self.assertEqual(m.Visit.objects.count(),1)
        later=timezone.now()+timedelta(seconds=11)
        with patch('app.services.business.timezone.now',return_value=later):
            response=self.device_post('access/authorize',{'credential':'FA000001','direction':'auto'})
            self.assertTrue(response.json()['result']['approved'])
            self.assertEqual(response.json()['result']['direction'],'exit')

    def test_device_secret_and_sensor_readiness(self):
        device=self.device_fixture()
        self.assertEqual(self.device_post('heartbeat',{'sensor':'ready'},secret='wrong').status_code,401)
        device.sensor='fault'; device.save()
        result=self.device_post('access/authorize',{'credential':'FA000001','direction':'auto'}).json()['result']
        self.assertFalse(result['approved']); self.assertEqual(m.Grant.objects.count(),0)

    def test_device_heartbeat_components_disconnect_and_purpose(self):
        device=self.device_fixture()
        response=self.device_post('heartbeat',{'sensor':'ready','telemetry':{'port':'COM6','rfid':'ready','servo':'closed','lcd':'ready','connection':'connected'}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['purpose'],'access')
        device.refresh_from_db(); self.assertEqual(device.telemetry['port'],'COM6')
        self.device_post('measurements',{'outsideCm':12,'insideCm':50})
        device.refresh_from_db(); self.assertEqual(device.telemetry['rfid'],'ready')
        self.assertEqual(self.device_post('heartbeat',{'connected':'yes'}).status_code,400)
        self.device_post('heartbeat',{'connected':False,'sensor':'unknown','telemetry':{'connection':'retrying'}})
        device.refresh_from_db(); self.assertIsNone(device.last_seen)
        self.assertEqual(snapshot(self.admin)['devices'][0]['status'],'offline')

    def test_sensor_progress_is_telemetry_not_physical_passage(self):
        device=self.device_fixture()
        payload={'sensor':'ready','telemetry':{'firmware':'6','passageState':'detected','detectedDirection':'entry','progressAt':timezone.now().isoformat()}}
        self.assertEqual(self.device_post('heartbeat',payload).status_code,200)
        self.assertEqual(self.device_post('diagnostics',{'type':'entry_detected'}).status_code,200)
        device.refresh_from_db()
        self.assertEqual(device.telemetry['passageState'],'detected')
        self.assertEqual(device.telemetry['detectedDirection'],'entry')
        self.assertEqual(m.Passage.objects.count(),0)
        self.assertEqual(m.Visit.objects.count(),0)
        self.assertEqual(m.Shift.objects.count(),0)

    def test_access_and_attendance_device_purposes_are_separate(self):
        device=self.device_fixture()
        self.assertEqual(self.device_post('attendance',{'credential':'FA000001'}).status_code,400)
        execute('devicePurpose',{'id':str(device.id),'purpose':'attendance'},self.admin,uuid.uuid4())
        response=self.device_post('access/authorize',{'credential':'FA000001','direction':'entry'})
        self.assertEqual(response.status_code,200); self.assertFalse(response.json()['result']['approved'])
        self.assertEqual(m.Grant.objects.count(),0)
        attendance=self.device_post('attendance',{'credential':'FA000001'})
        self.assertEqual(attendance.status_code,400)
        self.assertIn('fiziksel geçiş',attendance.json()['message'])
        self.assertEqual(m.AttendanceEvent.objects.count(),0)
        self.assertEqual(m.Shift.objects.count(),0)
        with self.assertRaises(RuleError): execute('devicePurpose',{'id':str(device.id),'purpose':'access'},self.staff,uuid.uuid4())

    def test_purpose_change_cannot_invalidate_pending_access(self):
        device=self.device_fixture()
        result=self.device_post('access/authorize',{'credential':'FA000001','direction':'entry'}).json()['result']
        self.assertTrue(result['approved'])
        with self.assertRaises(RuleError): execute('devicePurpose',{'id':str(device.id),'purpose':'attendance'},self.admin,uuid.uuid4())

    def test_wrong_sensor_direction_rejected(self):
        self.device_fixture()
        result=self.device_post('access/authorize',{'credential':'FA000001','direction':'auto'}).json()['result']
        response=self.device_post('passage-events',{'grantId':result['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':timezone.now().isoformat(),'direction':'exit'})
        self.assertEqual(response.status_code,400); self.assertEqual(m.Visit.objects.count(),0)

    def test_short_offline_delivery_preserves_event_time(self):
        self.device_fixture()
        result=self.device_post('access/authorize',{'credential':'FA000001','direction':'auto'}).json()['result']
        occurred=timezone.now()+timedelta(seconds=2)
        with patch('app.services.business.timezone.now',return_value=occurred+timedelta(seconds=45)):
            response=self.device_post('passage-events',{'grantId':result['grantId'],'eventId':str(uuid.uuid4()),'occurredAt':occurred.isoformat(),'direction':'entry'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(m.Visit.objects.get().entry,occurred)

    def test_recent_entries_scope_and_limit(self):
        self.add(); member=m.Member.objects.get()
        other=m.Branch.objects.create(name='Other')
        device=m.Device.objects.create(branch=self.branch,code='RECENT',name='Recent')
        now=timezone.now()
        for index in range(12):
            m.Visit.objects.create(branch=self.branch,member=member,device=device,entry=now-timedelta(minutes=index+1),exit=now)
        m.Visit.objects.create(branch=other,member=member,device=device,entry=now,exit=now)
        self.client.force_login(self.staff)
        response=self.client.get('/api/v1/access/recent-entries/').json()
        self.assertEqual(len(response['entries']),10)
        self.assertEqual(response['entries'][0]['entry'],(now-timedelta(minutes=1)).isoformat())
        self.assertEqual(len(response['movements']),10)
        self.assertTrue(all(item['direction']=='exit' for item in response['movements']))

    def test_recent_movements_show_exit_of_old_visit(self):
        self.add(); member=m.Member.objects.get()
        device=m.Device.objects.create(branch=self.branch,code='MOVEMENTS',name='Gate')
        now=timezone.now()
        old=m.Visit.objects.create(branch=self.branch,member=member,device=device,entry=now-timedelta(days=2),exit=now)
        for index in range(12):
            m.Visit.objects.create(branch=self.branch,member=member,device=device,entry=now-timedelta(minutes=index+2),exit=now-timedelta(minutes=index+1))
        self.client.force_login(self.staff)
        response=self.client.get('/api/v1/access/recent-entries/').json()
        self.assertEqual(response['movements'][0]['id'],f'{old.id}:exit')
        self.assertEqual(response['movements'][0]['direction'],'exit')
        self.assertNotIn(str(old.id),[row['id'] for row in response['entries']])

    def test_recent_attempts_show_rejection_and_expired_grant(self):
        device=self.device_fixture()
        execute('authorize',{'uid':'FA000001','deviceId':str(device.id),'direction':'entry'},None,uuid.uuid4(),device)
        m.Grant.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        m.Attempt.objects.create(branch=self.branch,member=None,card='UNKNOWN',device=device,
            direction='entry',status='rejected',reason='Kart bulunamadı')
        self.client.force_login(self.staff)
        result=self.client.get('/api/v1/access/recent-entries/').json()
        self.assertEqual(result['movements'],[])
        self.assertEqual(result['attempts'][0]['status'],'rejected')
        self.assertEqual(result['attempts'][0]['name'],'Tanımsız kart')
        self.assertEqual(result['attempts'][1]['status'],'expired')

    def test_capture_and_assign_without_visit(self):
        device=self.device_fixture(); member=m.Member.objects.get()
        self.client.force_login(self.staff)
        response=self.client.post('/api/v1/cards/capture/',data={'deviceId':str(device.id),'memberId':str(member.id)},content_type='application/json')
        self.assertEqual(response.status_code,200); capture=response.json()
        device.sensor='fault'; device.save()
        response=self.device_post('capture/read',{'captureId':capture['id'],'uid':'AABBCCDD'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/api/v1/cards/capture/'+capture['id']+'/').json()['uid'],'AABBCCDD')
        execute('assignCard',{'memberId':str(member.id),'uid':'AABBCCDD','captureId':capture['id']},self.staff,uuid.uuid4())
        self.assertEqual(m.Card.objects.get(uid='AABBCCDD').member_id,member.id)
        self.assertEqual(m.Visit.objects.count(),0); self.assertEqual(m.Grant.objects.count(),0)

    def test_capture_blocks_normal_access_and_other_staff_reads(self):
        device=self.device_fixture(); member=m.Member.objects.get()
        self.client.force_login(self.staff)
        capture=self.client.post('/api/v1/cards/capture/',data={'deviceId':str(device.id),'memberId':str(member.id)},content_type='application/json').json()
        result=self.device_post('access/authorize',{'credential':'FA000001','direction':'auto'}).json()['result']
        self.assertFalse(result['approved']); self.assertEqual(m.Grant.objects.count(),0)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/v1/cards/capture/'+capture['id']+'/').status_code,404)
        self.assertEqual(self.client.post('/api/v1/cards/capture/',data={'deviceId':str(device.id),'memberId':str(member.id)},content_type='application/json').status_code,409)

    def test_admin_can_capture_assign_and_change_card_status_without_access_permissions(self):
        device=self.device_fixture(); member=m.Member.objects.get()
        self.client.force_login(self.admin)
        response=self.client.post('/api/v1/cards/capture/',data={'deviceId':str(device.id),'memberId':str(member.id)},content_type='application/json')
        self.assertEqual(response.status_code,200)
        capture=response.json()
        self.assertEqual(self.device_post('capture/read',{'captureId':capture['id'],'uid':'11223344'}).status_code,200)
        execute('assignCard',{'memberId':str(member.id),'uid':'11223344','captureId':capture['id']},self.admin,uuid.uuid4())
        card=m.Card.objects.get(uid='11223344')
        execute('cardStatus',{'id':str(card.id),'status':'inactive'},self.admin,uuid.uuid4())
        card.refresh_from_db(); self.assertEqual(card.status,'inactive')
        with self.assertRaises(RuleError):
            execute('authorize',{'uid':'11223344','deviceId':str(device.id),'direction':'entry'},self.admin,uuid.uuid4())
        self.assertEqual(m.Visit.objects.count(),0)
        other=m.Branch.objects.create(name='Other')
        wrong=m.Member.objects.create(branch=other,number='OTHER-CARD',name='Other',phone='123',normalized_phone='123',created_by=self.admin)
        with self.assertRaises(RuleError):
            execute('assignCard',{'memberId':str(wrong.id),'uid':'55667788'},self.admin,uuid.uuid4())

    def test_dashboard_critical_device_and_passage_warnings_precede_debts(self):
        device=self.device_fixture()
        m.Device.objects.filter(pk=device.pk).update(last_seen=None)
        installment=m.Installment.objects.first()
        installment.due=timezone.localdate()-timedelta(days=1); installment.save()
        m.DeviceEvent.objects.create(branch=self.branch,device=device,event_type='fault',level='error',message='Gate failure')
        self.client.force_login(self.admin)
        alerts=self.client.get('/api/v1/admin/dashboard/').json()['attention']
        self.assertEqual(alerts[0]['target'],'devices')
        self.assertEqual(alerts[1]['target'],'access')
        self.assertTrue(any(row['target']=='payments' for row in alerts[2:]))

    def test_capture_can_read_another_card_before_assignment(self):
        device=self.device_fixture();member=m.Member.objects.get();self.client.force_login(self.staff)
        capture=self.client.post('/api/v1/cards/capture/',data={'deviceId':str(device.id),'memberId':str(member.id)},content_type='application/json').json()
        for uid in ['AABBCCDD','11223344']:
            self.assertEqual(self.device_post('capture/read',{'captureId':capture['id'],'uid':uid}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/cards/capture/'+capture['id']+'/').json()['uid'],'11223344')
        self.assertEqual(m.Grant.objects.count(),0)

    def test_diagnostics_has_levels_and_scoped_capture_logs(self):
        device=self.device_fixture();member=m.Member.objects.get();self.client.force_login(self.staff)
        capture=self.client.post('/api/v1/cards/capture/',data={'deviceId':str(device.id),'memberId':str(member.id)},content_type='application/json').json()
        self.device_post('capture/read',{'captureId':capture['id'],'uid':'AABBCCDD'})
        self.assertEqual(self.client.get('/api/v1/diagnostics/events/').status_code,403)
        self.client.force_login(self.admin)
        messages=self.client.get('/api/v1/diagnostics/events/').json()['events']
        self.assertTrue(any('AABBCCDD' in e['message'] and e['level']=='info' for e in messages))
        other=m.User.objects.create_user(username='other@test.com',email='other@test.com',role='staff',branch=self.branch)
        self.client.force_login(other)
        self.assertEqual(self.client.get('/api/v1/diagnostics/events/').status_code,403)

    def test_live_measurements_and_stale_detection(self):
        device=self.device_fixture()
        self.assertEqual(self.device_post('measurements',{'outsideCm':18,'insideCm':None}).status_code,200)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/api/v1/sensors/measurements/').status_code,403)
        self.client.force_login(self.admin)
        data=self.client.get('/api/v1/sensors/measurements/').json()['devices'][0]
        self.assertEqual(data['outsideCm'],18);self.assertIsNone(data['insideCm']);self.assertFalse(data['stale'])
        device.refresh_from_db();device.telemetry_at=timezone.now()-timedelta(seconds=5);device.save()
        self.assertTrue(self.client.get('/api/v1/sensors/measurements/').json()['devices'][0]['stale'])
        self.assertEqual(self.device_post('measurements',{'outsideCm':-1,'insideCm':40}).status_code,400)
