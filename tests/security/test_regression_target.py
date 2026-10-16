"""Regression runner must refuse the live server before connecting or resetting."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'backend'))
from sqlalchemy.engine import make_url
with patch.dict(os.environ, {'SECRET_KEY': 'test-only-' * 8, 'DATABASE_URL': 'sqlite:///:memory:',
                            'ENVIRONMENT': 'development', 'LOCAL_SAMPLE_DATA': 'false', 'DEMO_MODE': 'false'}):
    from app.core.config import settings
from tools import isolated_regression as runner


class RegressionTargetTests(unittest.TestCase):
    def test_target_is_fixed_to_disposable_database(self):
        url = make_url('postgresql+psycopg://fitgate@127.0.0.1:5434/fitgate_demo')
        with patch('tools.demo_test.guard_target') as guard:
            target = runner.checked_test_url(url)
        guard.assert_called_once_with(url)
        self.assertEqual((target.host, target.port, target.database), ('127.0.0.1', 5434, 'fitgate_fastapi_test'))

    def test_guard_failure_precedes_database_engine_creation(self):
        with patch('sys.argv', ['test_fastapi.py', '--isolated-demo-container']), \
                patch('tools.demo_test.guard_target', side_effect=RuntimeError('wrong server')), \
                patch('sqlalchemy.create_engine') as engine, self.assertRaises(RuntimeError):
            runner.main()
        engine.assert_not_called()

    def test_sql_identity_mismatch_refuses_reset(self):
        for row in [('fitgate', 'fitgate', 170011, '123'), ('fitgate_fastapi_test', 'fitgate', 170011, 'other-server')]:
            connection = Mock()
            connection.execute.return_value.one.return_value = row
            with self.assertRaises(RuntimeError): runner.verify_identity(connection, 'fitgate_fastapi_test', '123')

    def test_missing_explicit_flag_does_not_connect(self):
        with patch('sys.argv', ['test_fastapi.py']), patch('sqlalchemy.create_engine') as engine, self.assertRaises(SystemExit):
            runner.main()
        engine.assert_not_called()


if __name__ == '__main__': unittest.main()
