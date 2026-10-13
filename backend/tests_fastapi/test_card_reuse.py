import uuid
from datetime import timedelta
from app import models as m
from app.core import time as timezone
from app.db.session import get_session
from app.services.business import execute, RuleError
from app.services.projection import snapshot
from sqlalchemy.exc import IntegrityError
from tests_fastapi.support import TestCase


class CardReuseTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Reuse test')
        self.staff=m.User.objects.create_user(username='reuse@test.com',email='reuse@test.com',password='LongTest123!',role='staff',branch=self.branch)
        self.old=m.Member.objects.create(branch=self.branch,number='OLD',name='Erdem',phone='05321112233',normalized_phone='5321112233',created_by=self.staff)
        self.new=m.Member.objects.create(branch=self.branch,number='NEW',name='New owner',phone='05321112234',normalized_phone='5321112234',created_by=self.staff)
        self.card=m.Card.objects.create(branch=self.branch,member=self.old,uid='AABBCCDD')
        self.device=m.Device.objects.create(branch=self.branch,code='REUSE-TEST',sensor='ready',last_seen=timezone.now())

    def act(self,action,payload,key=None):
        return execute(action,payload,self.staff,key or uuid.uuid4())

    def release(self,key=None):
        return self.act('releaseCard',{'id':str(self.card.id),'confirmed':True},key)

    def test_return_reassign_keeps_history_and_unique_uid(self):
        visit=m.Visit.objects.create(branch=self.branch,member=self.old,device=self.device,entry=timezone.now()-timedelta(hours=1),exit=timezone.now())
        key=uuid.uuid4(); self.release(key); self.release(key)
        self.card.refresh_from_db()
        self.assertIsNone(self.card.member_id); self.assertEqual(self.card.status,'available')
        self.assertEqual(next(row for row in snapshot(self.staff)['cards'] if row['id']==str(self.card.id))['memberId'],None)
        audit=m.Audit.objects.get(type='releaseCard')
        self.assertEqual(audit.before['memberId'],str(self.old.id)); self.assertIsNone(audit.after['memberId'])
        self.act('assignCard',{'memberId':str(self.new.id),'uid':'aabbccdd'})
        self.card.refresh_from_db(); visit.refresh_from_db()
        self.assertEqual(self.card.member_id,self.new.id); self.assertEqual(self.card.status,'active')
        self.assertEqual(visit.member_id,self.old.id); self.assertEqual(m.Card.objects.count(),1)
        self.assertEqual(m.Audit.objects.filter(type='releaseCard').count(),1)
        self.assertEqual(m.Audit.objects.get(type='assignCard').after['memberId'],str(self.new.id))

    def test_cancelled_and_lost_require_explicit_return(self):
        for status in ['inactive','lost','cancelled']:
            self.card.status=status; self.card.member=self.old; self.card.member_id=self.old.id; self.card.save()
            with self.assertRaises(RuleError): self.act('assignCard',{'memberId':str(self.new.id),'uid':self.card.uid})
            with self.assertRaises(RuleError): self.act('releaseCard',{'id':str(self.card.id)})
            self.release(); self.assertIsNone(self.card.member_id)

    def test_open_visit_and_pending_grant_block_return(self):
        visit=m.Visit.objects.create(branch=self.branch,member=self.old,device=self.device,entry=timezone.now())
        with self.assertRaises(RuleError): self.release()
        visit.exit=timezone.now(); visit.save()
        attempt=m.Attempt.objects.create(branch=self.branch,member=self.old,card=self.card.uid,device=self.device,direction='entry',status='granted')
        grant=m.Grant.objects.create(branch=self.branch,member=self.old,attempt=attempt,device=self.device,direction='entry',expires_at=timezone.now()+timedelta(seconds=30))
        with self.assertRaises(RuleError): self.release()
        grant.expires_at=timezone.now()-timedelta(seconds=1); grant.save()
        self.release()

    def test_stock_card_denied_and_cannot_directly_activate(self):
        self.release()
        result=execute('authorize',{'uid':self.card.uid,'direction':'entry'},None,uuid.uuid4(),self.device)['result']
        self.assertFalse(result['approved']); self.assertIsNone(result['memberId'])
        with self.assertRaises(RuleError): self.act('cardStatus',{'id':str(self.card.id),'status':'active'})
        with self.assertRaises(RuleError): self.release()

    def test_other_branch_cannot_return_or_take_stock_card(self):
        branch=m.Branch.objects.create(name='Other')
        other=m.User.objects.create_user(username='other-reuse@test.com',email='other-reuse@test.com',role='staff',branch=branch)
        member=m.Member.objects.create(branch=branch,number='OTHER',name='Other',phone='05321112235',created_by=other)
        with self.assertRaises(RuleError): execute('releaseCard',{'id':str(self.card.id),'confirmed':True},other,uuid.uuid4())
        self.release()
        with self.assertRaises(RuleError): execute('assignCard',{'memberId':str(member.id),'uid':self.card.uid},other,uuid.uuid4())

    def test_available_card_requires_no_member_in_database(self):
        with self.assertRaises(IntegrityError),get_session().begin_nested():
            m.Card.objects.create(branch=self.branch,member=self.old,uid='BAD-STOCK',status='available')

    def test_return_cancels_stale_capture_and_employee_collision_stays_blocked(self):
        capture=m.CardCapture.objects.create(branch=self.branch,device=self.device,member=self.old,actor=self.staff,expires_at=timezone.now()+timedelta(seconds=45),uid=self.card.uid,captured_at=timezone.now())
        self.release(); capture.refresh_from_db(); self.assertTrue(capture.cancelled)
        m.Employee.objects.create(branch=self.branch,name='Employee',card=self.card.uid)
        with self.assertRaises(RuleError): self.act('assignCard',{'memberId':str(self.new.id),'uid':self.card.uid})

    def test_http_return_and_assign_refresh_the_card_list(self):
        self.client.force_login(self.staff)
        response=self.client.post('/api/v1/actions/releaseCard/',{'payload':{'id':str(self.card.id),'confirmed':True}},HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json()['db']['cards'][0]['memberId'])
        self.assertEqual(response.json()['db']['cards'][0]['status'],'available')
        response=self.client.post('/api/v1/actions/assignCard/',{'payload':{'memberId':str(self.new.id),'uid':self.card.uid}},HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['db']['cards'][0]['memberId'],str(self.new.id))
