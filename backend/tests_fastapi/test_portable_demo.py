"""Regression tests run only through tools/test_fastapi.py's isolated database."""
from unittest.mock import patch
from sqlalchemy.engine import make_url
from tests_fastapi.support import TestCase
from tools import install_demo as demo
from app import models as m
from contextlib import nullcontext
from app.db.session import get_session
import json
import uuid


def accounts():
    return [{'email': f'{i}.demo@example.com', 'name': f'Demo {i}',
             'role': 'admin' if i == 0 else 'trainer' if i == 2 else 'staff',
             'password': 'Fictional-test-only-987!' + str(i)} for i in range(6)]


class PortableDemoTests(TestCase):
    def test_explicit_flag_selects_public_accounts_without_prompt(self):
        with patch('sys.argv', ['install_demo.py', '--local-demo-accounts']), patch.object(demo, 'guard'), patch.object(demo.getpass, 'getpass') as prompt, patch.object(demo, 'populate') as populate:
            demo.main()
        prompt.assert_not_called()
        self.assertEqual(populate.call_args.args[0], demo.demo_accounts())

    def test_password_prompt_remains_without_explicit_flag(self):
        with patch('sys.argv', ['install_demo.py']), patch.object(demo, 'guard'), patch.object(demo.getpass, 'getpass', return_value='Custom-password-2026!') as prompt, patch.object(demo, 'populate') as populate:
            demo.main()
        self.assertEqual(prompt.call_count, 12)
        self.assertTrue(all(a['password'] == 'Custom-password-2026!' for a in populate.call_args.args[0]))
        from app.core.config import Settings
        self.assertFalse(Settings.model_fields['demo_mode'].default)

    def test_refuses_existing_data_without_changing_it(self):
        branch = m.Branch.objects.create(name='Preserved')
        with patch.object(demo, 'guard'), patch.object(demo.SessionLocal, 'begin',
                return_value=nullcontext(get_session())):
            with self.assertRaises(RuntimeError):
                demo.populate(accounts())
        self.assertEqual(m.Branch.objects.get().id, branch.id)
        self.assertEqual(m.User.objects.count(), 0)

    def test_repeat_is_noop_and_does_not_change_passwords(self):
        from tools.demo_seed import seed
        config = {'memberUids': ['DEMO-MEMBER-%02d' % i for i in range(4)],
                  'employeeUids': ['DEMO-STAFF-%02d' % i for i in range(5)]}
        with patch.object(demo, 'guard'):
            seed(config, accounts(), None, None, portable=True)
        hashes = {u.id: u.password for u in m.User.objects.all()}
        with patch.object(demo, 'guard'), patch.object(demo.SessionLocal, 'begin',
                return_value=nullcontext(get_session())):
            self.assertFalse(demo.populate(accounts()))
        self.assertEqual(m.Member.objects.count(), 20)
        self.assertEqual({u.id: u.password for u in m.User.objects.all()}, hashes)

    def test_refuses_live_remote_and_wrong_database(self):
        for value in ['postgresql://localhost:5433/fitgate',
                      'postgresql://remote:5433/fitgate_demo', 'sqlite:///fitgate_demo']:
            with self.assertRaises(RuntimeError):
                demo.guard(make_url(value))

    def test_portable_seed_real_login_and_relationships(self):
        from tools.demo_seed import seed
        from app.services.projection import snapshot
        config = {'memberUids': ['DEMO-MEMBER-%02d' % i for i in range(4)],
                  'employeeUids': ['DEMO-STAFF-%02d' % i for i in range(5)]}
        with patch.object(demo, 'guard'):
            seed(config, demo.demo_accounts(), None, None, portable=True)
        self.assertEqual(m.Member.objects.count(), 20)
        self.assertEqual(m.Employee.objects.count(), 5)
        self.assertEqual(m.Shift.objects.filter(simulated=True).count(), 5)
        self.assertEqual(m.Device.objects.count(), 0)
        for account in demo.demo_accounts():
            response = self.client.post('/api/v1/auth/login/',
                                        {'email': account['email'], 'password': account['password']},
                                        HTTP_X_CSRFToken=self.client.csrf)
            self.assertEqual(response.status_code, 200)
            user = response.json()['user']
            self.assertEqual(user['role'], account['role'])
            self.assertEqual(user['personnelPermissions']['manualAttendance'], account['role'] == 'admin')
            self.assertEqual(user['personnelPermissions']['memberManagement'], account['role'] != 'trainer')
            self.assertTrue(m.User.objects.get(email=account['email']).password.startswith('$argon2'))
            result = self.client.post('/api/v1/actions/saveRolePolicy/',
                {'payload': {'role': 'staff', 'permissions': {'manualAttendance': False}}},
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            self.assertEqual(result.status_code, 200 if account['role'] == 'admin' else 403)
            snapshot(m.User.objects.get(email=account['email']))
        hashes = {u.id: u.password for u in m.User.objects.all()}
        with patch.object(demo, 'guard'), patch.object(demo.SessionLocal, 'begin',
                return_value=nullcontext(get_session())):
            self.assertFalse(demo.populate(demo.demo_accounts()))
        self.assertEqual(m.User.objects.count(), 6)
        self.assertEqual({u.id: u.password for u in m.User.objects.all()}, hashes)
        for invoice in m.Invoice.objects.all():
            self.assertEqual(sum(i.amount_cents for i in m.Installment.objects.filter(invoice=invoice)), invoice.total_cents)
        for product in m.Product.objects.all():
            self.assertEqual(product.stock, sum(s.quantity for s in m.StockMovement.objects.filter(product=product)))

    def test_public_credentials_guard(self):
        url = make_url('postgresql://localhost:5433/fitgate_demo')
        info = [{'State': {'Running': True}, 'NetworkSettings': {'Ports': {
            '5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '5433'}]}}}]
        with patch.object(demo.settings, 'demo_mode', True), patch.object(demo.settings, 'environment', 'development'), patch.object(demo.subprocess, 'run') as run:
            run.return_value.stdout = json.dumps(info)
            demo.guard(url)
            for target in ['fitgate', 'fitgate_fastapi_test']:
                with self.assertRaises(RuntimeError):
                    demo.guard(url.set(database=target))
            for invalid in [url.set(host='remote'), url.set(port=5432), make_url('sqlite:///fitgate_demo')]:
                with self.assertRaises(RuntimeError):
                    demo.guard(invalid)
            with patch.object(demo.settings, 'environment', 'production'):
                with self.assertRaises(RuntimeError):
                    demo.guard(url)
            with patch.object(demo.settings, 'demo_mode', False):
                with self.assertRaises(RuntimeError):
                    demo.guard(url)
            info[0]['NetworkSettings']['Ports']['5432/tcp'].append({'HostIp': '0.0.0.0', 'HostPort': '5433'})
            run.return_value.stdout = json.dumps(info)
            with self.assertRaises(RuntimeError):
                demo.guard(url)
        from tools.demo_seed import seed
        with self.assertRaises(RuntimeError):
            seed({}, demo.demo_accounts(), None, None, portable=True)
