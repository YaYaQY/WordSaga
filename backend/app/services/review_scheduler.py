from datetime import datetime, timezone

from app.schemas.vocabulary import SelectedWord
from app.services.memory_service import MemoryService
from app.storage.protocol import Store


class ReviewScheduler:
    def __init__(self, store: Store, vocabulary: list[dict]):
        self.store = store
        self.vocabulary = {row["word"]: row for row in vocabulary}
        self.memory_service = MemoryService(store)

    def _days_since(self, last_seen: str | None) -> int:
        if last_seen is None:
            return 9999
        previous = datetime.fromisoformat(last_seen)
        delta = datetime.now(timezone.utc) - previous.replace(tzinfo=timezone.utc)
        return max(0, delta.days)

    def _overdue_days(self, card: dict, now: datetime) -> int:
        next_review_at = card["next_review_at"]
        if next_review_at is not None:
            due = datetime.fromisoformat(next_review_at).replace(tzinfo=timezone.utc)
            if due <= now:
                return (now - due).days
        incomplete_due_at = card["incomplete_due_at"]
        if incomplete_due_at is not None:
            due = datetime.fromisoformat(incomplete_due_at).replace(tzinfo=timezone.utc)
            if due <= now:
                return (now - due).days
        return 0

    def pick_review_words(self, count: int, level: str) -> list[SelectedWord]:
        memory = self.memory_service.list_memory_cards()
        now = datetime.now(timezone.utc)

        candidates: list[tuple[float, dict, dict]] = []
        for word, card in memory.items():
            row = self.vocabulary.get(word)
            if row is None:
                continue
            if level == "basic" and row["level"] != "basic":
                continue
            if level == "cet6" and row["level"] != "cet6":
                continue
            if card["review_count"] == 0 and card["learn_count"] == 0:
                continue
            if not self.memory_service.is_due(card, now) and card["wrong_count"] == 0:
                continue

            wrong_count = card["wrong_count"]
            days = self._days_since(card["last_seen_at"])
            overdue_days = self._overdue_days(card, now)
            leech_bonus = 3000 if card["is_leech"] else 0
            incomplete_bonus = 1500 if card["incomplete_due_at"] is not None else 0
            score = (
                leech_bonus
                + incomplete_bonus
                + overdue_days * 100
                + wrong_count * 1000
                + days * 10
                + row["frequency"]
            )
            candidates.append((score, row, card))

        candidates.sort(key=lambda item: item[0], reverse=True)

        selected: list[SelectedWord] = []
        used = set()
        for _, row, card in candidates:
            if len(selected) >= count:
                break
            if row["word"] in used:
                continue
            source = "wrong" if card["wrong_count"] > 0 else "review"
            selected.append(
                SelectedWord(
                    word=row["word"],
                    rank=row["rank"],
                    frequency=row["frequency"],
                    level=row["level"],
                    meaning=row["meaning"],
                    source=source,
                )
            )
            used.add(row["word"])
        return selected

    def list_due_words(self, level: str, limit: int) -> list[dict]:
        memory = self.memory_service.list_memory_cards()
        now = datetime.now(timezone.utc)
        rows: list[tuple[int, dict, dict]] = []

        for word, card in memory.items():
            row = self.vocabulary.get(word)
            if row is None:
                continue
            if level == "basic" and row["level"] != "basic":
                continue
            if level == "cet6" and row["level"] != "cet6":
                continue
            if not self.memory_service.is_due(card, now):
                continue
            overdue_days = self._overdue_days(card, now)
            rows.append((overdue_days, row, card))

        rows.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "word": row["word"],
                "rank": row["rank"],
                "frequency": row["frequency"],
                "level": row["level"],
                "meaning": row["meaning"],
                "memory": card,
            }
            for _, row, card in rows[:limit]
        ]

    def count_due_words(self, level: str) -> int:
        return len(self.list_due_words(level, limit=10000))
