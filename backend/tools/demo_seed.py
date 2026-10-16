"""Explicit local demo reset; never invoked by application startup.

Real card identifiers and generated credentials belong only in ignored work/demo-reset.
Windows DPAPI encrypts the recovery archive for the current Windows account.
"""
import argparse
import ctypes
import json
import os
import re
import secrets
import subprocess
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from app import models as m
from app.core import time as tz
from app.core.config import settings
from app.core.security import check_password, hash_password
from app.db.base import Base
from app.db.session import SessionLocal, active_session, engine
from app.services.business import cash_balance, debt, execute
from app.services.membership import status

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'work' / 'demo-reset'
TEST_DB = 'fitgate_demo_seed_test'
SEED_VERSION = 'fitgate-local-demo-v1'


def command(*args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError('Yerel komut başarısız: ' + args[0] + ' (gizli çıktı gösterilmedi).')
    return result.stdout


def secure_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        raise RuntimeError('Şifreli yerel sıfırlama yalnızca Windows DPAPI ile destekleniyor.')
    identity = command('whoami').decode().strip()
    command('icacls', str(path), '/inheritance:r', '/grant:r',
            identity + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F')


def dpapi(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    destination = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), 'FitGate temporary recovery', None, None, None, 1, ctypes.byref(destination))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(destination.data, destination.size)
    finally:
        kernel.LocalFree(destination.data)


def local_config(path):
    path = path.resolve()
    if path.parent != LOCAL.resolve():
        raise RuntimeError('Seed yapılandırması yalnızca korumalı work/demo-reset içinde olabilir.')
    if subprocess.run(['git', 'check-ignore', '--quiet', str(path)], cwd=ROOT).returncode != 0:
        raise RuntimeError('Yerel yapılandırma Git tarafından yok sayılmıyor.')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    uids = value['memberUids'] + value['employeeUids']
    if len(value['memberUids']) != 4 or len(value['employeeUids']) != 3 or len(set(uids)) != 7:
        raise RuntimeError('Tam olarak yedi benzersiz kart gerekli.')
    if not all(isinstance(uid, str) and re.fullmatch(r'[0-9A-F]{8}', uid) for uid in uids):
        raise RuntimeError('Kart yapılandırması geçersiz.')
    if value.get('serialPort') != 'COM6':
        raise RuntimeError('Yerel cihaz portu doğrulanamadı.')
    return value


def guard(url, config, test=False):
    if settings.environment != 'development':
        raise RuntimeError('Uretim ortaminda demo sifirlama yasak.')
    target = config['target']
    if target != {'host': '127.0.0.1', 'port': 5433, 'database': 'fitgate'}:
        raise RuntimeError('Hedef yalnızca yerel FitGate olabilir.')
    expected = TEST_DB if test else 'fitgate'
    if url.host not in ['127.0.0.1', 'localhost'] or url.port != 5433 or url.database != expected or url.username != 'fitgate':
        raise RuntimeError('Yanlış sunucu/veritabanı: işlem durduruldu.')
    info = json.loads(command('docker', 'inspect', 'fitgate-postgres'))[0]
    bindings = info['NetworkSettings']['Ports'].get('5432/tcp', [])
    if not info['State']['Running'] or not any(p['HostIp'] == '127.0.0.1' and p['HostPort'] == '5433' for p in bindings):
        raise RuntimeError('Yerel PostgreSQL konteyneri/portu doğrulanamadı.')


def schema_inventory(connection):
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    if set(tables) != set(Base.metadata.tables) | {'alembic_version'}:
        raise RuntimeError('Bilinmeyen/eksik tablolar var; otomatik sıfırlama durduruldu.')
    q = connection.dialect.identifier_preparer.quote
    def indexes(name):
        rows = inspector.get_indexes(name)
        for row in rows:
            if name == 'gym_booking' and row['name'] == 'one_active_class_booking':
                # pg_restore can deparse the equivalent varchar[] -> text[] cast differently.
                predicate = row['dialect_options']['postgresql_where']
                states = ['booked', 'waiting', 'attended', 'late', 'absent', 'cancelled', 'excused', '', 'unknown', None]
                values = [connection.scalar(text('SELECT (' + predicate + ') FROM (SELECT CAST(:status AS varchar) AS status) AS gym_booking'),
                                           {'status': state}) for state in states]
                if values != [True, True, True, True, True, False, False, False, False, None]:
                    raise RuntimeError('Rezervasyon indeks kurali beklenen semantikle uyusmuyor.')
                row['dialect_options']['postgresql_where'] = {'statusTruthTable': values}
        return rows
    return {'migration': connection.scalar(text('SELECT version_num FROM alembic_version')),
            'tables': {name: {'rows': connection.scalar(text('SELECT count(*) FROM ' + q(name))),
                             'columns': [{'name': c['name'], 'type': str(c['type']), 'nullable': c['nullable'], 'default': c['default']}
                                         for c in inspector.get_columns(name)],
                             'primaryKey': inspector.get_pk_constraint(name),
                             'uniqueConstraints': inspector.get_unique_constraints(name),
                             'checkConstraints': inspector.get_check_constraints(name),
                             'foreignKeys': inspector.get_foreign_keys(name),
                             'indexes': indexes(name)} for name in tables}}


def recovery_backup(inventory):
    secure_directory(LOCAL)
    payload = command('docker', 'exec', 'fitgate-postgres', 'pg_dump', '-U', 'fitgate', '-d', 'fitgate', '-Fc')
    encrypted = dpapi(payload)
    if dpapi(encrypted, decrypt=True) != payload:
        raise RuntimeError('Yedek şifreleme doğrulaması başarısız.')
    archive = LOCAL / ('before-demo-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.dump.dpapi')
    with archive.open('xb') as handle:
        handle.write(encrypted)
    restored = dpapi(archive.read_bytes(), decrypt=True)
    command('docker', 'exec', '-i', 'fitgate-postgres', 'pg_restore', '--list', data=restored)
    # Restore only to an unguessable, freshly created scratch database, then remove it.
    verify = 'fitgate_demo_backup_verify_' + uuid.uuid4().hex
    command('docker', 'exec', 'fitgate-postgres', 'createdb', '-U', 'fitgate', verify)
    try:
        command('docker', 'exec', '-i', 'fitgate-postgres', 'pg_restore', '-U', 'fitgate', '-d', verify,
                '--exit-on-error', '--no-owner', data=restored)
        temporary = create_engine(make_url(settings.database_url).set(database=verify))
        try:
            with temporary.connect() as connection:
                check = schema_inventory(connection)
            if check != inventory:
                raise RuntimeError('Ayrı ortam yedek geri yüklemesi uyuşmuyor.')
        finally:
            temporary.dispose()
    finally:
        command('docker', 'exec', 'fitgate-postgres', 'dropdb', '-U', 'fitgate', verify)
    return str(archive)


def personal_file_inventory(connection):
    values = set()
    for model, fields in [(m.User, ['email', 'full_name']), (m.Member, ['name', 'email', 'phone', 'normalized_phone']),
                          (m.Employee, ['name', 'email', 'phone']), (m.Card, ['uid']), (m.EmployeeCard, ['uid'])]:
        for row in connection.execute(select(*[getattr(model, field) for field in fields])):
            values.update(str(value) for value in row if value and len(str(value)) >= 8)
    paths = []
    excluded = {'.git', 'node_modules', '__pycache__', '.pytest_cache', 'tools', 'dist', '.venv', '.venv-fastapi'}
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in excluded and not d.startswith('.venv')]
        for name in files:
            path = Path(folder) / name
            if LOCAL in path.parents: continue
            relative = path.relative_to(ROOT).as_posix()
            categories = []
            if path.suffix in ['.dump', '.bak', '.db', '.sqlite3'] or 'backups' in path.parts:
                categories.append('old-data-backup-or-database')
            if path.suffix in ['.png', '.jpg', '.xlsx', '.csv', '.log'] and ('outputs' in path.parts or 'work' in path.parts):
                categories.append('possible-old-personal-export-screenshot-or-log')
            if path.suffix in ['.json', '.py', '.mjs', '.cjs', '.jsx', '.md', '.txt', '.log', '.env'] and path.stat().st_size < 5_000_000:
                content = path.read_text(encoding='utf-8', errors='ignore')
                if any(value in content for value in values): categories.append('old-field-value-match-review-required')
            if categories:
                tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', '--', relative], cwd=ROOT, capture_output=True).returncode == 0
                paths.append({'path': relative, 'bytes': path.stat().st_size, 'categories': categories, 'tracked': tracked})
    (LOCAL/'Eski-Veri-Dosyalari.json').write_text(json.dumps(paths, indent=2, ensure_ascii=False), encoding='utf-8')
    return paths


def credentials():
    names = [('admin', 'Demo Yonetici', 'admin'), ('reception', 'Demo Resepsiyon', 'staff'),
             ('trainer', 'Demo Antrenor', 'trainer'), ('floor', 'Demo Salon Personeli', 'staff')]
    return [{'key': key, 'name': name, 'role': role, 'email': key + '.demo@example.com',
             'password': 'Fg9!' + secrets.token_urlsafe(24)} for key, name, role in names]


def seed(config, accounts, device_key, device_code, *, portable=False):
    from tools.install_demo import DEMO_PASSWORD, guard as demo_guard
    if portable:
        demo_guard(engine.url)
    if any(account['password'] == DEMO_PASSWORD for account in accounts):
        if not portable:
            raise RuntimeError('Public demo credentials require the portable demo installer')
    branch = m.Branch.objects.create(name='FitGate Kurgusal Demo', capacity=100, debt_block=False)
    admin_data = accounts[0]
    admin = m.User.objects.create(branch=branch, username=admin_data['email'], email=admin_data['email'],
                                  full_name=admin_data['name'], role='admin', password=hash_password(admin_data['password']))
    def act(action, payload, actor=admin):
        return execute(action, payload, actor, uuid.uuid4())['result']
    act('openCash', {'amount': '0'})
    employees = []
    jobs = ['Resepsiyon', 'Antrenor', 'Salon destek', 'Satis', 'Destek']
    for index, account in enumerate(accounts[1:]):
        key = act('saveEmployee', {'name': account['name'], 'role': account['role'], 'email': account['email'],
                  'createAccount': True, 'password': account['password'], 'jobTitle': jobs[index],
                  'type': 'hourly' if index == 2 else 'fixed', 'startDate': (tz.localdate()-timedelta(days=400)).isoformat(),
                  'card': config['employeeUids'][index]})
        employees.append(m.Employee.objects.get(pk=key))
    act('saveRates', {'confirmed': True, 'rates': {str(employees[2].id): '150'}})
    act('saveRolePolicy', {'role': 'staff', 'permissions': {'manualAttendance': False, 'simulateAttendance': False}})
    act('saveRolePolicy', {'role': 'trainer', 'permissions': {'memberManagement': False, 'cardManagement': False,
        'collections': False, 'productSales': False, 'deviceRead': False, 'manualAttendance': False, 'simulateAttendance': False}})
    today = tz.localdate()
    plans = []
    definitions = [('Aylik sinirsiz', 1, None, '1500'), ('3 aylik', 3, None, '4000'),
                   ('6 aylik', 6, None, '7000'), ('10 seans', 0, 10, '2000'), ('20 seans', 0, 20, '3500')]
    for name, duration, sessions, price in definitions:
        result = act('savePlan', {'name': name, 'description': 'Tamamen kurgusal demo paketi',
                     'kind': 'sessions' if sessions else 'timed', 'durationValue': duration,
                     'durationUnit': 'month', 'sessions': sessions, 'price': price, 'from': '00:00', 'to': '23:59',
                     'weekdays': list(range(7)), 'freezeDays': 14, 'freezeMin': 1, 'freezeMax': 14,
                     'lessonTypes': ['group', 'private'], 'active': True})
        plans.append(m.Plan.objects.get(pk=result['id']))
    members = []
    for index in range(20 if portable else 24):
        # NANPA reserves 555-0100..0199 as non-working fictional numbers.
        name = f'Demo Uye {index+1:02d}'
        plan = plans[0] if index == 0 or index == 2 else plans[3] if index == 1 else plans[1] if index == 3 else plans[index % 5]
        start = today-timedelta(days=70) if index == 2 else today
        if index >= 4 and index % 7 == 0: plan = plans[0]; start = today-timedelta(days=70)
        if index >= 4 and index % 7 == 1: start = today+timedelta(days=14)
        payload = {'name': name, 'phone': f'+1202555{101+index:04d}', 'email': f'member{index+1:02d}.demo@example.com',
                   'birthDate': date(today.year-(18+index*2), 2, 10).isoformat(),
                   'consent': True, 'marketing': False, 'note': 'Kurgusal demo; gercek kisi kaydi degildir.'}
        if not (index >= 4 and index % 7 == 2):
            payload.update(planId=str(plan.id), start=start.isoformat(), installments=3 if index == 3 or index % 6 == 0 else 1)
            if index == 3: payload.update(paid='1000', method='cash')
            elif index == 2 or index % 3 == 0: payload.update(paid=str(plan.price), method='bank' if index == 2 else 'cash')
            elif index % 3 == 1: payload.update(paid='500', method='pos')
        if index < 4: payload['uid'] = config['memberUids'][index]
        key = act('addMember', payload)
        member = m.Member.objects.get(pk=key)
        members.append(member)
        sub = m.Subscription.objects.filter(member=member).first()
        if sub and (index == 3 or index >= 4 and index % 7 == 3):
            act('freeze', {'id': str(sub.id), 'start': today.isoformat(), 'end': (today+timedelta(days=6)).isoformat(), 'reason': 'Kurgusal demo dondurma'})
        if sub and index >= 4 and index % 7 == 4:
            act('cancelSubscription', {'id': str(sub.id), 'confirmed': True, 'reason': 'Kurgusal demo iptali'})
    supplier_id = act('saveSupplier', {'name': 'Demo Tedarikci', 'email': 'supplier.demo@example.com'})['id']
    products = []
    definitions = [('Su 500 ml', '20', '8', 40), ('Protein bar', '60', '30', 25),
                   ('Protein tozu', '1200', '700', 8), ('Spor havlusu', '150', '80', 15),
                   ('Enerji icecegi', '50', '25', 1), ('Spor ekipmanlari', '500', '250', 10)]
    for index, (name, price, cost, stock) in enumerate(definitions):
        key = act('saveProduct', {'name': name, 'code': f'DEMO-P{index+1:02d}', 'price': price, 'cost': cost,
                   'stock': 0, 'minimum': 3, 'supplierId': supplier_id})['id']
        act('stock', {'id': key, 'kind': 'receipt', 'quantity': stock, 'cost': cost, 'supplierId': supplier_id,
                     'receivedCode': f'DEMO-TESLIM-{index+1}', 'reason': 'Kurgusal mal kabul'})
        products.append(m.Product.objects.get(pk=key))
    for product, quantity, method in [(products[0], 2, 'cash'), (products[1], 1, 'cash'), (products[2], 1, 'pos')]:
        act('sellProduct', {'productId': str(product.id), 'quantity': quantity, 'revision': product.revision,
                           'memberId': str(members[0].id), 'method': method})
    for offset in [0, 1, 2]:
        for employee in employees:
            begin = tz.make_aware(datetime.combine(today+timedelta(days=offset), time(8)))
            act('savePlannedShift', {'employeeId': str(employee.id), 'start': begin.isoformat(),
                'end': (begin+timedelta(hours=10)).isoformat(), 'breakMinutes': 30, 'autoStart': True})
    leave_id = act('saveLeaveType', {'name': 'Demo yillik izin', 'annualDays': 14, 'weekdays': list(range(7))})
    for index, employee in enumerate(employees):
        day = today+timedelta(days=8+index)
        request = act('requestLeave', {'employeeId': str(employee.id), 'typeId': leave_id,
            'start': day.isoformat(), 'end': day.isoformat(), 'reason': 'Kurgusal izin talebi'}, employee.user)
        if index == 0: act('reviewLeave', {'id': request, 'status': 'approved', 'reason': 'Demo izin onayi'})
    for index, name in enumerate(['Pilates', 'Yoga', 'Fitness', 'Ozel antrenman']):
        at = tz.make_aware(datetime.combine(today+timedelta(days=1), time(9+index*2)))
        key = act('saveClass', {'name': name, 'trainerId': str(employees[1].id), 'room': 'Demo Salon',
            'at': at.isoformat(), 'duration': 60, 'capacity': 1 if index == 3 else 8,
            'kind': 'private' if index == 3 else 'group', 'requireMembership': True, 'requireLesson': False})['id']
        for member in members[:2] if index < 3 else members[:1]:
            act('book', {'classId': key, 'memberId': str(member.id)})
    if portable:
        for employee in employees:
            begin = tz.make_aware(datetime.combine(today-timedelta(days=1), time(8)))
            shift = m.Shift.objects.create(branch=branch, employee=employee, entry=begin,
                exit=begin+timedelta(hours=8), source='simulation', simulated=True,
                reason='Kurgusal demo mesaisi; fiziksel gecis degildir.')
            for direction, at in [('entry', begin), ('exit', shift.exit)]:
                m.AttendanceEvent.objects.create(branch_id=branch.id, employee_id=employee.id,
                    shift_id=shift.id, occurred_at=at, direction=direction, source='simulation',
                    actor=admin, approved=True, message='Kurgusal demo mesaisi')
        branch.configuration = {**branch.configuration, 'portableDemoSeed': 'v1'}
        branch.save()
        return {'members': m.Member.objects.count(), 'employees': m.Employee.objects.count()}
    m.Device.objects.create(branch=branch, code=device_code, name='Arduino UNO USB Turnike',
        model='Arduino UNO / RC522 / 2 HC-SR04', purpose='mixed', credential_context='auto',
        direction='both', mode='auto', sensor='unknown', enabled=True, simulated=False,
        token_hash=hash_password(device_key), last_seen=None, telemetry={}, telemetry_at=None)
    branch.configuration = {**branch.configuration, 'localDemoSeed': SEED_VERSION,
        'demoDevice': {'serialPort': config['serialPort'], 'expectedFirmware': config.get('expectedFirmware'),
                       'firmwareVerified': False}}
    branch.save()
    return verify(config, accounts)


def verify(config, accounts):
    from app.services.projection import snapshot
    from app.services.dashboard import summary
    branch = m.Branch.objects.get()
    if m.Member.objects.count() != 24 or m.Employee.objects.count() != 3 or m.User.objects.count() != 4:
        raise RuntimeError('Demo kayit sayilari uyusmuyor.')
    for account in accounts:
        user = m.User.objects.get(email=account['email'])
        if not check_password(account['password'], user.password): raise RuntimeError('Giris hesabi dogrulanamadi.')
        snapshot(user)
    cards = list(m.Card.objects.all())
    employee_cards = list(m.EmployeeCard.objects.all())
    if {c.uid for c in cards} != set(config['memberUids']) or {c.uid for c in employee_cards} != set(config['employeeUids']):
        raise RuntimeError('Kart eslestirmeleri uyusmuyor.')
    for index, uid in enumerate(config['memberUids']):
        if m.Card.objects.get(uid=uid).member.name != f'Demo Uye {index+1:02d}': raise RuntimeError('Uye karti yanlis.')
    for index, uid in enumerate(config['employeeUids']):
        card = m.EmployeeCard.objects.get(uid=uid)
        if card.employee.name != accounts[index+1]['name'] or card.status != 'active' or card.employee.card != uid:
            raise RuntimeError('Personel karti yanlis.')
    for cls in m.ClassSession.objects.all():
        if m.Booking.objects.filter(class_session=cls, status='booked').count() > cls.capacity: raise RuntimeError('Kontenjan asildi.')
    invoices = list(m.Invoice.objects.all())
    for invoice in invoices:
        if sum(i.amount_cents for i in m.Installment.objects.filter(invoice=invoice, archived=False)) != invoice.total_cents:
            raise RuntimeError('Taksit/satis toplamı uyusmuyor.')
        if sum(p.amount_cents for p in m.Payment.objects.filter(invoice=invoice)) > invoice.total_cents:
            raise RuntimeError('Fazla tahsilat var.')
    for product in m.Product.objects.all():
        if product.stock != sum(s.quantity for s in m.StockMovement.objects.filter(product=product)):
            raise RuntimeError('Stok hareketleri uyusmuyor.')
    for model in [m.Passage, m.Visit, m.PersonnelVisit, m.Shift, m.AttendanceEvent, m.Grant, m.Attempt]:
        if model.objects.count(): raise RuntimeError('Gercek olmayan fiziksel gecis/mesai var.')
    device = m.Device.objects.get()
    if device.last_seen or device.telemetry or device.simulated: raise RuntimeError('Sahte cihaz durumu var.')
    cash = m.CashSession.objects.get()
    payments = list(m.Payment.objects.all())
    sales = list(m.Sale.objects.all())
    expected_cash = sum(p.amount_cents for p in payments if p.method == 'cash') + sum(s.total_cents for s in sales if s.method == 'cash')
    if cash_balance(branch, cash, tz.now()) != expected_cash: raise RuntimeError('Kasa uyusmuyor.')
    owner = m.User.objects.get(role='admin')
    dashboard = summary(owner, tz.localdate())
    counts = {table: get_count(table) for table in Base.metadata.tables}
    return {'members': 24, 'employees': 3, 'users': 4, 'cards': 7, 'plans': m.Plan.objects.count(),
        'membershipStates': {state: sum(status(sub) == state for sub in m.Subscription.objects.all())
                             for state in ['active', 'expired', 'frozen', 'pending', 'cancelled']},
        'subscriptions': m.Subscription.objects.count(), 'invoices': len(invoices),
        'payments': len(payments), 'collectedCents': sum(p.amount_cents for p in payments),
        'debtCents': int(sum(debt(i) for i in invoices)), 'cashCents': expected_cash,
        'productSalesCents': sum(s.total_cents for s in sales), 'products': m.Product.objects.count(),
        'classes': m.ClassSession.objects.count(), 'bookings': m.Booking.objects.count(),
        'physicalPassages': 0, 'automaticShifts': 0, 'deviceOnline': False, 'tableCounts': counts}


def get_count(table):
    from app.db.session import get_session
    return get_session().scalar(select(text('count(*)')).select_from(Base.metadata.tables[table]))


def bridge_config():
    from dotenv import dotenv_values
    path = ROOT / 'backend' / 'hardware' / '.env'
    values = dotenv_values(path)
    if values.get('SERIAL_PORT') != 'COM6' or not values.get('DEVICE_KEY') or not values.get('DEVICE_CODE'):
        raise RuntimeError('Mevcut yerel COM6 bridge yapılandırması bulunamadı; gizli değerler değiştirilmedi.')
    return values['DEVICE_KEY'], values['DEVICE_CODE']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=LOCAL / 'config.json')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--reset-local', action='store_true')
    parser.add_argument('--confirm', default='')
    args = parser.parse_args()
    config = local_config(args.config)
    original = make_url(settings.database_url)
    guard(original, config)
    device_key, device_code = bridge_config()
    if args.test:
        command('docker', 'exec', 'fitgate-postgres', 'psql', '-U', 'fitgate', '-d', 'postgres', '-tAc',
                "SELECT 1 FROM pg_database WHERE datname='" + TEST_DB + "'")
        maintenance = create_engine(original.set(database='postgres'), isolation_level='AUTOCOMMIT')
        with maintenance.connect() as connection:
            if not connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:db'), {'db': TEST_DB}):
                connection.execute(text('CREATE DATABASE ' + TEST_DB))
        maintenance.dispose()
        env = dict(os.environ, DATABASE_URL=original.set(database=TEST_DB).render_as_string(hide_password=False))
        child = subprocess.run([sys.executable, __file__, '--config', str(args.config), '--internal-test'], env=env)
        raise SystemExit(child.returncode)
    run_local(config, args, device_key, device_code)


def run_local(config, args, device_key, device_code, test=False):
    guard(make_url(settings.database_url), config, test=test)
    secure_directory(LOCAL)
    with engine.connect() as connection:
        existing = list(connection.execute(select(m.Branch.configuration)).scalars()) if inspect(connection).has_table('gym_branch') else []
    if any(value.get('localDemoSeed') == SEED_VERSION for value in existing):
        print('Demo seed zaten uygulanmis; hicbir kayit degistirilmedi.')
        return
    if test:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(32) primary key)'))
    elif not (args.reset_local and args.confirm == 'RESET LOCAL FITGATE' and config.get('allowLocalReset') is True):
        raise RuntimeError('Yikici islem icin yerel izin ve acik onay gerekli.')
    with engine.connect() as connection:
        inventory = schema_inventory(connection)
        old_ids = {table: set(connection.execute(select(model.c.id)).scalars())
                   for table, model in Base.metadata.tables.items() if 'id' in model.c}
        if not test:
            if connection.scalar(text('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()')):
                raise RuntimeError('Diger veritabani baglantilari acik; once uygulama/bridge kapatilmali.')
            personal_file_inventory(connection)
    backup = None if test else recovery_backup(inventory)
    accounts = credentials()
    if not test:
        path = LOCAL / 'Giris-Bilgileri.json'
        with path.open('x', encoding='utf-8') as handle:
            json.dump({'warning': 'Gecici parolalar; ilk giristen sonra Ayarlar uzerinden degistirin.', 'accounts': accounts}, handle, ensure_ascii=False, indent=2)
    with SessionLocal() as session:
        token = active_session.set(session)
        try:
            session.execute(text('SET LOCAL lock_timeout = \'10s\''))
            session.execute(text('SELECT pg_advisory_xact_lock(74617431)'))
            if any(value.get('localDemoSeed') == SEED_VERSION for value in session.execute(select(m.Branch.configuration)).scalars()):
                raise RuntimeError('Eszamanli seed zaten uygulanmis; ikinci sifirlama engellendi.')
            tables = list(Base.metadata.tables)
            quoted = [engine.dialect.identifier_preparer.quote(name) for name in tables]
            session.execute(text('TRUNCATE TABLE ' + ', '.join(quoted)))
            result = seed(config, accounts, device_key, device_code)
            for table, identifiers in old_ids.items():
                if identifiers and session.scalar(select(text('count(*)')).select_from(Base.metadata.tables[table])
                                                  .where(Base.metadata.tables[table].c.id.in_(identifiers))):
                    raise RuntimeError('Eski kayit kimligi aktif veritabaninda kaldi.')
            after_schema = schema_inventory(session.connection())
            if after_schema['migration'] != inventory['migration'] or any(
                {key: value for key, value in inventory['tables'][table].items() if key != 'rows'} !=
                {key: value for key, value in after_schema['tables'][table].items() if key != 'rows'}
                for table in inventory['tables']):
                raise RuntimeError('Schema/migration yapisi degisti.')
            result['oldRecordIdsRemaining'] = 0
            result['oldRecordsRemoved'] = sum(row['rows'] for name, row in inventory['tables'].items() if name != 'alembic_version')
            result['backup'] = backup
            result['testOnly'] = test
            result['preservedMigration'] = inventory['migration']
            serialized = json.dumps(result, indent=2)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            active_session.reset(token)
    if not test:
        config['allowLocalReset'] = False
        args.config.write_text(json.dumps(config, indent=2), encoding='utf-8')
    (LOCAL / ('test-report.json' if test else 'reset-report.json')).write_text(serialized, encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in ['tableCounts', 'backup']}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        if '--internal-test' in sys.argv:
            if make_url(settings.database_url).database != TEST_DB: raise RuntimeError('Test veritabani korumasi.')
            args = argparse.Namespace(config=Path(sys.argv[sys.argv.index('--config')+1]), reset_local=False, confirm='')
            run_local(local_config(args.config), args, *bridge_config(), test=True)
        else:
            main()
    except Exception as error:
        # Database errors can include UIDs, passwords or old row contents; never echo them.
        print('Seed tamamlanamadi (' + type(error).__name__ + '). Yerel raporu kontrol edin; gizli hata icerigi yazdirilmadi.', file=sys.stderr)
        raise SystemExit(1)
