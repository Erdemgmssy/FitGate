"""Reproduce event-loop lock starvation only on a disposable PostgreSQL database."""
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import create_engine,select,text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app import models as m
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base

NAME='fitgate_stability_test'
BASE='http://127.0.0.1:8003'
ROOT=Path(__file__).resolve().parents[2]


def run(legacy=False):
    url=make_url(settings.database_url)
    if url.host not in ['localhost','127.0.0.1'] or url.port!=5433 or url.database==NAME:
        raise RuntimeError('Only the normal local configuration can launch this isolated test.')
    with socket.socket() as port: port.bind(('127.0.0.1',8003))
    admin=create_engine(url.set(database='postgres'),isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        if not connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':NAME}):
            connection.execute(text('CREATE DATABASE '+NAME))
    admin.dispose()
    engine=create_engine(url.set(database=NAME))
    assert engine.url.database==NAME
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    key=secrets.token_urlsafe(32)
    with Session(engine) as session:
        branch=m.Branch(name='Isolated stability fixture');session.add(branch);session.flush()
        device=m.Device(branch=branch,code='STABILITY-TEST',token_hash=hash_password(key),purpose='mixed')
        session.add(device);session.commit();branch_id=branch.id
    env=dict(os.environ,DATABASE_URL=url.set(database=NAME).render_as_string(hide_password=False),
             DB_LOCK_TIMEOUT_MS='3000',ALLOW_SINGLE_SENSOR_PROTOTYPE='false')
    code="from app.db.session import engine; assert engine.url.database=='fitgate_stability_test'; import app.main as mod; import uvicorn; "
    if legacy:
        code+="exec('async def direct(function,*args,**kwargs):\\n return function(*args,**kwargs)'.replace('\\\\n','\\n')); mod.run_in_threadpool=direct; "
    code+="uvicorn.run(mod.app,host='127.0.0.1',port=8003,log_level='error',access_log=False)"
    log=ROOT/'outputs'/('stability-legacy.log' if legacy else 'stability-fixed.log')
    log.parent.mkdir(exist_ok=True)
    with log.open('wb') as handle:
        server=subprocess.Popen([sys.executable,'-c',code],cwd=ROOT/'backend',env=env,stdout=handle,stderr=handle,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            with httpx.Client(base_url=BASE,timeout=8) as client,ThreadPoolExecutor(max_workers=4) as pool:
                deadline=time.monotonic()+15
                while True:
                    try:
                        if client.get('/api/v1/health/',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    if time.monotonic()>deadline:raise RuntimeError('Isolated server failed to start')
                    time.sleep(.1)
                headers={'X-Device-Code':'STABILITY-TEST','X-Device-Key':key}
                with engine.begin() as holder:
                    holder.execute(select(m.Branch.id).where(m.Branch.id==branch_id).with_for_update()).one()
                    blocked=pool.submit(client.post,'/api/v1/device/commands/poll/',json={},headers=headers)
                    time.sleep(.3)
                    started=time.monotonic();hung=False
                    try:health=client.get('/api/v1/health/',timeout=1)
                    except httpx.TimeoutException:hung=True
                    latency=time.monotonic()-started
                    if hung!=legacy:raise AssertionError('Unexpected lock/health isolation result')
                    if not hung and health.status_code!=200:raise AssertionError('Health unavailable')
                if blocked.result(timeout=5).status_code!=200:raise AssertionError('Released lock request failed')
                result={'mode':'legacy-reproduction' if legacy else 'fixed','healthHungBehindLock':hung,
                        'healthMilliseconds':round(latency*1000)}
                if not legacy:
                    with engine.begin() as holder:
                        holder.execute(select(m.Branch.id).where(m.Branch.id==branch_id).with_for_update()).one()
                        blocked=pool.submit(client.post,'/api/v1/device/commands/poll/',json={},headers=headers)
                        response=blocked.result(timeout=6)
                        if response.status_code!=503:raise AssertionError('Database lock timeout not bounded')
                        if client.get('/api/v1/health/').status_code!=200:raise AssertionError('Lock timeout stalled event loop')
                    result['boundedLockResponse']=503
                    def request(index):
                        start=time.monotonic()
                        if index%3==0:r=client.get('/api/v1/health/')
                        elif index%3==1:r=client.post('/api/v1/device/commands/poll/',json={},headers=headers)
                        else:r=client.post('/api/v1/device/heartbeat/',json={'connected':False,'sensor':'unknown'},headers=headers)
                        if r.status_code!=200:raise AssertionError('Concurrent request failed')
                        return round((time.monotonic()-start)*1000)
                    times=list(pool.map(request,range(60)))
                    with engine.connect() as connection:
                        idle=connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name AND state='idle in transaction'"),{'name':NAME})
                    if idle:raise AssertionError('Leaked transaction')
                    result.update(concurrentRequests=60,maxRequestMilliseconds=max(times),idleTransactions=idle)
                print(json.dumps(result));return result
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
            engine.dispose()


if __name__=='__main__':
    run('--reproduce-old' in sys.argv)
