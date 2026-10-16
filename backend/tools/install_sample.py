"""Standard first installation: Alembic plus fictional local sample records."""
import json
import os
from pathlib import Path
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True,
                          check=True, timeout=20).stdout


def guard_target(url):
    from app.core.config import settings
    if (not settings.local_sample_data or settings.environment != 'development'
            or os.environ.get('FITGATE_ISOLATED_DEMO_TEST')
            or url.get_backend_name() != 'postgresql' or url.query
            or url.username != 'fitgate' or url.host != '127.0.0.1'
            or url.port != 5433 or url.database != 'fitgate_local'):
        raise RuntimeError('Only a fresh local FitGate sample installation is allowed')
    endpoint = docker('context', 'inspect', '--format', '{{.Endpoints.docker.Host}}').strip()
    if not endpoint.startswith('npipe://') or (os.environ.get('DOCKER_HOST') and os.environ['DOCKER_HOST'] != endpoint):
        raise RuntimeError('Only the local Windows Docker Desktop context is allowed')
    info = json.loads(docker('inspect', 'fitgate-postgres'))[0]
    mounts = info.get('Mounts', [])
    if (info['Name'] != '/fitgate-postgres' or not info['State']['Running']
            or info['HostConfig'].get('NetworkMode') == 'host'
            or info['NetworkSettings']['Ports'].get('5432/tcp') !=
                [{'HostIp': '127.0.0.1', 'HostPort': '5433'}]
            or len(mounts) != 1 or mounts[0].get('Name') != 'fitgate-postgres-data'
            or mounts[0]['Type'] != 'volume' or mounts[0]['Destination'] != '/var/lib/postgresql/data'
            or 'POSTGRES_DB=fitgate_local' not in info['Config']['Env']):
        raise RuntimeError('Local PostgreSQL container identity or storage refused')


def preflight(connection):
    from sqlalchemy import text
    identity = connection.execute(text("SELECT current_database(), current_user, current_setting('server_version_num')::int, (SELECT system_identifier::text FROM pg_control_system())")).one()
    container_id = docker('exec', 'fitgate-postgres', 'psql', '-X', '-U', 'fitgate', '-d',
                          'fitgate_local', '-At', '-c', 'SELECT system_identifier FROM pg_control_system()').strip()
    if tuple(identity[:2]) != ('fitgate_local', 'fitgate') or not 170000 <= identity[2] < 180000 or identity[3] != container_id:
        raise RuntimeError('SQL identity/version does not match the new local container')
    if connection.scalar(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')")):
        raise RuntimeError('Existing database objects found; migration and seed refused')


def main():
    if sys.argv[1:]:
        raise RuntimeError('The standard installation has no mode selection')
    from app.db.session import engine
    guard_target(engine.url)
    with engine.connect() as connection:
        preflight(connection)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, check=True)
    from tools.install_demo import demo_accounts, populate
    if not populate(demo_accounts()):
        raise RuntimeError('Unexpected existing sample installation')
    print('FitGate ready: 20 members, 5 employees and 6 local sample accounts. Use FitGate-Baslat.bat.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('FitGate installation refused or failed. Preserve existing configuration and data; no reset was performed.') from None
