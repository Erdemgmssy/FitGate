"""Explicitly isolated demo test. Never create, reset or delete Docker resources."""
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True,
                          text=True, timeout=20).stdout


def guard_target(url):
    from app.core.config import settings
    if (os.environ.get('FITGATE_ISOLATED_DEMO_TEST') != '1'
            or not settings.demo_mode or settings.environment != 'development'
            or url.get_backend_name() != 'postgresql' or url.username != 'fitgate'
            or url.query or url.host != '127.0.0.1' or url.port != 5434 or url.database != 'fitgate_demo'):
        raise RuntimeError('Isolated demo target refused')
    endpoint = docker('context', 'inspect', '--format', '{{.Endpoints.docker.Host}}').strip()
    if not endpoint.startswith('npipe://') or (os.environ.get('DOCKER_HOST') and
            os.environ['DOCKER_HOST'] != endpoint) or os.environ.get('DOCKER_CONTEXT'):
        raise RuntimeError('Only the local Windows Docker context is allowed')
    info = json.loads(docker('inspect', 'fitgate-demo-test'))[0]
    if (info['Name'] != '/fitgate-demo-test' or not info['State']['Running']
            or info.get('HostConfig', {}).get('NetworkMode') == 'host'
            or info['NetworkSettings']['Ports'].get('5432/tcp') !=
                [{'HostIp': '127.0.0.1', 'HostPort': '5434'}]
            or not info.get('Mounts')
            or any(m.get('Name') != 'fitgate-demo-test-data' or m['Type'] != 'volume'
                   for m in info['Mounts'])):
        raise RuntimeError('Container identity, binding or isolated volume refused')


def preflight(connection):
    from sqlalchemy import text
    identity = connection.execute(text("SELECT current_database(), current_user, current_setting('server_version_num')::int, (SELECT system_identifier::text FROM pg_control_system())")).one()
    container_identity = docker('exec', 'fitgate-demo-test', 'psql', '-X', '-U', 'fitgate',
        '-d', 'fitgate_demo', '-At', '-c', 'SELECT system_identifier FROM pg_control_system()').strip()
    if tuple(identity[:2]) != ('fitgate_demo', 'fitgate') or identity[2] != 170011 or identity[3] != container_identity:
        raise RuntimeError('SQL server identity/version mismatch')
    count = connection.scalar(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')"))
    if count:
        raise RuntimeError('Expected an empty database; migration and seed refused')


def verify():
    from sqlalchemy import select, text
    from app import models as m
    from app.db.session import engine, SessionLocal, active_session
    from app.db.base import Base
    from app.core.security import check_password
    from app.services.business import cash_balance
    from app.core import time as tz
    from tools.install_demo import populate, demo_accounts
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    guard_target(engine.url)
    with SessionLocal() as session:
        token = active_session.set(session)
        try:
            session.execute(text('SET TRANSACTION READ ONLY'))
            counts = {model.__name__: session.scalar(select(text('count(*)')).select_from(model))
                      for model in [m.Member, m.Employee, m.User, m.Plan, m.Subscription, m.Invoice,
                                    m.Payment, m.Product, m.StockMovement, m.Sale, m.ClassSession, m.Booking]}
            assert (counts['Member'], counts['Employee'], counts['User'], counts['Plan']) == (20, 5, 6, 5)
            assert session.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config(str(BACKEND/'alembic.ini'))).get_current_head()
            hashes = {u.id: u.password for u in session.scalars(select(m.User))}
            for account in demo_accounts():
                user = m.User.objects.get(email=account['email'])
                assert check_password(account['password'], user.password) and user.role == account['role']
            for employee in m.Employee.objects.all():
                assert employee.user and employee.user.role in ('staff', 'trainer')
            for sub in m.Subscription.objects.all():
                assert sub.member and sub.plan and sub.member.branch_id == sub.plan.branch_id == sub.branch_id
            for invoice in m.Invoice.objects.all():
                assert sum(i.amount_cents for i in m.Installment.objects.filter(invoice=invoice, archived=False)) == invoice.total_cents
                assert sum(p.amount_cents for p in m.Payment.objects.filter(invoice=invoice)) <= invoice.total_cents
            for product in m.Product.objects.all():
                assert product.stock == sum(s.quantity for s in m.StockMovement.objects.filter(product=product))
            for cls in m.ClassSession.objects.all():
                assert m.Booking.objects.filter(class_session=cls, status='booked').count() <= cls.capacity
            branch = m.Branch.objects.get()
            cash = m.CashSession.objects.get()
            expected = sum(p.amount_cents for p in m.Payment.objects.all() if p.method == 'cash') + sum(s.total_cents for s in m.Sale.objects.all() if s.method == 'cash')
            assert cash_balance(branch, cash, tz.now()) == expected
            assert m.Device.objects.count() == 0 and m.Shift.objects.filter(simulated=True).count() == 5
            for table in Base.metadata.tables.values():
                for fk in table.foreign_keys:
                    source = table.c[fk.parent.name]
                    target = fk.column
                    assert not session.scalar(select(text('count(*)')).select_from(table.outerjoin(target.table, source == target)).where(source.is_not(None), target.is_(None)))
            before = {table.name: sorted(session.execute(select(table)).all(), key=repr) for table in Base.metadata.tables.values()}
        finally:
            active_session.reset(token)
    assert populate(demo_accounts()) is False
    with SessionLocal() as session:
        assert hashes == {u.id: u.password for u in session.scalars(select(m.User))}
        assert before == {table.name: sorted(session.execute(select(table)).all(), key=repr) for table in Base.metadata.tables.values()}
    print(json.dumps({'counts': counts, 'cashCents': expected, 'checks': ['migration_head', 'passwords_roles', 'packages', 'installments_payments', 'stock', 'cash', 'all_foreign_keys', 'booking_capacity', 'simulated_shifts', 'repeat_seed_no_changes']}, indent=2))


def main():
    if sys.argv[1:] == ['--verify']:
        verify()
        return
    if sys.argv[1:]:
        raise RuntimeError('Unknown arguments')
    from app.db.session import engine
    guard_target(engine.url)
    with engine.connect() as connection:
        preflight(connection)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, check=True)
    from tools.install_demo import populate, demo_accounts
    if not populate(demo_accounts()):
        raise RuntimeError('Unexpected existing demo')
    print('Isolated demo migration and seed completed.')


if __name__ == '__main__':
    main()
