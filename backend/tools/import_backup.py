"""Import an archived Django export without importing Django or changing its database."""
import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models  # noqa: F401
from app.db.base import Base, UTCDateTime
from app.db.session import engine
from sqlalchemy import Date, Numeric, Uuid, select, text, func


def convert(column, value):
    if value is None:
        return None
    if isinstance(column.type, Uuid):
        return uuid.UUID(str(value))
    if isinstance(column.type, UTCDateTime):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    if isinstance(column.type, Date):
        return date.fromisoformat(value)
    if isinstance(column.type, Numeric):
        return Decimal(str(value))
    return value


def run(path):
    records = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    groups = {}
    archived = Counter()
    for record in records:
        namespace, name = record['model'].split('.')
        table = Base.metadata.tables.get(f'gym_{name}') if namespace == 'gym' else None
        if table is None:
            archived[record['model']] += 1
            continue
        primary = list(table.primary_key.columns)[0]
        row = {primary.name: convert(primary, record['pk'])}
        for column in table.c:
            if column.primary_key:
                continue
            field = column.name[:-3] if column.foreign_keys and column.name.endswith('_id') else column.name
            personnel_defaults={'gym_branch':{'attendance_rules':{}},'gym_employee':{'email':'','photo':'','job_title':'','start_date':None,'user':None},'gym_shift':{'planned':None,'source':'legacy','simulated':False,'device':None}}
            if field not in record['fields'] and field in personnel_defaults.get(table.name,{}):
                row[column.name]=personnel_defaults[table.name][field]
                continue
            if table.name == 'gym_member' and field not in record['fields'] and column.name in ['birth_date','emergency_phone']:
                row[column.name] = None if column.name == 'birth_date' else ''
                continue
            if table.name=='gym_freeze' and field=='planned_end' and field not in record['fields']:
                row[field]=None
                continue
            if table.name=='gym_subscription' and field=='total_sessions' and field not in record['fields']:
                remaining=record['fields']['remaining']
                total=record['fields']['rules'].get('sessions')
                used=sum(item['model']=='gym.grant' and str(item['fields'].get('subscription'))==str(record['pk']) and item['fields'].get('confirmed') and item['fields'].get('direction')=='entry' for item in records)
                row[field]=None if remaining is None else max(remaining,int(total) if total is not None else remaining+used)
                continue
            if field not in record['fields']:
                raise ValueError(f'Missing field: {table.name}.{field}')
            row[column.name] = convert(column, record['fields'][field])
        groups.setdefault(table.name, []).append(row)
    report = {}
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not table.name.startswith('gym_'):
                continue
            added = 0
            primary = list(table.primary_key.columns)[0]
            for row in groups.get(table.name, []):
                existing = connection.execute(select(table).where(primary == row[primary.name])).mappings().first()
                if existing:
                    if any(existing[key] != value for key, value in row.items()):
                        raise ValueError(f'Conflicting record: {table.name}/{row[primary.name]}; nothing overwritten')
                else:
                    connection.execute(table.insert().values(**row))
                    added += 1
            count = connection.scalar(select(func.count()).select_from(table))
            expected = len(groups.get(table.name, []))
            if count != expected:
                raise ValueError(f'Count mismatch: {table.name}: {count} != {expected}')
            report[table.name] = {'source': expected, 'destination': count, 'inserted': added}
            if engine.dialect.name == 'postgresql':
                sequence = connection.scalar(text('SELECT pg_get_serial_sequence(:table, :column)'), {'table': table.name, 'column': primary.name})
                if sequence:
                    maximum = connection.scalar(select(func.max(primary)))
                    connection.execute(text('SELECT setval(:sequence, :value, :called)'), {'sequence': sequence, 'value': maximum or 1, 'called': maximum is not None})
    return {'tables': report, 'archived_framework_records': dict(archived)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('backup')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    result = run(args.backup)
    Path(args.report).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Validated {len(result["tables"])} tables; report: {args.report}')
