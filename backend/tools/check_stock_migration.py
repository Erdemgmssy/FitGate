"""Verify legacy full returns using a disposable database, never the live records."""
import os
import sys
import uuid
import subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from app.core.config import settings

url=make_url(settings.database_url)
name='fitgate_stock_migration_'+uuid.uuid4().hex[:12]
admin=create_engine(url.set(database='postgres'),isolation_level='AUTOCOMMIT')
engine=None;created=False
try:
    with admin.connect() as connection:connection.execute(text(f'CREATE DATABASE "{name}"'));created=True
    env=dict(os.environ,DATABASE_URL=url.set(database=name).render_as_string(hide_password=False))
    subprocess.run([sys.executable,'-m','alembic','upgrade','8c24e9120a31'],env=env,check=True)
    engine=create_engine(url.set(database=name))
    branch,product,sale,movement=[uuid.uuid4() for _ in range(4)]
    p={'branch':branch,'product':product,'sale':sale,'movement':movement}
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO gym_branch(id,name,capacity,debt_block,member_counter,invoice_counter,payment_counter,attendance_rules) VALUES (:branch,'Migration fixture',100,false,0,0,0,'{}')"),p)
        connection.execute(text("INSERT INTO gym_user(id,password,is_superuser,username,first_name,last_name,is_staff,is_active,date_joined,email,full_name,role,branch_id) VALUES (1,'!',false,'migration-test','','',false,true,now(),'migration@test.invalid','Fixture','admin',:branch)"),p)
        connection.execute(text("INSERT INTO gym_product(id,branch_id,name,code,barcode,category,price,cost,stock,minimum,supplier) VALUES (:product,:branch,'Water','MIG-W','MIG-123','Drink',10.01,2,9,2,'Legacy Supplier')"),p)
        connection.execute(text("INSERT INTO gym_sale(id,branch_id,product_id,product_name,quantity,total_cents,method,at,actor_id,returned,returned_at) VALUES (:sale,:branch,:product,'Water',2,2001,'cash',now()-interval '2 days',1,true,now()-interval '1 day')"),p)
        connection.execute(text("INSERT INTO gym_stockmovement(id,branch_id,product_id,quantity,reason,at) VALUES (:movement,:branch,:product,2,'Prior return already restocked',now()-interval '1 day')"),p)
    engine.dispose()
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT stock FROM gym_product WHERE id=:product'),p)==9
        row=connection.execute(text('SELECT returned_quantity,refunded_cents,total_cents,checkout_id FROM gym_sale WHERE id=:sale'),p).one()
        assert tuple(row)==(2,2001,2001,sale)
        refund=connection.execute(text("SELECT quantity,returned_units,refund_cents,actor_id FROM gym_stockmovement WHERE sale_id=:sale AND kind='legacy_return'"),p).one()
        assert tuple(refund)==(0,2,2001,None)
        assert connection.scalar(text('SELECT count(*) FROM gym_stockmovement'))==2
        assert connection.scalar(text('SELECT sum(total_cents) FROM gym_sale'))-connection.scalar(text('SELECT sum(refund_cents) FROM gym_stockmovement'))==0
        assert connection.scalar(text("SELECT name FROM gym_supplier"))=='Legacy Supplier'
        assert connection.scalar(text('SELECT supplier_id IS NOT NULL FROM gym_product')) is True
    print('PASS: legacy sale, stock, supplier and exact cash refund preserved; no double restock/refund.')
finally:
    if engine:engine.dispose()
    if created:
        with admin.connect() as connection:connection.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
