"""Queue an audited real diagnostic; never create a visit or attendance fixture."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal,active_session
from app.models import Device,User,DeviceCommand
from app.services.business import execute,RuleError

parser=argparse.ArgumentParser()
parser.add_argument('--action',choices=['lcd','indicators','servo'],required=True)
parser.add_argument('--safe-area',action='store_true')
args=parser.parse_args()
if args.action=='servo' and not args.safe_area: raise SystemExit('Servo hareket alani onayi icin --safe-area gerekli.')
with SessionLocal() as session:
    token=active_session.set(session)
    try:
        device=session.scalar(select(Device).where(Device.code=='TRN-UNO-001'))
        admin=session.scalar(select(User).where(User.branch_id==device.branch_id,User.role=='admin',User.is_active==True))
        result=execute('queueDeviceDiagnostic',{'deviceId':str(device.id),'action':args.action,'confirmed':True},admin,uuid.uuid4())['result']
        session.commit(); identifier=uuid.UUID(result['id'])
    except RuleError as error: raise SystemExit(str(error))
    finally: active_session.reset(token)
deadline=time.monotonic()+20
while time.monotonic()<deadline:
    with SessionLocal() as session:
        command=session.get(DeviceCommand,identifier)
        if command.status in ['complete','failed','expired']:
            print(json.dumps({'id':str(identifier),'action':args.action,'status':command.status,'result':command.result},ensure_ascii=True))
            raise SystemExit(0 if command.status=='complete' else 1)
    time.sleep(0.3)
raise SystemExit('Cihaz sonucu alinamadi; web panelinde gunlugu kontrol edin. Fiziksel test basarili sayilmadi.')
