"""Demo tooling tests use only synthetic credentials and identifiers."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from sqlalchemy.engine import make_url
from app import models as m
from app.db import transaction
from app.services.membership import entry_sub, status
from app.core import time as tz
from tests_fastapi.support import TestCase
from tools import demo_seed as demo


def config():
    return {'target': {'host': '127.0.0.1', 'port': 5433, 'database': 'fitgate'},
            'memberUids': [f'FA00000{i}' for i in range(1, 5)],
            'employeeUids': [f'FB00000{i}' for i in range(1, 4)], 'serialPort': 'COM6', 'expectedFirmware': 5}


class DemoSeedTests(TestCase):
    def test_refuses_remote_wrong_port_and_wrong_database(self):
        for url in ['postgresql://fitgate@remote:5433/fitgate', 'postgresql://fitgate@127.0.0.1:5432/fitgate',
                    'postgresql://fitgate@127.0.0.1:5433/production', 'postgresql://root@127.0.0.1:5433/fitgate']:
            with self.subTest(target=url), self.assertRaises(RuntimeError), patch.object(demo, 'command') as command:
                demo.guard(make_url(url), config())
            command.assert_not_called()

    def test_refuses_config_outside_ignored_directory(self):
        with self.assertRaises(RuntimeError): demo.local_config(Path('public-seed.json'))
        with patch.object(Path, 'read_text', return_value=json.dumps(config())), patch.object(demo.subprocess, 'run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(RuntimeError): demo.local_config(demo.LOCAL/'config.json')

    def test_refuses_duplicate_cards_before_reset(self):
        value = config(); value['employeeUids'][0] = value['memberUids'][0]
        with patch.object(Path, 'read_text', return_value=json.dumps(value)), patch.object(demo.subprocess, 'run') as run:
            run.return_value.returncode = 0
            with self.assertRaises(RuntimeError): demo.local_config(demo.LOCAL/'config.json')

    def test_strong_unique_generated_accounts(self):
        accounts = demo.credentials()
        self.assertEqual(len({row['password'] for row in accounts}), 4)
        self.assertTrue(all(len(row['password']) >= 32 and row['email'].endswith('@example.com') for row in accounts))

    def test_seed_relationships_finance_permissions_and_no_fake_passages(self):
        accounts = demo.credentials()
        result = demo.seed(config(), accounts, 'synthetic-device-secret', 'DEMO-TEST-DEVICE')
        self.assertEqual(result['members'], 24); self.assertEqual(result['employees'], 3)
        self.assertEqual(result['collectedCents'], 2350000); self.assertEqual(result['debtCents'], 3800000)
        self.assertEqual(result['cashCents'], 1860000); self.assertEqual(result['bookings'], 7)
        self.assertEqual(result['membershipStates'], {'active':8,'expired':4,'frozen':3,'pending':3,'cancelled':3})
        json.dumps(result)
        for index, uid in enumerate(config()['memberUids']):
            member = m.Card.objects.get(uid=uid).member
            self.assertEqual(entry_sub(member, tz.now()) is not None, index < 2)
        from app.services.projection import snapshot
        for account in accounts[1:]:
            user = m.User.objects.get(email=account['email'])
            data = snapshot(user)
            self.assertEqual(len(data['employees']), 1)
            self.assertEqual(data['employees'][0]['userId'], user.id)
        for account in accounts:
            response = self.client.post('/api/v1/auth/login/', {'email':account['email'],'password':account['password']},
                                        HTTP_X_CSRFToken=self.client.csrf)
            self.assertEqual(response.status_code, 200)

    def test_invalid_seed_rolls_back_whole_operation(self):
        invalid = config(); invalid['employeeUids'][1] = invalid['employeeUids'][0]
        with self.assertRaises(Exception):
            with transaction.atomic(): demo.seed(invalid, demo.credentials(), 'synthetic-secret', 'DEMO-ROLLBACK')
        self.assertEqual(m.User.objects.count(), 0)
        self.assertEqual(m.Branch.objects.count(), 0)
