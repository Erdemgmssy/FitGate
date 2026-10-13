"""Explicit isolated PostgreSQL fixture for the existing personnel Playwright test."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from app.core.config import settings

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reset',action='store_true',required=True);parser.add_argument('--panel-fixture',action='store_true');args=parser.parse_args()
    url=make_url(settings.database_url);name='fitgate_personnel_ui_test'
    if url.database==name:raise RuntimeError('Run with the normal configuration; only the isolated database will be reset.')
    admin=create_engine(url.set(database='postgres'),isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        if not connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':name}):connection.execute(text('CREATE DATABASE fitgate_personnel_ui_test'))
    settings.database_url=url.set(database=name).render_as_string(hide_password=False)
    settings.allow_device_simulation=True
    from app import models as m
    from app.db.base import Base
    from app.db.session import engine,SessionLocal,active_session
    from app.core.security import hash_password
    assert engine.url.database==name
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with SessionLocal() as session:
        token=active_session.set(session)
        try:
            branch=m.Branch.objects.create(name='Isolated personnel QA')
            owner=m.User.objects.create(branch=branch,username='admin@test.com',email='admin@test.com',full_name='QA Admin',role='admin',password=hash_password('LongTest123!'))
            if args.panel_fixture:
                from datetime import timedelta
                import uuid
                from app.core import time as tz
                from app.services.business import execute
                worker=m.User.objects.create(branch=branch,username='staff@test.com',email='staff@test.com',full_name='QA Staff',role='staff',password=hash_password('LongTest123!'))
                m.Employee.objects.create(branch=branch,user=worker,name='QA Staff',role='staff')
                plan=m.Plan.objects.create(branch=branch,name='Monthly QA',price=100,weekdays=list(range(7)),allowed_from='00:00',allowed_to='23:59')
                execute('addMember',{'name':'Panel Existing','phone':'05321112233','consent':True,'planId':str(plan.id),'start':tz.localdate().isoformat(),'paid':'30','method':'cash'},owner,uuid.uuid4())
                m.Product.objects.create(branch=branch,name='Water QA',code='P-W',barcode='869000000001',price=10,cost=5,stock=10)
                m.ClassSession.objects.create(branch=branch,name='Yoga QA',at=tz.now()+timedelta(hours=2),capacity=5,duration=60)
                m.Device.objects.create(branch=branch,code='P-REAL',name='Real QA',purpose='mixed',last_seen=None,sensor='unknown')
            session.commit()
        finally:active_session.reset(token)
    print('Personnel UI fixture ready; only fitgate_personnel_ui_test, port 8002.',flush=True)
    import uvicorn
    from app.main import app
    uvicorn.run(app,host='127.0.0.1',port=8002,log_level='warning')

if __name__=='__main__':main()
