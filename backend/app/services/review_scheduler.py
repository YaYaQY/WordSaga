from datetime import datetime, timezone

from app.schemas.vocabulary import SelectedWord
from app.storage.protocol import Store


class ReviewScheduler:
    def __init__(self, store: Store, vocabulary: list[dict]):
        self.store = store
        self.vocabulary = {row["word"]: row for row in vocabulary}

    def _days_since(self, last_seen: str | None) -> int:
        if not last_seen:
            return 9999
        previous = datetime.fromisoformat(last_seen)
        delta = datetime.now(timezone.utc) - previous.replace(tzinfo=timezone.utc)
        return max(0, delta.days)

    def pick_review_words(self, count: int, level: str) -> list[SelectedWord]:
        progress = self.store.get_word_progress()
        wrong_records = self.store.get_wrong_records()
        wrong_bonus: dict[str, int] = {}
        for record in wrong_records:
            word = record["word"]
            wrong_bonus[word] = wrong_bonus.get(word, 0) + 500

        candidates: list[tuple[float, dict, dict]] = []
        for word, record in progress.items():
            row = self.vocabulary.get(word)
            if row is None:
                continue
            if level == "basic" and row["level"] != "basic":
                continue
            if level == "cet6" and row["level"] != "cet6":
                continue

            wrong_count = int(record.get("wrong_count", 0))
            days = self._days_since(record.get("last_seen"))
            if wrong_count == 0 and days < 1:
                continue
            score = wrong_count * 1000 + days * 10 + row["frequency"] + wrong_bonus.get(word, 0)
            candidates.append((score, row, record))

        candidates.sort(key=lambda item: item[0], reverse=True)

        selected: list[SelectedWord] = []
        used = set()
        for _, row, record in candidates:
            if len(selected) >= count:
                break
            if row["word"] in used:
                continue
            source = "wrong" if int(record.get("wrong_count", 0)) > 0 else "review"
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
