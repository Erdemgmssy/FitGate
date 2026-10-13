import unittest
from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app import models as m
from app.db.base import Base
from app.db.session import engine, SessionLocal, active_session, get_session
from app.core import time as timezone
from app.core.security import hash_password, digest, random_token, access_token
from app.repositories.query import Query


def create_user(query, password=None, **values):
    return query.create(password=hash_password(password) if password else '!', **values)


class Client:
    def __init__(self, **options):
        self.client = TestClient(app)
        self.csrf = self.client.get('/api/v1/auth/csrf/').json()['csrfToken']
    def force_login(self, user):
        refresh = random_token()
        session = m.AuthSession.objects.create(user=user, refresh_hash=digest(refresh), expires_at=timezone.now()+timedelta(hours=8))
        self.client.cookies.set('fitgate_access', access_token(user, session))
        self.client.cookies.set('fitgate_refresh', refresh, path='/api/v1/auth/')
    def get(self, path):
        return self.client.get(path)
    def post(self, path, data=None, content_type=None, **options):
        headers = {key[5:].replace('_','-'):value for key,value in options.items() if key.startswith('HTTP_')}
        if 'X-CSRFToken' not in headers and self.client.cookies.get('fitgate_access'):
            headers['X-CSRFToken'] = self.csrf
        return self.client.post(path, json=data or {}, headers=headers)


class TestCase(unittest.TestCase):
    def run(self, result=None):
        if engine.url.database != 'fitgate_fastapi_test':
            raise RuntimeError('Refusing to run tests against a non-test database')
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            names = ','.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)
            connection.execute(text('TRUNCATE '+names+' RESTART IDENTITY CASCADE'))
        with SessionLocal() as session:
            token = active_session.set(session)
            try:
                with patch('app.main.SessionLocal', side_effect=lambda: nullcontext(session)), patch.object(Query, 'create_user', create_user, create=True):
                    self.client = Client()
                    return super().run(result)
            finally:
                session.rollback()
                active_session.reset(token)
