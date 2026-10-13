from datetime import timezone
from sqlalchemy import DateTime, inspect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator
from sqlalchemy.exc import NoResultFound

class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError('Timezone-aware datetime required')
        return value.astimezone(timezone.utc) if value else None
    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

class Base(DeclarativeBase):
    __abstract__ = True
    DoesNotExist = NoResultFound
    @property
    def pk(self): return getattr(self, inspect(type(self)).primary_key[0].key)
    def save(self, **options):
        from app.db.session import get_session
        session = get_session(); session.add(self); session.flush()
    def refresh_from_db(self):
        from app.db.session import get_session
        get_session().refresh(self)
