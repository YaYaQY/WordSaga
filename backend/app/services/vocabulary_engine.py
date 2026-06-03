import json
import re

from app.config import VOCAB_JSON_PATH
from app.schemas.vocabulary import SelectedWord
from app.services.memory_service import MemoryService
from app.services.review_scheduler import ReviewScheduler
from app.services.weak_scheduler import WeakScheduler
from app.storage.protocol import Store

_VOCAB_CACHE: list[dict] | None = None


def normalize_word(word: str) -> str:
    return word.strip().lower()


def parse_word_list(text: str) -> list[str]:
    return [normalize_word(part) for part in re.split(r"[\s,，;；]+", text) if part.strip()]


class VocabularyEngine:
    def __init__(self, store: Store):
        self.store = store
        self._vocabulary = self._load_vocabulary()
        self.scheduler = ReviewScheduler(store, self._vocabulary)
        self.weak_scheduler = WeakScheduler(store, self._vocabulary)

    def _load_vocabulary(self) -> list[dict]:
        global _VOCAB_CACHE
        if _VOCAB_CACHE is not None:
            return _VOCAB_CACHE

        data = json.loads(VOCAB_JSON_PATH.read_text(encoding="utf-8"))
        items = data["四六级词汇词频排序表"]
        deduped: dict[str, dict] = {}
        for item in items:
            word = normalize_word(str(item["单词"]))
            if not word:
                continue
            entry = {
                "word": word,
                "rank": int(item["序号"]),
                "frequency": int(item["词频"]),
                "level": "cet6" if item.get("六级") == "★" else "basic",
                "meaning": str(item["释义"]).strip(),
            }
            if word not in deduped or entry["rank"] < deduped[word]["rank"]:
                deduped[word] = entry
        _VOCAB_CACHE = sorted(deduped.values(), key=lambda row: row["rank"])
        return _VOCAB_CACHE

    def vocabulary_count(self) -> int:
        return len(self._vocabulary)

    def get_word(self, word: str) -> dict | None:
        for row in self._vocabulary:
            if row["word"] == word:
                return row
        return None

    def _filter_by_level(self, level: str) -> list[dict]:
        if level == "basic":
            return [row for row in self._vocabulary if row["level"] == "basic"]
        if level == "cet6":
            return [row for row in self._vocabulary if row["level"] == "cet6"]
        return list(self._vocabulary)

    def select_by_frequency(self, count: int, level: str, start_rank: int | None) -> list[SelectedWord]:
        start = start_rank if start_rank is not None else self.store.get_last_rank()
        progress = MemoryService(self.store).list_memory_cards()
        mastered_words = {
            word
            for word, record in progress.items()
            if record["status"] == "mastered" or record["mastery"] >= 0.85
        }

        review_words = self.scheduler.pick_review_words(count=count * 3 // 10, level=level)
        selected: list[SelectedWord] = []
        used = set()

        for item in review_words:
            if len(selected) >= count:
                break
            selected.append(item)
            used.add(item.word)

        for row in self._filter_by_level(level):
            if len(selected) >= count:
                break
            if row["rank"] <= start:
                continue
            if row["word"] in used or row["word"] in mastered_words:
                continue
            selected.append(
                SelectedWord(
                    word=row["word"],
                    rank=row["rank"],
                    frequency=row["frequency"],
                    level=row["level"],
                    meaning=row["meaning"],
                    source="new",
                )
            )
            used.add(row["word"])

        if len(selected) < count:
            raise RuntimeError(f"词库可用新词不足，当前仅选到 {len(selected)} 个，需要 {count} 个")

        return selected

    def select_manual(self, words: list[str]) -> list[SelectedWord]:
        normalized = []
        seen = set()
        for raw in words:
            word = normalize_word(raw)
            if word in seen:
                continue
            seen.add(word)
            normalized.append(word)

        selected: list[SelectedWord] = []
        for word in normalized:
            row = self.get_word(word)
            if row is None:
                raise RuntimeError(f"词库中不存在：{word}")
            selected.append(
                SelectedWord(
                    word=row["word"],
                    rank=row["rank"],
                    frequency=row["frequency"],
                    level=row["level"],
                    meaning=row["meaning"],
                    source="manual",
                )
            )
        return selected

    def select_due_review(self, count: int, level: str) -> list[SelectedWord]:
        due_rows = self.scheduler.list_due_words(level=level, limit=count)
        if not due_rows:
            raise RuntimeError("目前没有到期的复习词")
        return [
            SelectedWord(
                word=row["word"],
                rank=row["rank"],
                frequency=row["frequency"],
                level=row["level"],
                meaning=row["meaning"],
                source="review",
            )
            for row in due_rows[:count]
        ]

    def select_weak_words(self, count: int, level: str) -> list[SelectedWord]:
        selected = self.weak_scheduler.pick_weak_words(count=count, level=level)
        if not selected:
            raise RuntimeError("目前没有需要薄弱巩固的词")
        return selected

    def count_weak_words(self, level: str) -> int:
        return self.weak_scheduler.count_weak_words(level)

    def list_due_words(self, level: str, limit: int) -> list[dict]:
        return self.scheduler.list_due_words(level=level, limit=limit)

    def count_due_words(self, level: str) -> int:
        return self.scheduler.count_due_words(level=level)
