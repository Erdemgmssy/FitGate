"""Destructive regression fixtures only on the explicitly isolated test container."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
TEST_DATABASE = 'fitgate_fastapi_test'


def checked_test_url(source):
    from tools.demo_test import guard_target
    guard_target(source)
    if source.database != 'fitgate_demo' or source.query:
        raise RuntimeError('Only the isolated demo server may host regression fixtures')
    return source.set(database=TEST_DATABASE)


def verify_identity(connection, expected_database, expected_system):
    from sqlalchemy import text
    row = connection.execute(text("SELECT current_database(), current_user, current_setting('server_version_num')::int, (SELECT system_identifier::text FROM pg_control_system())")).one()
    if tuple(row[:2]) != (expected_database, 'fitgate') or row[2] != 170011 or row[3] != expected_system:
        raise RuntimeError('SQL identity mismatch; regression reset refused')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--isolated-demo-container', action='store_true', required=True,
                        help='Reset only fitgate_fastapi_test on fitgate-demo-test at 127.0.0.1:5434')
    args, pytest_args = parser.parse_known_args()
    from app.core.config import settings
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from tools.demo_test import docker
    source = make_url(settings.database_url)
    target = checked_test_url(source)
    system = docker('exec', 'fitgate-demo-test', 'psql', '-X', '-U', 'fitgate', '-d',
                    'fitgate_demo', '-At', '-c', 'SELECT system_identifier FROM pg_control_system()').strip()
    admin = create_engine(source.set(database='postgres'), isolation_level='AUTOCOMMIT', connect_args={'connect_timeout': 5})
    try:
        with admin.connect() as connection:
            verify_identity(connection, 'postgres', system)
            if not connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': TEST_DATABASE}):
                connection.execute(text('CREATE DATABASE fitgate_fastapi_test'))
    finally:
        admin.dispose()
    print('RESET TARGET: fitgate-demo-test / 127.0.0.1:5434 / fitgate_fastapi_test', flush=True)
    print('Only regression tables in that database are dropped/truncated. fitgate_demo is preserved.', flush=True)
    test_engine = create_engine(target, connect_args={'connect_timeout': 5})
    try:
        with test_engine.begin() as connection:
            verify_identity(connection, TEST_DATABASE, system)
            from app import models
            from app.db.base import Base
            Base.metadata.drop_all(connection)
            connection.execute(text('DROP TABLE IF EXISTS alembic_version'))
    finally:
        test_engine.dispose()
    env = dict(os.environ, DATABASE_URL=target.render_as_string(hide_password=False),
               LOCAL_SAMPLE_DATA='false', DEMO_MODE='true', ALLOW_DEVICE_SIMULATION='true')
    env.pop('FITGATE_ISOLATED_DEMO_TEST', None)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, env=env, check=True)
    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests_fastapi', '-q', *pytest_args], cwd=BACKEND, env=env)
    return result.returncode
