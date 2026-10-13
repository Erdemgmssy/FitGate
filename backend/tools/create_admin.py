"""Provision an administrator interactively; never ship a default password."""
import getpass
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Branch, User
from app.core.security import hash_password

email = input('Admin email: ').strip().lower()
name = input('Full name: ').strip()
password = getpass.getpass('Password (at least 12 characters): ')
confirm = getpass.getpass('Confirm password: ')
if '@' not in email or not name or len(password) < 12 or password != confirm:
    raise SystemExit('Invalid email/name/password or confirmation mismatch')
with SessionLocal.begin() as session:
    if session.scalar(select(User).where(User.email == email)):
        raise SystemExit('This email already exists; nothing changed')
    branch = session.scalar(select(Branch).order_by(Branch.id))
    if branch is None:
        branch = Branch(name=input('Branch name: ').strip() or 'Merkez')
        session.add(branch)
        session.flush()
    elif session.query(Branch).count() > 1:
        raise SystemExit('Multiple branches exist; explicitly choose a branch before provisioning')
    session.add(User(username=email,email=email,full_name=name,password=hash_password(password),role='admin',branch=branch,is_staff=True))
print('Administrator created; no password was written to a file')
