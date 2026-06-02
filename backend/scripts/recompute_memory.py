"""从 word_events 重算 word_memory 聚合字段。

用法：
    cd backend
    python scripts/recompute_memory.py
"""

from app.deps import get_store
from app.services.memory_service import MemoryService


def main():
    store = get_store()
    service = MemoryService(store)
    count = service.recompute_from_events()
    print(f"recomputed {count} words from events")


if __name__ == "__main__":
    main()
