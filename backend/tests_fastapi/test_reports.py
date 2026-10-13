import base64
from datetime import datetime,date,timedelta
from decimal import Decimal
from io import BytesIO
import time
import uuid
from sqlalchemy import event,insert,select,func
from openpyxl import load_workbook
from app import models as m
from app.core import time as tz
from app.db.session import get_session
from app.db.session import SessionLocal,engine
from unittest.mock import patch
from app.services.reports import build
from app.services.reports.common import filters,table,RuleError
from app.services.reports.export import export
from tests_fastapi.support import TestCase


class ReportTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='İstanbul test')
        self.admin=m.User.objects.create_user(username='reports@test.com',email='reports@test.com',password='LongPassword123!',full_name='Yönetici',role='admin',branch=self.branch)
        self.staff=m.User.objects.create_user(username='staff@reports.test',email='staff@reports.test',password='LongPassword123!',full_name='Çalışan',role='staff',branch=self.branch)
        self.employee=m.Employee.objects.create(branch=self.branch,user=self.staff,name='Çalışan',type='hourly',phone='private-phone',email='private-email')
        self.member=m.Member.objects.create(branch=self.branch,name='Üye',number='R-1',phone='private-member-phone',normalized_phone='phone',created_by=self.admin,created_at=self.at(1))
        self.plan=m.Plan.objects.create(branch=self.branch,name='Güncel Paket',days=30,price=Decimal('300'),sessions=10)
        self.sub=m.Subscription.objects.create(branch=self.branch,member=self.member,plan=self.plan,plan_name='Satın Alınan Paket',start=date(2026,9,10),end=date(2026,10,10),price_cents=10000,total_sessions=10,remaining=8,rules={'kind':'hybrid'},created_at=self.at(10))
        self.invoice=m.Invoice.objects.create(branch=self.branch,member=self.member,subscription=self.sub,number='INV-1',total_cents=10000,created_at=self.at(10))
        self.p1=m.Payment.objects.create(branch=self.branch,invoice=self.invoice,number='P-1',amount_cents=6000,method='cash',actor=self.admin,at=self.at(10))
        self.p2=m.Payment.objects.create(branch=self.branch,invoice=self.invoice,number='P-2',amount_cents=2000,method='bank',actor=self.staff,at=self.at(11))
        self.refund=m.Refund.objects.create(branch=self.branch,payment=self.p1,amount_cents=1000,reason='Kısmi iade',actor=self.admin,at=self.at(12))
        m.Installment.objects.create(branch=self.branch,invoice=self.invoice,due=date(2026,9,11),amount_cents=5000)
        m.Installment.objects.create(branch=self.branch,invoice=self.invoice,due=date(2026,9,12),amount_cents=5000)
        m.Audit.objects.create(branch=self.branch,actor=self.admin,type='renew',entity_id=str(self.sub.id),at=self.at(10),detail={'phone':'hidden','nested':{'secret':'hidden','reason':'Allowed'}})
        self.product=m.Product.objects.create(branch=self.branch,name='Su',code='W',category='İçecek',price=10,cost=5,stock=2,minimum=3)
        self.sale=m.Sale.objects.create(branch=self.branch,product=self.product,product_name='Su',quantity=2,total_cents=2000,unit_cost_cents=500,unit_price_cents=1000,method='pos',actor=self.staff,number='SALE-1',at=self.at(10))
        m.StockMovement.objects.create(branch=self.branch,product=self.product,sale=self.sale,kind='sale',quantity=-2,actor=self.staff,at=self.at(10),unit_cost_cents=500)
        m.StockMovement.objects.create(branch=self.branch,product=self.product,sale=self.sale,kind='return',quantity=1,returned_units=1,refund_cents=1000,restocked=True,method='pos',actor=self.admin,at=self.at(12))
        self.real=m.Device.objects.create(branch=self.branch,code='REAL',simulated=False)
        self.sim=m.Device.objects.create(branch=self.branch,code='SIM',simulated=True)
    def at(self,day,hour=12,minute=0):return tz.make_aware(datetime(2026,9,day,hour,minute))
    def report(self,tab='finance',**values):return build(self.admin,{'tab':tab,'from':'2026-09-10','to':'2026-09-12',**values})
    def metrics(self,data):return {x['key']:x['value'] for x in data['metrics']}
    def passage(self,direction,at,device=None,confirmed=True):
        device=device or self.real
        attempt=m.Attempt.objects.create(branch=self.branch,member=self.member,device=device,direction=direction,status='confirmed' if confirmed else 'granted',at=at)
        grant=m.Grant.objects.create(branch=self.branch,member=self.member,subscription=self.sub,device=device,attempt=attempt,direction=direction,confirmed=confirmed,expires_at=at+timedelta(seconds=10))
        if not confirmed:return None
        return m.Passage.objects.create(branch=self.branch,grant=grant,device=device,event_key=uuid.uuid4(),occurred_at=at)

    def test_financial_accrual_collections_net_debt_and_installments(self):
        metrics=self.metrics(self.report())
        self.assertEqual({k:metrics[k] for k in ['accrued','gross','refund','net','remaining','overdue']},{'accrued':12000,'gross':10000,'refund':2000,'net':8000,'remaining':3000,'overdue':3000})
        self.assertEqual(self.report()['table']['count'],5)
        self.assertEqual(self.metrics(self.report(type='debt'))['remaining'],3000)
        self.assertEqual(self.report(type='overdue')['table']['rows'][0][-1],3000)

    def test_cancelled_invoice_and_later_refund_are_not_retroactive(self):
        self.invoice.status='cancelled';self.invoice.save()
        m.Audit.objects.create(branch=self.branch,actor=self.admin,type='cancelInvoice',entity_id=str(self.invoice.id),at=self.at(13))
        self.assertEqual(self.metrics(self.report())['accrued'],12000)
        self.assertEqual(self.metrics(self.report(to='2026-09-13'))['accrued'],2000)
        self.refund.at=self.at(13);self.refund.save()
        self.assertEqual(self.metrics(self.report())['refund'],1000)
        self.assertEqual(self.metrics(self.report())['net'],9000)

    def test_sources_and_lesson_invoice_not_double_counted(self):
        lesson=m.ClassSession.objects.create(branch=self.branch,name='Özel ders',kind='private',at=self.at(11),duration=60,capacity=1,price_cents=3000)
        booking=m.Booking.objects.create(branch=self.branch,member=self.member,class_session=lesson,status='booked',at=self.at(10),actor_id=self.admin.id)
        invoice=m.Invoice.objects.create(branch=self.branch,member=self.member,booking_id=booking.id,number='INV-L',total_cents=3000,created_at=self.at(10),description='Özel ders')
        m.Payment.objects.create(branch=self.branch,invoice=invoice,number='P-L',amount_cents=3000,actor=self.admin,at=self.at(10),method='cash')
        self.assertEqual(self.metrics(self.report())['gross'],13000)
        self.assertEqual(self.metrics(self.report(type='lesson'))['gross'],3000)
        self.assertEqual(self.metrics(self.report(type='membership'))['gross'],8000)
        self.assertEqual(self.metrics(self.report(type='product'))['net'],1000)
        self.assertEqual(self.metrics(self.report('classes',type='private'))['lessonSales'],3000)
        self.assertEqual(self.metrics(self.report('classes',type='private'))['lessonCollections'],3000)

    def test_new_member_and_sale_renewal_and_snapshot_are_distinct(self):
        m.Subscription.objects.create(branch=self.branch,member=self.member,plan=self.plan,plan_name='Önceki',start=date(2026,8,1),end=date(2026,9,10),price_cents=9000,created_at=self.at(1))
        data=self.report('members');metrics=self.metrics(data)
        self.assertEqual(metrics['new'],0);self.assertEqual(metrics['sold'],1);self.assertEqual(metrics['renew'],1)
        self.assertEqual(data['table']['rows'][0][2],'Satın Alınan Paket')
        self.assertEqual(data['table']['rows'][0][7],10000)
        self.assertEqual(self.metrics(self.report('overview'))['new'],0)

    def test_membership_states_and_cancellation_cutoff(self):
        self.sub.status='cancelled';self.sub.save()
        m.Audit.objects.create(branch=self.branch,actor=self.admin,type='cancelSubscription',entity_id=str(self.sub.id),at=self.at(13))
        self.assertEqual(self.report('members')['table']['rows'][0][3],'active')
        self.assertEqual(self.report('members',to='2026-09-13')['table']['rows'][0][3],'cancelled')

    def test_real_physical_visits_exclude_raw_and_simulated_scans(self):
        entry=self.passage('entry',self.at(10,9));exit=self.passage('exit',self.at(10,10))
        m.Visit.objects.create(branch=self.branch,member=self.member,device=self.real,entry_event=entry,exit_event=exit,entry=self.at(10,9),exit=self.at(10,10))
        self.passage('entry',self.at(11),self.sim);self.passage('entry',self.at(12),confirmed=False)
        m.Attempt.objects.create(branch=self.branch,member=self.member,device=self.real,status='rejected',reason='Tekrar okuma',at=self.at(12))
        data=self.report('visits');metrics=self.metrics(data)
        self.assertEqual(metrics['entry'],1);self.assertEqual(metrics['exit'],1);self.assertEqual(metrics['duration'],60);self.assertEqual(metrics['timeout'],1);self.assertEqual(metrics['duplicates'],1)
        self.assertEqual(data['table']['count'],2)
        self.assertEqual(self.metrics(self.report('members'))['used'],1)
        self.assertEqual(self.report('visits',type='timeout',hour='1')['table']['count'],0)

    def test_open_visit_inside_asof_and_time_weighted_density(self):
        entry=self.passage('entry',self.at(10,9))
        m.Visit.objects.create(branch=self.branch,member=self.member,device=self.real,entry_event=entry,entry=self.at(10,9))
        data=self.metrics(self.report('visits',to='2026-09-10'))
        self.assertEqual(data['inside'],1);self.assertAlmostEqual(data['density'],15/24);self.assertIsNone(data['duration'])

    def test_class_bookings_actual_attendance_waitlist_and_trainer(self):
        lesson=m.ClassSession.objects.create(branch=self.branch,name='Pilates',trainer='Çalışan',trainer_id=self.employee.id,at=self.at(11),capacity=4,duration=60)
        for index,status in enumerate(['booked','attended','absent','waiting']):
            member=m.Member.objects.create(branch=self.branch,name=str(index),number=f'C-{index}',phone=str(index),normalized_phone=str(index),created_by=self.admin)
            m.Booking.objects.create(branch=self.branch,member=member,class_session=lesson,status=status,at=self.at(10),subscription=self.sub)
        data=self.metrics(self.report('classes',person=f'e:{self.employee.id}'))
        self.assertEqual(data['bookings'],4);self.assertEqual(data['attended'],1);self.assertEqual(data['attendanceRate'],50);self.assertEqual(data['occupancy'],75);self.assertEqual(data['waiting'],1)
        self.assertEqual(self.report('classes',type='attended')['table']['count'],1)
        self.assertEqual(self.report('classes',type='attended',planId=str(self.plan.id))['table']['count'],1)

    def test_overnight_shift_unpaid_paid_break_and_daily_split(self):
        plan=m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.employee,actor=self.admin,start=self.at(10,22),end=self.at(11,6),break_minutes=30)
        shift=m.Shift.objects.create(branch=self.branch,employee=self.employee,planned_id=plan.id,entry=self.at(10,22,10),exit=self.at(11,7),simulated=False)
        m.ShiftBreak.objects.create(branch_id=self.branch.id,shift=shift,start=self.at(10,23,45),end=self.at(11,0,15),paid=False)
        m.ShiftBreak.objects.create(branch_id=self.branch.id,shift=shift,start=self.at(11,2),end=self.at(11,2,30),paid=True)
        get_session().flush()
        data=self.report('personnel');metrics=self.metrics(data)
        self.assertAlmostEqual(metrics['hours'],8+1/3);self.assertEqual(metrics['late'],1);self.assertAlmostEqual(metrics['overtime'],35/60)
        from app.services.personnel import state
        module=state(self.admin)['shiftMetrics'][0]
        self.assertAlmostEqual(module['workedMs']/3600000,metrics['hours'])
        self.assertEqual(module['lateMinutes'],5);self.assertAlmostEqual(module['overtimeMinutes']/60,metrics['overtime'])
        values={p['label']:p['value'] for p in data['charts'][1]['points']}
        self.assertAlmostEqual(values['2026-09-10'],95/60);self.assertAlmostEqual(values['2026-09-11'],6.75)
        m.Shift.objects.create(branch=self.branch,employee=self.employee,entry=self.at(12,8),exit=self.at(12,9),simulated=True)
        self.assertAlmostEqual(self.metrics(self.report('personnel'))['hours'],8+1/3)

    def test_absence_and_approved_leave_use_existing_planned_shift_rules(self):
        plan=m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.employee,actor=self.admin,start=self.at(10,9),end=self.at(10,17))
        self.assertEqual(self.metrics(self.report('personnel'))['absent'],1)
        kind=m.LeaveType.objects.create(branch_id=self.branch.id,name='Yıllık')
        m.LeaveRequest.objects.create(branch_id=self.branch.id,employee=self.employee,actor=self.admin,type_id=kind.id,start=date(2026,9,10),end=date(2026,9,10),status='approved')
        self.assertEqual(self.metrics(self.report('personnel'))['absent'],0)
        self.assertEqual(self.report('personnel',type='leave')['table']['count'],1)
        m.PlannedShift.objects.create(branch_id=self.branch.id,employee=self.employee,actor=self.admin,start=self.at(11,0),end=self.at(11,8))
        self.assertEqual(self.metrics(self.report('personnel'))['absent'],1)

    def test_personnel_period15_matches_clipped_work_and_own_employee(self):
        from app.services.personnel import milliseconds
        shift=m.Shift.objects.create(branch=self.branch,employee=self.employee,entry=self.at(14,22),exit=self.at(15,6),simulated=False)
        m.ShiftBreak.objects.create(branch_id=self.branch.id,shift=shift,start=self.at(15,0),end=self.at(15,0,30),paid=False)
        m.ShiftBreak.objects.create(branch_id=self.branch.id,shift=shift,start=self.at(15,2),end=self.at(15,2,30),paid=True)
        m.Shift.objects.create(branch=self.branch,employee=self.employee,entry=self.at(16,9),exit=self.at(16,10),simulated=True)
        other=m.Employee.objects.create(branch=self.branch,name='Other staff')
        m.Shift.objects.create(branch=self.branch,employee=other,entry=self.at(15,9),exit=self.at(15,17),simulated=False)
        query={'tab':'personnel','from':'2026-09-15','to':'2026-10-14'}
        data=build(self.staff,query);metric=self.metrics(data)
        expected=milliseconds(shift,self.at(15,0),tz.make_aware(datetime(2026,10,15)),tz.now())/3600000
        self.assertAlmostEqual(expected,5.5);self.assertAlmostEqual(metric['hours'],expected);self.assertEqual(data['table']['count'],1)
        with self.assertRaises(RuleError):build(self.staff,{**query,'person':f'e:{other.id}'})

    def test_stock_net_cost_snapshot_margin_and_current_valuation(self):
        data=self.metrics(self.report('stock'))
        self.assertEqual(data['net'],1000);self.assertEqual(data['sold'],2);self.assertEqual(data['returned'],1);self.assertEqual(data['profit'],500);self.assertEqual(data['value'],1000);self.assertEqual(data['critical'],1)
        self.product.cost=99;self.product.save()
        self.assertEqual(self.metrics(self.report('stock'))['profit'],500)
        self.assertEqual(self.metrics(self.report('stock',category='Başka'))['net'],0)

    def test_turkey_inclusive_boundary_person_method_plan_filters(self):
        self.p1.at=self.at(10,0);self.p1.save();self.p2.at=self.at(11,0);self.p2.save()
        one=self.report(to='2026-09-10');self.assertEqual(self.metrics(one)['gross'],8000)
        cash=self.report(method='cash');self.assertEqual(self.metrics(cash)['net'],5000);self.assertIsNone(self.metrics(cash)['accrued'])
        own=self.report(person=f'u:{self.staff.id}');self.assertEqual(self.metrics(own)['gross'],4000)
        self.assertEqual(self.metrics(self.report(planId=str(self.plan.id)))['gross'],8000)
        self.assertEqual(self.metrics(self.report(category='İçecek'))['net'],1000)

    def test_branch_permissions_and_staff_own_only_endpoints(self):
        other=m.Branch.objects.create(name='Other')
        user=m.User.objects.create_user(username='other@test.com',role='admin',branch=other)
        self.assertEqual(build(user,{'tab':'finance','from':'2026-09-10','to':'2026-09-12'})['table']['count'],0)
        self.client.force_login(self.staff)
        for endpoint in ['/api/v1/reports/?tab=finance','/api/v1/reports/export/?tab=finance','/api/v1/reports/?tab=personnel&branch='+str(other.id),'/api/v1/reports/?tab=personnel&person=u:'+str(self.admin.id)]:self.assertEqual(self.client.get(endpoint).status_code,403)
        self.assertEqual(self.client.get('/api/v1/reports/?tab=personnel').status_code,200)
        self.assertEqual(list(self.client.get('/api/v1/reports/options/').json()['tabs']),['personnel'])
        trainer=m.User.objects.create_user(username='trainer@reports.test',email='trainer@reports.test',role='trainer',branch=self.branch)
        m.Employee.objects.create(branch=self.branch,user=trainer,name='Antrenör')
        self.client.force_login(trainer)
        self.assertEqual(self.client.get('/api/v1/reports/?tab=personnel').status_code,200)
        self.assertEqual(self.client.get('/api/v1/reports/export/?tab=finance').status_code,403)
        self.assertEqual(list(self.client.get('/api/v1/reports/options/').json()['tabs']),['personnel'])

    def test_http_report_uses_read_only_repeatable_snapshot(self):
        get_session().commit();self.client.force_login(self.admin);get_session().commit()
        statements=[]
        def capture(conn,cursor,statement,params,context,many):statements.append(statement)
        event.listen(engine,'before_cursor_execute',capture)
        try:
            with patch('app.main.SessionLocal',SessionLocal):
                response=self.client.get('/api/v1/reports/?tab=finance&from=2026-09-10&to=2026-09-12')
        finally:event.remove(engine,'before_cursor_execute',capture)
        self.assertEqual(response.status_code,200)
        self.assertIn('SET TRANSACTION READ ONLY',statements)
        self.assertTrue(all(sql.lstrip().upper().startswith(('SELECT','SET TRANSACTION READ ONLY')) for sql in statements))

    def test_csv_xlsx_match_all_filtered_rows_and_escape_formula(self):
        self.member.name='=HYPERLINK("bad")';self.member.save()
        params={'tab':'finance','from':'2026-09-10','to':'2026-09-12','type':'membership','pageSize':'1'}
        csv=base64.b64decode(export(self.admin,params)['base64']).decode('utf-8-sig')
        self.assertIn("'=HYPERLINK",csv);self.assertIn('İstanbul',csv);self.assertNotIn('private-member-phone',csv);self.assertIn('P-1',csv);self.assertIn('P-2',csv)
        book=load_workbook(BytesIO(base64.b64decode(export(self.admin,{**params,'format':'xlsx'})['base64'])))
        values=[v.value for row in book.active for v in row]
        self.assertIn('P-2',values);self.assertIn(60,values);self.assertFalse(any(cell.data_type=='f' for row in book.active for cell in row))

    def test_devices_do_not_invent_history_and_audit_hides_private_data(self):
        m.DeviceEvent.objects.create(branch=self.branch,device=self.real,event_type='sensor_fault',level='error',message='Sensör hatası',at=self.at(11))
        report=self.report('devices');self.assertEqual(report['table']['count'],1);self.assertEqual(self.metrics(report)['errors'],1)
        self.assertEqual(self.report('devices',type='servo')['table']['count'],0)
        detail=self.report('audit')['table']['rows'][0][-1];self.assertNotIn('hidden',detail);self.assertIn('Allowed',detail)

    def test_read_only_reports_and_reloading_preserve_business_records(self):
        before={cls.__tablename__:mcount(cls) for cls in [m.Member,m.Subscription,m.Payment,m.Refund,m.Sale,m.StockMovement,m.Audit,m.Visit,m.Passage]}
        statements=[]
        def capture(conn,cursor,statement,params,context,many):statements.append(statement)
        conn=get_session().connection();event.listen(conn,'before_cursor_execute',capture)
        try:
            for tab in ['overview','finance','members','visits','classes','personnel','stock','devices','audit']:
                first=self.report(tab);second=self.report(tab);self.assertEqual(first['table'],second['table'])
        finally:event.remove(conn,'before_cursor_execute',capture)
        self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements))
        self.assertEqual(before,{cls.__tablename__:mcount(cls) for cls in [m.Member,m.Subscription,m.Payment,m.Refund,m.Sale,m.StockMovement,m.Audit,m.Visit,m.Passage]})

    def test_ten_thousand_rows_sql_aggregation_pagination_and_export_limit(self):
        session=get_session();session.execute(insert(m.Payment),[{'id':uuid.uuid4(),'branch_id':self.branch.id,'invoice_id':self.invoice.id,'number':f'LOAD-{i}','amount_cents':1,'method':'cash','actor_id':self.admin.id,'at':self.at(10),'recorded_at':self.at(10)} for i in range(10000)])
        statements=[]
        def capture(conn,cursor,statement,params,context,many):statements.append(statement)
        conn=session.connection();event.listen(conn,'before_cursor_execute',capture);start=time.perf_counter()
        try:report=self.report(pageSize='25',page='2')
        finally:event.remove(conn,'before_cursor_execute',capture)
        self.assertEqual(report['table']['count'],10005);self.assertEqual(len(report['table']['rows']),25);self.assertEqual(self.metrics(report)['gross'],20000)
        self.assertLess(len(statements),35);self.assertLess(time.perf_counter()-start,10)
        print(f'Report load: 10,005 rows, {len(statements)} SELECT queries, {time.perf_counter()-start:.3f}s; 25 returned rows.')
        with self.assertRaises(RuleError):table(select(func.generate_series(1,50001)),[('Count','count')],filters(self.admin,{'tab':'finance'}),True)
        with self.assertRaises(RuleError):self.report(**{'from':'2024-01-01'})


def mcount(cls):return int(get_session().scalar(select(func.count()).select_from(cls)))
