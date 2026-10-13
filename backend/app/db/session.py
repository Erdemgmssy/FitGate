from contextvars import ContextVar
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

active_session = ContextVar('fitgate_session')
options = {}
if settings.database_url.startswith('postgresql'):
    options['options'] = (f'-c lock_timeout={settings.db_lock_timeout_ms} '
                          f'-c statement_timeout={settings.db_statement_timeout_ms} '
                          f'-c idle_in_transaction_session_timeout={settings.db_idle_transaction_timeout_ms}')
engine = create_engine(settings.database_url, pool_pre_ping=True,connect_args=options)
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_session():
    return active_session.get()
