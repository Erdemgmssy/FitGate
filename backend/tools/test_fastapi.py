"""Run regression tests on an isolated PostgreSQL database, never the live database."""
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = make_url(settings.database_url)
test_name = 'fitgate_fastapi_test'
if url.database == test_name:
    raise RuntimeError('Use the live configuration as the runner input')
admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
with admin.connect() as connection:
    if not connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': test_name}):
        connection.execute(text('CREATE DATABASE fitgate_fastapi_test'))
env = dict(os.environ, DATABASE_URL=url.set(database=test_name).render_as_string(hide_password=False), ALLOW_DEVICE_SIMULATION='true')
test_engine = create_engine(url.set(database=test_name))
import app.models
from app.db.base import Base
Base.metadata.drop_all(test_engine)
with test_engine.begin() as connection:
    connection.execute(text('DROP TABLE IF EXISTS alembic_version'))
subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=env, check=True)
result = subprocess.run([sys.executable, '-m', 'pytest', 'tests_fastapi', '-q', *sys.argv[1:]], env=env)
raise SystemExit(result.returncode)
