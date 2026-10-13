from contextlib import ContextDecorator
from app.db.session import get_session

class _Atomic(ContextDecorator):
    def __enter__(self):
        self.transaction=get_session().begin_nested(); self.transaction.__enter__(); return self
    def __exit__(self,*args): return self.transaction.__exit__(*args)
    def _recreate_cm(self): return type(self)()

def atomic(function=None):
    context = _Atomic()
    return context(function) if function is not None else context
