"""Provision a USB reader independently of Django; never overwrite local credentials."""
import argparse
import re
import secrets
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Branch, Device
from app.core.security import hash_password

parser = argparse.ArgumentParser()
parser.add_argument('--code', default='TRN-UNO-001')
parser.add_argument('--port', required=True)
parser.add_argument('--branch')
args = parser.parse_args()
path = Path(__file__).resolve().parents[1] / 'hardware' / '.env'
if path.exists():
    raise SystemExit('Local bridge configuration exists; nothing overwritten')
if not re.fullmatch(r'COM[1-9]\d*', args.port) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',args.code):
    raise SystemExit('Invalid port or device code')
secret = secrets.token_urlsafe(48)
with SessionLocal.begin() as session:
    branches = list(session.scalars(select(Branch).where(Branch.id == uuid.UUID(args.branch))) if args.branch else session.scalars(select(Branch)))
    if len(branches) != 1 or session.scalar(select(Device).where(Device.code == args.code)):
        raise SystemExit('Choose one existing branch and an unused device code')
    session.add(Device(branch=branches[0],code=args.code,name='Arduino UNO USB Turnike',model='UNO / RC522 / 2 HC-SR04',direction='both',sensor='unknown',simulated=False,token_hash=hash_password(secret)))
    session.flush()
    with path.open('x', encoding='ascii') as file:
        file.write(f'API_BASE_URL=http://127.0.0.1:8001\nDEVICE_CODE={args.code}\nDEVICE_KEY={secret}\nSERIAL_PORT={args.port}\n')
print('Reader registered; secret stored locally, firmware not uploaded')
