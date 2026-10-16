import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from sqlalchemy.engine import make_url
from tools import demo_test
with patch.dict(os.environ, {'SECRET_KEY': 'test-only-' * 8, 'DATABASE_URL': 'sqlite:///:memory:',
                            'ENVIRONMENT': 'development', 'LOCAL_SAMPLE_DATA': 'false', 'DEMO_MODE': 'false'}):
    from app.core.config import settings


class IsolatedDemoSafety(unittest.TestCase):
    def setUp(self):
        self.url = make_url('postgresql+psycopg://fitgate@127.0.0.1:5434/fitgate_demo')
        self.info = {'Name': '/fitgate-demo-test', 'State': {'Running': True},
                     'HostConfig': {'NetworkMode': 'bridge'}, 'NetworkSettings': {'Ports': {
                         '5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '5434'}]}},
                     'Mounts': [{'Type': 'volume', 'Name': 'fitgate-demo-test-data'}]}

    def docker(self, *args):
        return 'npipe://local' if args[0] == 'context' else json.dumps([self.info])

    def test_exact_target_and_rejections(self):
        with patch.dict(os.environ, {'FITGATE_ISOLATED_DEMO_TEST': '1'}, clear=True), \
                patch.object(settings, 'demo_mode', True), patch.object(settings, 'environment', 'development'), \
                patch.object(demo_test, 'docker', side_effect=self.docker):
            demo_test.guard_target(self.url)
            for changes in [dict(host='localhost'), dict(host='remote'), dict(port=5433),
                            dict(database='fitgate'), dict(username='postgres'), dict(query={'host': 'remote'})]:
                with self.assertRaises(RuntimeError):
                    demo_test.guard_target(self.url.set(**changes))
            for field, value in [('Name', '/fitgate-postgres'), ('State', {'Running': False}),
                                 ('Mounts', [{'Type': 'volume', 'Name': 'fitgate-postgres-data'}]),
                                 ('NetworkSettings', {'Ports': {'5432/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '5434'}]}})]:
                original = copy.deepcopy(self.info)
                self.info[field] = value
                with self.assertRaises(RuntimeError):
                    demo_test.guard_target(self.url)
                self.info = original
            with patch.object(settings, 'demo_mode', False), self.assertRaises(RuntimeError):
                demo_test.guard_target(self.url)
            with patch.object(settings, 'environment', 'production'), self.assertRaises(RuntimeError):
                demo_test.guard_target(self.url)
            with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://remote:2375'}), self.assertRaises(RuntimeError):
                demo_test.guard_target(self.url)
            with patch.dict(os.environ, {'FITGATE_ISOLATED_DEMO_TEST': '0'}), self.assertRaises(RuntimeError):
                demo_test.guard_target(self.url)

    def test_nonempty_database_refuses_migration(self):
        from unittest.mock import Mock
        connection = Mock()
        connection.execute.return_value.one.return_value = ('fitgate_demo', 'fitgate', 170011, '123')
        connection.scalar.return_value = 1
        with patch.object(demo_test, 'docker', return_value='123'), self.assertRaisesRegex(RuntimeError, 'empty'):
            demo_test.preflight(connection)

    def test_sql_identity_and_version_must_match_container(self):
        from unittest.mock import Mock
        for identity in [('fitgate', 'fitgate', 170011, '123'),
                         ('fitgate_demo', 'postgres', 170011, '123'),
                         ('fitgate_demo', 'fitgate', 170010, '123'),
                         ('fitgate_demo', 'fitgate', 170011, 'other-server')]:
            connection = Mock()
            connection.execute.return_value.one.return_value = identity
            with patch.object(demo_test, 'docker', return_value='123'), self.assertRaises(RuntimeError):
                demo_test.preflight(connection)
            connection.scalar.assert_not_called()

    def test_default_installer_still_refuses_test_port(self):
        from tools import install_demo
        with patch.dict(os.environ, {'FITGATE_ISOLATED_DEMO_TEST': '0'}), \
                patch.object(settings, 'demo_mode', True), patch.object(settings, 'environment', 'development'), \
                patch.object(install_demo.subprocess, 'run') as run, self.assertRaises(RuntimeError):
            install_demo.guard(self.url)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
