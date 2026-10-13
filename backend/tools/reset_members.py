"""Dry run unless both the database name and destructive confirmation are explicit."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db.session import SessionLocal,active_session
from app.services.maintenance import reset_members

parser=argparse.ArgumentParser()
parser.add_argument('--branch',required=True)
parser.add_argument('--database',required=True)
parser.add_argument('--confirm',action='store_true')
args=parser.parse_args()
with SessionLocal.begin() as session:
    token=active_session.set(session)
    try:
        print(reset_members(args.branch,args.database,args.confirm))
    finally:
        active_session.reset(token)
