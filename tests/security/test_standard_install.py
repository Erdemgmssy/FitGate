"""Standard installer tests; Docker calls are mocked and no real database is written."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
with patch.dict(os.environ, {'SECRET_KEY': 'test-only-' * 8, 'DATABASE_URL': 'sqlite:///:memory:',
                            'ENVIRONMENT': 'development', 'LOCAL_SAMPLE_DATA': 'false', 'DEMO_MODE': 'false'}):
    from app.core.config import Settings, settings
from sqlalchemy.engine import make_url
from tools import install_sample, install_demo


class StandardInstallTests(unittest.TestCase):
    def setUp(self):
        self.url = make_url('postgresql+psycopg://fitgate@127.0.0.1:5433/fitgate_local')
        self.info = {'Name': '/fitgate-postgres', 'State': {'Running': True},
                     'HostConfig': {'NetworkMode': 'bridge'},
                     'NetworkSettings': {'Ports': {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '5433'}]}},
                     'Mounts': [{'Type': 'volume', 'Name': 'fitgate-postgres-data', 'Destination': '/var/lib/postgresql/data'}],
                     'Config': {'Env': ['POSTGRES_DB=fitgate_local']}}

    def docker(self, *args):
        return 'npipe://local' if args[0] == 'context' else json.dumps([self.info])

    def test_standard_guard_requires_exact_new_local_target(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(settings, 'local_sample_data', True), \
                patch.object(settings, 'environment', 'development'), patch.object(install_sample, 'docker', side_effect=self.docker):
            install_sample.guard_target(self.url)
            for change in [dict(database='fitgate'), dict(database='fitgate_demo'), dict(host='localhost'),
                           dict(host='remote'), dict(port=5434), dict(username='postgres'), dict(query={'host': 'remote'})]:
                with self.assertRaises(RuntimeError): install_sample.guard_target(self.url.set(**change))
            with patch.object(settings, 'environment', 'production'), self.assertRaises(RuntimeError):
                install_sample.guard_target(self.url)
            with patch.object(settings, 'local_sample_data', False), self.assertRaises(RuntimeError):
                install_sample.guard_target(self.url)
            with patch.dict(os.environ, {'FITGATE_ISOLATED_DEMO_TEST': '1'}), self.assertRaises(RuntimeError):
                install_sample.guard_target(self.url)
            with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://remote'}), self.assertRaises(RuntimeError):
                install_sample.guard_target(self.url)
            self.info['Config']['Env'] = ['POSTGRES_DB=fitgate']
            with self.assertRaises(RuntimeError): install_sample.guard_target(self.url)

    def test_standard_profile_routes_shared_seed_through_strict_guard(self):
        with patch.object(settings, 'local_sample_data', True), patch.object(install_sample, 'guard_target') as guard:
            install_demo.guard(self.url)
        guard.assert_called_once_with(self.url)

    def test_existing_database_stops_before_migration(self):
        connection = Mock()
        connection.execute.return_value.one.return_value = ('fitgate_local', 'fitgate', 170011, '123')
        connection.scalar.return_value = 1
        with patch.object(install_sample, 'docker', return_value='123'), self.assertRaisesRegex(RuntimeError, 'Existing'):
            install_sample.preflight(connection)

    def test_failed_preflight_never_invokes_migration_or_seed(self):
        with patch('sys.argv', ['install_sample.py']), patch.object(install_sample, 'guard_target'), \
                patch.object(install_sample, 'preflight', side_effect=RuntimeError('not empty')), \
                patch('app.db.session.engine') as engine, patch.object(install_sample.subprocess, 'run') as run, \
                patch.object(install_demo, 'populate') as populate, self.assertRaises(RuntimeError):
            install_sample.main()
        run.assert_not_called()
        populate.assert_not_called()

    def test_standard_installer_migrates_then_loads_shared_accounts(self):
        order = []
        with patch('sys.argv', ['install_sample.py']), patch.object(install_sample, 'guard_target'), \
                patch.object(install_sample, 'preflight', side_effect=lambda c: order.append('empty')), \
                patch('app.db.session.engine'), \
                patch.object(install_sample.subprocess, 'run', side_effect=lambda *a, **kw: order.append('migration')) as run, \
                patch.object(install_demo, 'populate', side_effect=lambda a: order.append('seed') or True) as populate:
            install_sample.main()
        self.assertEqual(order, ['empty', 'migration', 'seed'])
        self.assertEqual(run.call_args.args[0][-3:], ['alembic', 'upgrade', 'head'])
        populate.assert_called_once_with(install_demo.demo_accounts())

    def test_production_configuration_rejects_public_accounts(self):
        with self.assertRaises(ValueError):
            Settings(_env_file=None, secret_key='x'*64, environment='production', local_sample_data=True)
        self.assertFalse(Settings.model_fields['local_sample_data'].default)
        for target in [self.url.set(host='remote'), self.url.set(database='fitgate'), self.url.set(port=5434)]:
            with self.assertRaises(ValueError):
                Settings(_env_file=None, secret_key='x'*64, environment='development',
                         local_sample_data=True, database_url=str(target))
        Settings(_env_file=None, secret_key='x'*64, environment='development',
                 local_sample_data=True, database_url=str(self.url))

    def test_fresh_config_and_docker_command_without_touching_docker(self):
        spec = importlib.util.spec_from_file_location('local_postgres', ROOT/'backend/tools/local_postgres.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'ROOT', Path(directory)), \
                patch.dict(os.environ, {}, clear=True), patch('sys.argv', ['local_postgres.py']), \
                patch.object(module, 'preflight') as preflight, patch.object(module.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            module.main()
            preflight.assert_called_once_with(Path(directory))
            env = (Path(directory)/'.env.fastapi').read_text()
            self.assertIn('127.0.0.1:5433/fitgate_local', env)
            self.assertIn('LOCAL_SAMPLE_DATA=true', env)
            self.assertIn('DEMO_MODE=false', env)
            self.assertIn('ENVIRONMENT=development', env)
            self.assertNotIn('FitGateDemo2026!', env)
            self.assertIn('POSTGRES_DB=fitgate_local', (Path(directory)/'backups/postgres-docker.env').read_text())
            command = run.call_args_list[0].args[0]
            self.assertEqual(command[-1], 'postgres:17')
            self.assertIn('127.0.0.1:5433:5432', command)
            self.assertIn('type=volume,source=fitgate-postgres-data,target=/var/lib/postgresql/data', command)

    def test_powershell_has_one_ordered_path_and_no_account_prompt(self):
        value = (ROOT/'FitGate-Kurulum.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn('Read-Host', value)
        self.assertNotIn('$choice', value)
        self.assertNotIn('create_admin.py', value)
        self.assertNotIn('--demo', value)
        self.assertLess(value.index('tools/local_postgres.py }'), value.index('tools/install_sample.py }'))

    def test_launcher_fixture_replaces_docker_before_starting_processes(self):
        source = (ROOT/'tests/launcher/Test-Launcher.ps1').read_text(encoding='utf-8-sig')
        self.assertLess(source.index("$stub = [IO.File]::ReadAllText"), source.index('$sentinel = Start-Process'))
        self.assertIn("throw 'Cannot isolate Docker access", source)
        stub = (ROOT/'tests/launcher/fixtures/docker-stub.ps1').read_text()
        self.assertNotIn('Start-Process', stub)
        self.assertNotIn('& docker', stub)

    def test_shared_sample_generator_produces_complete_fictional_records(self):
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import Session
        from app.db.base import Base
        from app.db.session import active_session
        from app import models as m
        from app.core.security import check_password
        from tools.demo_seed import seed
        engine = create_engine('sqlite:///:memory:')
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            token = active_session.set(session)
            try:
                accounts = install_demo.demo_accounts()
                with patch.object(install_demo, 'guard'):
                    seed({'memberUids': ['DEMO-MEMBER-%02d' % i for i in range(4)],
                          'employeeUids': ['DEMO-STAFF-%02d' % i for i in range(5)]},
                         accounts, None, None, portable=True)
                self.assertEqual(m.Member.objects.count(), 20)
                self.assertEqual(m.Employee.objects.count(), 5)
                self.assertEqual(m.User.objects.count(), 6)
                self.assertEqual(m.Plan.objects.count(), 5)
                self.assertEqual(m.Product.objects.count(), 6)
                self.assertEqual(m.Payment.objects.count(), 13)
                self.assertEqual(m.Shift.objects.filter(simulated=True).count(), 5)
                self.assertEqual(m.Device.objects.count(), 0)
                for account in accounts:
                    user = m.User.objects.get(email=account['email'])
                    self.assertTrue(check_password(account['password'], user.password))
                    self.assertEqual(user.role, account['role'])
                for invoice in m.Invoice.objects.all():
                    self.assertEqual(sum(i.amount_cents for i in m.Installment.objects.filter(invoice=invoice)), invoice.total_cents)
                for product in m.Product.objects.all():
                    self.assertEqual(product.stock, sum(s.quantity for s in m.StockMovement.objects.filter(product=product)))
            finally:
                session.rollback()
                active_session.reset(token)
        engine.dispose()


if __name__ == '__main__': unittest.main()
