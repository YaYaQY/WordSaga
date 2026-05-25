from app.storage.local_store import LocalStore
from app.storage.protocol import Store

_store: LocalStore | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = LocalStore()
    return _store
