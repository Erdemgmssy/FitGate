"""SQLAlchemy query repository preserving the existing service vocabulary, not a Django runtime."""
from dataclasses import dataclass
from datetime import date
from sqlalchemy import select, func, and_, or_, not_, inspect, Uuid
from sqlalchemy.exc import NoResultFound
from app.db.session import get_session
import uuid

@dataclass
class Sum:
    field: str

class Q:
    def __init__(self, **values): self.values=values; self.children=[]; self.op='and'; self.negated=False
    def combine(self, other, op):
        result=Q(); result.children=[self,other]; result.op=op; return result
    def __and__(self,other): return self.combine(other,'and')
    def __or__(self,other): return self.combine(other,'or')
    def __invert__(self):
        result=Q(); result.children=[self]; result.negated=True; return result
    def sql(self, model):
        expressions=[condition(model,k,v) for k,v in self.values.items()]+[q.sql(model) for q in self.children]
        expression=(or_ if self.op=='or' else and_)(*expressions)
        return not_(expression) if self.negated else expression

LOOKUPS={'in','isnull','gt','gte','lt','lte','icontains','exact','date'}

def normalize(column,value):
    if hasattr(value,'pk'): value=value.pk
    if value is not None and isinstance(column.type,Uuid) and not isinstance(value,uuid.UUID): value=uuid.UUID(str(value))
    return value

def condition(model,key,value):
    parts=key.split('__'); operator=parts.pop() if parts[-1] in LOOKUPS else 'exact'
    name=parts.pop(0)
    if name=='pk': name=inspect(model).primary_key[0].key
    relation=inspect(model).relationships.get(name)
    if relation and parts:
        expression=condition(relation.mapper.class_, '__'.join(parts+([operator] if operator!='exact' else [])),value)
        return getattr(model,name).any(expression) if relation.uselist else getattr(model,name).has(expression)
    column=getattr(model,name+'_id' if relation else name)
    if operator=='date':
        value=date.fromisoformat(value) if isinstance(value,str) else value
        expression=func.timezone('Europe/Istanbul',column) if get_session().bind.dialect.name=='postgresql' else func.datetime(column,'+3 hours')
        return func.date(expression)==value
    if operator=='isnull': return column.is_(None) if value else column.is_not(None)
    if operator=='in':
        if isinstance(value,Query):
            return column.in_(select(inspect(value.model).primary_key[0]).where(*value.criteria))
        return column.in_([normalize(column,item) for item in value])
    value=normalize(column,value)
    if operator=='icontains': return column.ilike('%'+str(value).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',escape='\\')
    return {'exact':lambda:column==value,'gt':lambda:column>value,'gte':lambda:column>=value,'lt':lambda:column<value,'lte':lambda:column<=value}[operator]()

class Query:
    def __init__(self,model,criteria=(),order=(),lock=False): self.model=model; self.criteria=criteria; self.order=order; self.lock=lock
    def filter(self,*conditions,**values):
        return Query(self.model,self.criteria+tuple(q.sql(self.model) for q in conditions)+tuple(condition(self.model,k,v) for k,v in values.items()),self.order,self.lock)
    def exclude(self,**values): return Query(self.model,self.criteria+(not_(and_(*(condition(self.model,k,v) for k,v in values.items()))),),self.order,self.lock)
    def order_by(self,*fields):
        order=[]
        for field in fields:
            name=field.lstrip('-'); name=inspect(self.model).primary_key[0].key if name=='pk' else name
            column=getattr(self.model,name); order.append(column.desc() if field.startswith('-') else column.asc())
        return Query(self.model,self.criteria,tuple(order),self.lock)
    def select_related(self,*fields): return self
    def select_for_update(self): return Query(self.model,self.criteria,self.order,True)
    def statement(self):
        stmt=select(self.model).where(*self.criteria).order_by(*self.order)
        return stmt.with_for_update() if self.lock else stmt
    def __iter__(self): return iter(get_session().scalars(self.statement()).all())
    def __getitem__(self,key):
        if isinstance(key,slice):
            if key.step: return list(self)[key]
            start=key.start or 0
            return get_session().scalars(self.statement().offset(start).limit(key.stop-start if key.stop is not None else None)).all()
        return get_session().scalars(self.statement().offset(key).limit(1)).one()
    def count(self): return get_session().scalar(select(func.count()).select_from(self.model).where(*self.criteria))
    def exists(self): return get_session().scalar(select(self.statement().order_by(None).exists()))
    def first(self): return get_session().scalars(self.statement().limit(1)).first()
    def get(self,**values): return get_session().scalars(self.filter(**values).statement()).one()
    def all(self): return self
    def create(self,**values):
        record=self.model(**values); record.save(); return record
    def get_or_create(self,defaults=None,**values):
        record=self.filter(**values).first()
        return (record,False) if record else (self.create(**(defaults or {}),**values),True)
    def update(self,**values):
        records=list(self)
        for record in records:
            for key,value in values.items(): setattr(record,key,value)
        get_session().flush(); return len(records)
    def delete(self):
        records=list(self)
        for record in records: get_session().delete(record)
        get_session().flush(); return len(records)
    def aggregate(self,**values): return {key:get_session().scalar(select(func.sum(getattr(self.model,value.field))).where(*self.criteria)) for key,value in values.items()}
    def values(self,*fields):
        fields=fields or tuple(c.key for c in self.model.__table__.columns)
        return [{field:getattr(row,field) for field in fields} for row in self]
    def values_list(self,*fields,flat=False):
        return [getattr(row,fields[0]) if flat else tuple(getattr(row,field) for field in fields) for row in self]

class Manager:
    def __get__(self, instance, owner): return Query(owner)
