"""Portable fictional demo. No reset, backup, device or live database operations."""
import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, select, text
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal, active_session
from app import models as m
from tools.demo_seed import seed


def guard(url):
    if (not settings.demo_mode or settings.environment != 'development' or url.get_backend_name() != 'postgresql'
            or url.host not in ('127.0.0.1', 'localhost') or url.port != 5433
            or url.database != 'fitgate_demo'):
        raise RuntimeError('Only explicitly selected local fitgate_demo is allowed')

    result = subprocess.run(['docker', 'inspect', 'fitgate-postgres'],
                            capture_output=True, text=True, check=True, timeout=15)
    info = json.loads(result.stdout)[0]
    bindings = info['NetworkSettings']['Ports'].get('5432/tcp') or []
    if (not info['State']['Running'] or not bindings
            or any(b['HostIp'] != '127.0.0.1' or b['HostPort'] != '5433' for b in bindings)):
        raise RuntimeError('Demo PostgreSQL must be bound exclusively to loopback')


DEMO_PASSWORD = 'FitGateDemo2026!'


def demo_accounts():
    return [{'email': 'admin@fitgate.demo' if i == 0 else f'personel{i}@fitgate.demo',
             'name': 'Demo Admin' if i == 0 else f'Demo Personel {i}',
             'role': 'admin' if i == 0 else 'trainer' if i == 2 else 'staff',
             'password': DEMO_PASSWORD} for i in range(6)]


def populate(accounts):
    guard(engine.url)
    with SessionLocal.begin() as session:
        token = active_session.set(session)
        try:
            session.execute(text('SELECT pg_advisory_xact_lock(74617432)'))
            tables = set(inspect(session.connection()).get_table_names())
            if tables != set(Base.metadata.tables) | {'alembic_version'}:
                raise RuntimeError('Apply Alembic migrations to an empty database first')
            # Lock all application tables before checking emptiness; never truncate.
            quoted = ', '.join(engine.dialect.identifier_preparer.quote(t) for t in Base.metadata.tables)
            session.execute(text('LOCK TABLE ' + quoted + ' IN EXCLUSIVE MODE'))
            branches = list(session.scalars(select(m.Branch)))
            if len(branches) == 1 and branches[0].configuration.get('portableDemoSeed') == 'v1':
                return False
            if any(session.scalar(select(text('count(*)')).select_from(t)) for t in Base.metadata.tables.values()):
                raise RuntimeError('Database is not empty; nothing changed')
            if len(accounts) != 6 or any(len(a['password']) < 12 for a in accounts):
                raise RuntimeError('Six accounts with passwords of at least 12 characters required')
            config = {'memberUids': [], 'employeeUids': ['DEMO-STAFF-%02d' % i for i in range(5)]}
            # Synthetic labels cannot be mistaken for physical hexadecimal RFID UIDs.
            config['memberUids'] = ['DEMO-MEMBER-%02d' % i for i in range(4)]
            seed(config, accounts, None, None, portable=True)
            return True
        finally:
            active_session.reset(token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-demo-accounts', action='store_true',
                        help='Use public credentials only in explicitly enabled local demo mode')
    args = parser.parse_args()
    guard(engine.url)
    if args.local_demo_accounts:
        print('Demo created.' if populate(demo_accounts()) else 'Demo already installed; nothing changed.')
        return
    accounts = []
    for key, role in [('admin', 'admin'), ('reception', 'staff'), ('trainer', 'trainer'),
                      ('floor', 'staff'), ('sales', 'staff'), ('support', 'staff')]:
        email = key + '.demo@example.com'
        password = getpass.getpass(email + ' password (12+ characters): ')
        if len(password) < 12 or password != getpass.getpass('Confirm password: '):
            raise RuntimeError('Invalid password or confirmation')
        accounts.append({'email': email, 'name': 'Demo ' + key, 'role': role, 'password': password})
    print('Demo created.' if populate(accounts) else 'Demo already installed; nothing changed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Demo installation refused or failed; transaction rolled back. No secret output.') from None
