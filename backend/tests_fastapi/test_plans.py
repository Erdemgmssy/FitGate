import uuid
from datetime import timedelta,date
from unittest.mock import patch
from decimal import Decimal
from app import models as m
from app.core import time as timezone
from app.services.business import execute,RuleError,end_for
from app.services.projection import wire,snapshot
from app.services.plans import entry_error
from app.services.dashboard import summary
from tests_fastapi.support import TestCase


class PlanTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Package test')
        self.admin=m.User.objects.create_user(username='plan-admin@test.com',email='plan-admin@test.com',role='admin',branch=self.branch)
        self.staff=m.User.objects.create_user(username='plan-staff@test.com',email='plan-staff@test.com',role='staff',branch=self.branch)
        self.now=timezone.now()
        self.payload={'name':'Contract package','description':'Test','kind':'hybrid','durationValue':1,'durationUnit':'month','price':'2000','sessions':10,'weekdays':list(range(7)),'from':'00:00','to':'23:59','freezeDays':14,'freezeMin':2,'freezeMax':7,'freezeLimit':2,'active':True,'campaigns':[]}
        self.act('savePlan',self.payload);self.plan=m.Plan.objects.get()
        self.device=m.Device.objects.create(branch=self.branch,code='PLAN-REAL',sensor='ready',last_seen=self.now)

    def act(self,action,p,user=None,at=None):
        with patch('app.services.business.timezone.now',return_value=at or self.now):return execute(action,p,user or self.admin,uuid.uuid4())
    def update(self,**changes):return self.act('savePlan',{**wire(self.plan),'confirmed':True,**changes})
    def buy(self,**extra):
        self.act('addMember',{'name':'Package member','phone':'05329994455','consent':True,'planId':str(self.plan.id),'uid':'AABBCCDD',**extra})
        self.member=m.Member.objects.get();self.sub=m.Subscription.objects.get()
    def scan(self,direction='entry',seconds=0):
        at=self.now+timedelta(seconds=seconds);self.device.last_seen=at;self.device.save()
        with patch('app.services.business.timezone.now',return_value=at):return execute('authorize',{'uid':'AABBCCDD','direction':direction},None,uuid.uuid4(),self.device)['result']
    def passage(self,result,seconds):
        at=self.now+timedelta(seconds=seconds)
        with patch('app.services.business.timezone.now',return_value=at):return execute('confirmPassage',{'id':result['grantId'],'eventId':str(uuid.uuid4()),'direction':result['direction'],'occurredAt':at.isoformat()},None,uuid.uuid4(),self.device)

    def test_calendar_months_weeks_days_and_leap_year(self):
        for unit,value,start,expected in [('month',3,date(2026,1,1),date(2026,3,31)),('day',90,date(2026,1,1),date(2026,3,31)),('month',3,date(2026,2,1),date(2026,4,30)),('day',90,date(2026,2,1),date(2026,5,1)),('month',1,date(2026,1,31),date(2026,2,27)),('year',1,date(2024,2,29),date(2025,2,27)),('week',2,date(2026,1,1),date(2026,1,14))]:
            self.plan.duration_unit=unit;self.plan.duration_value=value
            self.assertEqual(end_for(self.plan,start),expected)

    def test_invalid_combinations_and_permissions(self):
        invalid=[{'kind':'timed','sessions':10},{'kind':'sessions','sessions':None},{'kind':'sessions','durationValue':2},{'from':'25:00'},{'from':'10:00','to':'10:00'},{'freezeMin':8,'freezeMax':3},{'freezeDays':0,'freezeMax':7},{'dailyLimit':0},{'price':'1.001'},{'saleStart':'2026-11-01','saleEnd':'2026-10-01'}]
        for changes in invalid:
            with self.subTest(changes=changes),self.assertRaises(RuleError):self.act('savePlan',{**self.payload,**changes})
        with self.assertRaises(RuleError):self.act('savePlan',self.payload,self.staff)

    def test_confirmation_revision_and_history_immutable(self):
        self.buy(paid='500');invoice=m.Invoice.objects.get();old_rules=dict(self.sub.rules)
        with self.assertRaises(RuleError):self.act('savePlan',{**wire(self.plan),'price':'3000'})
        previous=wire(self.plan);self.update(price='3000',sessions=20,dailyLimit=1)
        self.assertEqual(self.plan.revision,2);self.assertEqual(self.sub.rules,old_rules)
        self.assertEqual(self.sub.remaining,10);self.assertEqual(invoice.total_cents,200000);self.assertEqual(m.Payment.objects.get().amount_cents,50000)
        with self.assertRaises(RuleError):self.act('savePlan',{**previous,'confirmed':True})
        with self.assertRaises(RuleError):self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id),'planRevision':previous['revision']})
        self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id)})
        other=m.Subscription.objects.exclude(pk=self.sub.id).first();self.assertEqual(other.price_cents,300000);self.assertEqual(other.rules['dailyLimit'],1)

    def test_pure_sessions_have_no_end_date_and_dashboard_works(self):
        self.update(kind='sessions',durationValue=0,sessions=2);self.buy()
        self.assertIsNone(self.sub.end);self.assertIsNone(wire(self.sub)['remainingDays'])
        self.assertEqual(summary(self.admin,timezone.localdate())['metrics']['activeMembers'],1)
        result=self.scan();self.assertTrue(result['approved']);self.assertEqual(self.sub.remaining,2)
        self.passage(result,1);self.assertEqual(self.sub.remaining,1)
        self.assertTrue(snapshot(self.admin)['plans'][0]['usedCount'])

    def test_unlimited_entry_consumes_no_sessions(self):
        self.update(kind='timed',sessions=None);self.buy();result=self.scan();self.assertTrue(result['approved'])
        self.passage(result,1);self.assertIsNone(self.sub.remaining)

    def test_daily_limit_only_counts_confirmed_entries_and_exit_is_free(self):
        self.update(dailyLimit=1);self.buy();result=self.scan();self.assertTrue(result['approved'])
        self.assertEqual(entry_error(self.sub,self.now),'');self.passage(result,1)
        self.assertEqual(entry_error(self.sub,self.now),'Günlük giriş limiti doldu')
        self.passage(self.scan('exit',15),16)
        result=self.scan('entry',30);self.assertFalse(result['approved']);self.assertIn('Günlük',result['reason']);self.assertEqual(self.sub.remaining,9)

    def test_weekly_limit_resets_next_monday(self):
        self.update(weeklyLimit=1);self.buy();self.passage(self.scan(),1)
        tomorrow=self.now+timedelta(days=1)
        if timezone.localtime(tomorrow).weekday()!=0:self.assertEqual(entry_error(self.sub,tomorrow),'Haftalık giriş limiti doldu')
        next_week=self.now+timedelta(days=7-timezone.localtime(self.now).weekday())
        self.assertEqual(entry_error(self.sub,next_week),'')

    def test_overnight_hours_use_start_day(self):
        self.update(**{'from':'22:00','to':'06:00','weekdays':[1]});self.buy()
        monday=timezone.make_aware(__import__('datetime').datetime(2026,10,12,23))
        self.assertEqual(entry_error(self.sub,monday),'');self.assertEqual(entry_error(self.sub,monday+timedelta(hours=6)),'')
        self.assertIn('saat',entry_error(self.sub,monday+timedelta(hours=7)))
        self.assertIn('saat',entry_error(self.sub,monday+timedelta(days=1)))

    def test_sale_windows_and_passive_do_not_change_existing_contract(self):
        self.buy();self.update(active=False)
        self.assertTrue(self.scan()['approved'])
        with self.assertRaises(RuleError):self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id)})
        future=(timezone.localdate()+timedelta(days=2)).isoformat();self.update(active=True,saleStart=future)
        with self.assertRaises(RuleError):self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id)})

    def campaign(self,**changes):
        today=timezone.localdate().isoformat()
        return {'id':'test-campaign','name':'Summer','type':'percent','value':'25','start':today,'end':today,'active':True,**changes}

    def test_campaign_discount_snapshot_and_no_stacking(self):
        self.update(campaigns=[self.campaign()]);self.buy();invoice=m.Invoice.objects.get()
        self.assertEqual(invoice.total_cents,150000);self.assertEqual(invoice.discount_cents,50000)
        self.update(price='3000',campaigns=[])
        self.assertEqual(invoice.total_cents,150000);self.assertEqual(self.sub.rules['appliedCampaign']['name'],'Summer')
        self.update(campaigns=[self.campaign()])
        with self.assertRaises(RuleError):self.act('renew',{'memberId':str(self.member.id),'planId':str(self.plan.id),'discount':'1'})

    def test_campaign_overlap_and_decimal_rounding(self):
        with self.assertRaises(RuleError):self.update(campaigns=[self.campaign(),self.campaign(id='other')])
        self.update(price='100.01',campaigns=[self.campaign(value='50')]);self.buy()
        self.assertEqual(m.Invoice.objects.get().discount_cents,5001);self.assertEqual(m.Invoice.objects.get().total_cents,5000)

    def test_freeze_contract_bounds_and_count(self):
        self.buy();first=timezone.localdate();end=first+timedelta(days=1)
        with self.assertRaises(RuleError):self.act('freeze',{'id':str(self.sub.id),'start':first.isoformat(),'end':first.isoformat(),'reason':'Too short'})
        self.act('freeze',{'id':str(self.sub.id),'start':first.isoformat(),'end':end.isoformat(),'reason':'Holiday'})
        self.update(freezeDays=30,freezeMin=1,freezeMax=30,freezeLimit=10)
        self.assertEqual(self.sub.rules['freezeLimit'],2);self.assertEqual(self.sub.rules['freezeMax'],7)
        self.assertEqual(self.sub.frozen_days,2)
        self.act('resume',{'id':str(self.sub.id)})
        with self.assertRaises(RuleError):self.act('freeze',{'id':str(self.sub.id),'start':first.isoformat(),'end':(first+timedelta(days=7)).isoformat(),'reason':'Too long'})
        self.act('freeze',{'id':str(self.sub.id),'start':first.isoformat(),'end':end.isoformat(),'reason':'Second freeze'})
        self.act('resume',{'id':str(self.sub.id)})
        with self.assertRaises(RuleError):self.act('freeze',{'id':str(self.sub.id),'start':first.isoformat(),'end':end.isoformat(),'reason':'Third freeze exceeds original contract'})

    def test_expired_membership_exit_does_not_consume_session(self):
        self.buy();self.passage(self.scan(),1);self.sub.end=timezone.localdate()-timedelta(days=1);self.sub.start=self.sub.end;self.sub.save()
        result=self.scan('exit',15);self.assertTrue(result['approved']);self.passage(result,16);self.assertEqual(self.sub.remaining,9)
