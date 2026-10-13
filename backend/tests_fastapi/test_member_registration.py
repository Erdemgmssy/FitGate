import uuid
from datetime import timedelta, date
from app import models as m
from app.core import time as timezone
from app.services.business import execute, RuleError
from app.services.projection import snapshot
from tests_fastapi.support import TestCase


class MemberRegistrationTests(TestCase):
    def setUp(self):
        self.branch=m.Branch.objects.create(name='Registration test')
        self.admin=m.User.objects.create_user(username='admin@test.com',email='admin@test.com',password='LongTest123!',role='admin',full_name='Admin',branch=self.branch)
        self.plan=m.Plan.objects.create(branch=self.branch,name='Monthly',price=1500,weekdays=list(range(7)),allowed_from='00:00',allowed_to='23:59')
        self.payload={'name':'Test Member','phone':'0532 999 88 77','consent':True}

    def create(self, **changes):
        result=execute('addMember',{**self.payload,**changes},self.admin,uuid.uuid4())
        return m.Member.objects.get(pk=result['result'])

    def test_optional_package_creates_only_member_and_automatic_number(self):
        member=self.create(number='CLIENT-NUMBER',planId='')
        self.assertEqual(member.number,'GYM-000001')
        self.assertIsNone(member.birth_date)
        self.assertEqual(m.Subscription.objects.count(),0)
        self.assertEqual(m.Invoice.objects.count(),0)
        self.assertEqual(m.Payment.objects.count(),0)
        self.assertEqual(m.Card.objects.count(),0)

    def test_optional_details_and_photo_are_persisted_and_projected(self):
        photo='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jBCEAAAAASUVORK5CYII='
        member=self.create(email='  MEMBER@EXAMPLE.COM ',birthDate='1995-05-10',emergency='Contact',emergencyPhone='+90 555 444 33 22',note='Optional note',photo=photo)
        member.refresh_from_db()
        self.assertEqual(member.birth_date,date(1995,5,10))
        self.assertEqual(member.email,'member@example.com')
        row=snapshot(self.admin)['members'][0]
        self.assertEqual(row['birthDate'],'1995-05-10')
        self.assertEqual(row['emergencyPhone'],'+90 555 444 33 22')
        self.assertEqual(row['photo'],photo)

    def test_plan_payment_and_card_create_atomically(self):
        member=self.create(planId=str(self.plan.id),paid='500',method='cash',uid='aabbccdd')
        self.assertEqual(m.Subscription.objects.get().member_id,member.id)
        self.assertEqual(m.Payment.objects.get().amount_cents,50000)
        self.assertEqual(m.Card.objects.get().uid,'AABBCCDD')
        self.assertEqual(m.Visit.objects.count(),0)

    def test_member_with_card_but_no_membership_has_no_entry_permission(self):
        self.create(uid='AABBCCDD')
        device=m.Device.objects.create(branch=self.branch,code='ENTRY',name='Entry',sensor='ready',last_seen=timezone.now(),direction='both')
        response=execute('authorize',{'uid':'AABBCCDD','deviceId':str(device.id),'direction':'entry'},None,uuid.uuid4(),device)
        self.assertFalse(response['result']['approved'])
        self.assertEqual(response['result']['reason'],'Üyelik geçerli değil')
        self.assertEqual(m.Grant.objects.count(),0)
        self.assertEqual(m.Visit.objects.count(),0)

    def test_duplicate_phone_country_prefix_formats_and_email(self):
        self.create(email='member@example.com')
        for phone in ['+90 (532) 999-88-77','00905329998877','5329998877','05329998877']:
            with self.subTest(phone=phone),self.assertRaises(RuleError): self.create(phone=phone)
        with self.assertRaises(RuleError): self.create(phone='05551112233',email=' MEMBER@EXAMPLE.COM ')
        self.assertEqual(m.Member.objects.count(),1)
        self.assertEqual(self.branch.member_counter,1)

    def test_legacy_phone_format_is_checked_without_rewriting(self):
        legacy=m.Member.objects.create(branch=self.branch,number='LEGACY',name='Legacy',phone='+905329998877',normalized_phone='905329998877',created_by=self.admin)
        with self.assertRaises(RuleError): self.create()
        self.assertEqual(legacy.normalized_phone,'905329998877')

    def test_bad_contact_birth_photo_and_lengths_roll_back(self):
        cases=[{'name':'  '},{'name':'A'*121},{'phone':'abc05329998877'}, {'phone':'123'}, {'phone':'00000000000'}, {'email':'not-an-email'}, {'email':'a..b@example.com'}, {'email':'a@example..com'}, {'birthDate':(timezone.localdate()+timedelta(days=1)).isoformat()}, {'birthDate':'2020-02-31'}, {'birthDate':0}, {'emergencyPhone':'123'}, {'note':'x'*4001}, {'photo':'data:image/png;base64,AAAA'}, {'consent':False}, {'uid':'CARD <BAD>'}]
        for changes in cases:
            with self.subTest(changes=list(changes)),self.assertRaises(RuleError): self.create(**changes)
        self.assertEqual(m.Member.objects.count(),0)
        self.assertEqual(self.branch.member_counter,0)

    def test_duplicate_employee_card_rolls_back_member_sale_and_counter(self):
        m.Employee.objects.create(branch=self.branch,name='Employee',type='fixed',card='STAFF-CARD',hourly_rate=0)
        with self.assertRaises(RuleError):
            self.create(planId=str(self.plan.id),paid='500',method='cash',uid='STAFF-CARD')
        self.assertEqual(m.Member.objects.count(),0)
        self.assertEqual(m.Subscription.objects.count(),0)
        self.assertEqual(m.Payment.objects.count(),0)
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.member_counter,0)

    def test_payment_without_package_is_rejected(self):
        with self.assertRaises(RuleError): self.create(paid='500',method='cash')
        self.assertEqual(m.Member.objects.count(),0)

    def test_edit_contact_details_preserves_other_fields_and_checks_duplicates(self):
        member=self.create(birthDate='1995-05-10')
        other=self.create(phone='05551112233',email='other@example.com')
        with self.assertRaises(RuleError): execute('editMember',{'id':str(member.id),'email':'OTHER@example.com'},self.admin,uuid.uuid4())
        execute('editMember',{'id':str(member.id),'emergencyPhone':'05552223344','birthDate':''},self.admin,uuid.uuid4())
        member.refresh_from_db()
        self.assertIsNone(member.birth_date)
        self.assertEqual(member.phone,'0532 999 88 77')
        self.assertEqual(other.email,'other@example.com')

    def test_api_registration_refreshes_list_and_retries_without_duplicates(self):
        self.client.force_login(self.admin)
        key=str(uuid.uuid4())
        for _ in range(2):
            response=self.client.post('/api/v1/actions/addMember/',data={'payload':{**self.payload,'birthDate':'1995-05-10','uid':'AABBCCDD'}},HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(response.status_code,200)
            body=response.json()
            self.assertEqual(body['db']['members'][0]['id'],body['result'])
            self.assertEqual(body['db']['members'][0]['birthDate'],'1995-05-10')
        self.assertEqual(self.client.get('/api/v1/members/').json()['count'],1)
        self.assertEqual(m.Card.objects.count(),1)

    def test_api_validation_and_other_branch_contacts(self):
        self.client.force_login(self.admin)
        response=self.client.post('/api/v1/actions/addMember/',data={'payload':{**self.payload,'email':'bad'}},HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,400)
        self.assertEqual(m.Member.objects.count(),0)
        other=m.Branch.objects.create(name='Other')
        m.Member.objects.create(branch=other,number='OTHER',name='Other',phone=self.payload['phone'],normalized_phone='05329998877',email='member@example.com',created_by=self.admin)
        self.create(email='member@example.com')
        self.assertEqual(m.Member.objects.count(),2)

    def test_legacy_duplicate_email_does_not_block_unrelated_edit(self):
        member=self.create(email='member@example.com')
        m.Member.objects.create(branch=self.branch,number='LEGACY',name='Legacy',phone='05551112233',normalized_phone='05551112233',email='member@example.com',created_by=self.admin)
        execute('editMember',{'id':str(member.id),'name':'Updated','email':'member@example.com'},self.admin,uuid.uuid4())
        self.assertEqual(member.name,'Updated')
        self.assertEqual(m.Member.objects.count(),2)
        with self.assertRaises(RuleError): self.create(phone='05552223344',email='member@example.com')
