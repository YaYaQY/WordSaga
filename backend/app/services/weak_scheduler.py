from app.schemas.vocabulary import SelectedWord
from app.services.memory_service import MemoryService
from app.storage.protocol import Store

MASTERED_MASTERY = 0.85
WEAK_MASTERY = 0.6


class WeakScheduler:
    def __init__(self, store: Store, vocabulary: list[dict]):
        self.store = store
        self.vocabulary = {row["word"]: row for row in vocabulary}
        self.memory_service = MemoryService(store)

    def _is_mastered(self, card: dict) -> bool:
        return card["status"] == "mastered" or card["mastery"] >= MASTERED_MASTERY

    def _is_weak(self, card: dict) -> bool:
        if card["is_leech"]:
            return True
        if card["wrong_count"] > 0:
            return True
        if card["review_count"] > 0 and card["mastery"] < WEAK_MASTERY:
            return True
        return False

    def _level_match(self, row: dict, level: str) -> bool:
        if level == "basic":
            return row["level"] == "basic"
        if level == "cet6":
            return row["level"] == "cet6"
        return True

    def list_weak_candidates(self, level: str) -> list[tuple[float, dict, dict]]:
        memory = self.memory_service.list_memory_cards()
        candidates: list[tuple[float, dict, dict]] = []

        for word, card in memory.items():
            row = self.vocabulary.get(word)
            if row is None:
                continue
            if not self._level_match(row, level):
                continue
            if card["learn_count"] == 0 and card["review_count"] == 0:
                continue
            if self._is_mastered(card):
                continue
            if not self._is_weak(card):
                continue

            score = (
                (3000 if card["is_leech"] else 0)
                + card["wrong_count"] * 1000
                + int((1 - card["mastery"]) * 500)
                + row["frequency"]
            )
            candidates.append((score, row, card))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates

    def pick_weak_words(self, count: int, level: str) -> list[SelectedWord]:
        selected: list[SelectedWord] = []
        for _, row, _card in self.list_weak_candidates(level):
            if len(selected) >= count:
                break
            selected.append(
                SelectedWord(
                    word=row["word"],
                    rank=row["rank"],
                    frequency=row["frequency"],
                    level=row["level"],
                    meaning=row["meaning"],
                    source="weak",
                )
            )
        return selected

    def count_weak_words(self, level: str) -> int:
        return len(self.list_weak_candidates(level))
