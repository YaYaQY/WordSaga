import uuid
from datetime import datetime, timedelta, timezone

from app.storage.protocol import Store
from app.storage.util import now_iso

MIN_EASE = 1.3
DEFAULT_EASE = 2.5
MASTERED_MASTERY = 0.85
MASTERED_REPETITIONS = 4
LEECH_FAIL_STREAK = 3
LEECH_WRONG_RATIO = 0.6
SAME_DAY_SM2 = timedelta(hours=24)
INCOMPLETE_DUE = timedelta(days=1)
MASTERED_INTERVAL = 30
MASTERED_LONG_INTERVAL = 90
REVIEW_TRACK_SOURCES = {"review", "wrong", "weak"}
STAGE_WEIGHTS = {2: 0.2, 3: 0.3, 4: 0.5}
PROMPT_BY_STAGE = {1: "context", 2: "recall_meaning", 3: "card", 4: "blind"}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class MemoryService:
    def __init__(self, store: Store):
        self.store = store

    def _new_card(self, word: str) -> dict:
        return {
            "word": word,
            "first_learned_at": None,
            "last_seen_at": None,
            "learn_count": 0,
            "review_count": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "spelling_wrong_count": 0,
            "meaning_wrong_count": 0,
            "last_error_type": None,
            "last_prompt_type": None,
            "mastery": 0.0,
            "repetitions": 0,
            "interval_days": 0,
            "ease_factor": DEFAULT_EASE,
            "next_review_at": None,
            "incomplete_due_at": None,
            "last_sm2_at": None,
            "session_fail_streak": 0,
            "is_leech": False,
            "status": "new",
        }

    def _get_card(self, memory: dict[str, dict], word: str) -> dict:
        key = word.lower()
        if key not in memory:
            memory[key] = self._new_card(word)
        return memory[key]

    def _validate_card(self, card: dict) -> None:
        required = self._new_card(card["word"])
        missing = [key for key in required if key not in card]
        if missing:
            raise RuntimeError(f"word_memory 字段缺失 {card['word']}：{', '.join(missing)}")

    def list_memory_cards(self) -> dict[str, dict]:
        memory = self.store.get_word_memory()
        for card in memory.values():
            self._validate_card(card)
        return memory

    def _word_source(self, session_id: str, word: str) -> str:
        session = self.store.get_session(session_id)
        for row in session["words"]:
            if row["word"].lower() == word.lower():
                return row["source"]
        raise RuntimeError(f"Session 中不存在单词：{word}")

    def _is_review_track(self, session_id: str, word: str) -> bool:
        return self._word_source(session_id, word) in REVIEW_TRACK_SOURCES

    def _interval_after_second_success(self, composite: int) -> int:
        if composite >= 5:
            return 6
        if composite >= 4:
            return 3
        return 2

    def _apply_sm2(self, card: dict, quality: int, composite: int, occurred_at: str) -> None:
        if quality < 3:
            card["repetitions"] = 0
            card["interval_days"] = 1
        else:
            if card["repetitions"] == 0:
                card["interval_days"] = 1
            elif card["repetitions"] == 1:
                card["interval_days"] = self._interval_after_second_success(composite)
            else:
                card["interval_days"] = round(card["interval_days"] * card["ease_factor"])

            if card["is_leech"]:
                card["interval_days"] = min(card["interval_days"], 3)

            if card["repetitions"] >= MASTERED_REPETITIONS and card["mastery"] >= MASTERED_MASTERY:
                card["interval_days"] = (
                    MASTERED_LONG_INTERVAL if card["repetitions"] > MASTERED_REPETITIONS else MASTERED_INTERVAL
                )

            card["repetitions"] += 1

        card["ease_factor"] = max(
            MIN_EASE,
            card["ease_factor"] + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
        )
        due = _parse_iso(occurred_at) + timedelta(days=card["interval_days"])
        card["next_review_at"] = due.isoformat()
        card["last_sm2_at"] = occurred_at
        card["incomplete_due_at"] = None

    def _refresh_status(self, card: dict) -> None:
        if card["review_count"] == 0 and card["learn_count"] > 0:
            card["status"] = "learning"
            return
        if card["mastery"] >= MASTERED_MASTERY and card["repetitions"] >= MASTERED_REPETITIONS:
            card["status"] = "mastered"
        elif card["review_count"] > 0:
            card["status"] = "review"
        elif card["learn_count"] > 0:
            card["status"] = "learning"

    def _refresh_leech(self, card: dict) -> None:
        review_count = int(card["review_count"])
        wrong_count = int(card["wrong_count"])
        if int(card["session_fail_streak"]) >= LEECH_FAIL_STREAK:
            card["is_leech"] = True
            return
        if review_count >= 3 and wrong_count / review_count >= LEECH_WRONG_RATIO:
            card["is_leech"] = True
            return
        if review_count >= 2 and wrong_count == 0:
            card["is_leech"] = False

    def _append_event(
        self,
        events: list[dict],
        *,
        word: str,
        session_id: str,
        event_type: str,
        stage: int,
        result: str,
        quality: int,
        detail: dict,
        occurred_at: str,
    ) -> None:
        events.append(
            {
                "id": str(uuid.uuid4()),
                "word": word,
                "session_id": session_id,
                "event_type": event_type,
                "stage": stage,
                "result": result,
                "quality": quality,
                "detail": detail,
                "occurred_at": occurred_at,
            }
        )

    def _save(self, memory: dict[str, dict], events: list[dict]) -> None:
        for card in memory.values():
            self._validate_card(card)
        self.store.save_word_memory(memory)
        if events:
            self.store.append_word_events(events)

    def _touch_card(self, card: dict, occurred_at: str) -> None:
        card["last_seen_at"] = occurred_at

    def _stage_quality_from_answer(self, answer: dict) -> tuple[int, str]:
        if answer["skipped"]:
            return 0, "wrong"
        if answer["meaning_correct"]:
            return 4, "correct"
        return 1, "wrong"

    def _grade_quality(self, spelling_correct: bool, meaning_correct: bool) -> tuple[int, str]:
        if spelling_correct and meaning_correct:
            return 5, "correct"
        if spelling_correct or meaning_correct:
            return 3, "partial"
        return 1, "wrong"

    def _session_stage_event(self, session_id: str, word: str, stage: int) -> dict | None:
        key = word.lower()
        for event in reversed(self.store.get_word_events()):
            if event["session_id"] != session_id:
                continue
            if event["word"].lower() != key:
                continue
            if event["stage"] != stage:
                continue
            if event["event_type"] != "stage_submit":
                continue
            return event
        return None

    def _session_stage_skipped(self, session_id: str, word: str) -> bool:
        event = self._session_stage_event(session_id, word, 2)
        if event is None:
            return False
        return bool(event["detail"]["skipped"])

    def _composite_quality(
        self,
        session_id: str,
        word: str,
        stage4_quality: int,
        review_track: bool,
    ) -> int:
        present: dict[int, int] = {}
        if not review_track:
            quality = self._session_stage_event(session_id, word, 2)
            if quality is not None:
                present[2] = int(quality["quality"])
        for stage in (3,):
            event = self._session_stage_event(session_id, word, stage)
            if event is not None:
                present[stage] = int(event["quality"])
        present[4] = stage4_quality
        total_weight = sum(STAGE_WEIGHTS[stage] for stage in present)
        score = sum(STAGE_WEIGHTS[stage] * present[stage] for stage in present) / total_weight
        return round(score)

    def _session_is_correct(
        self,
        session_id: str,
        word: str,
        stage4_result: str,
        review_track: bool,
    ) -> bool:
        if stage4_result != "correct":
            return False
        if self._session_stage_skipped(session_id, word):
            return False
        stages = (3,) if review_track else (2, 3)
        for stage in stages:
            event = self._session_stage_event(session_id, word, stage)
            if event is None:
                continue
            if event["result"] != "correct":
                return False
        return True

    def _record_error_types(self, card: dict, spelling_correct: bool, meaning_correct: bool, skipped: bool) -> None:
        if skipped:
            card["last_error_type"] = "skip"
            return
        if not spelling_correct and not meaning_correct:
            card["spelling_wrong_count"] += 1
            card["meaning_wrong_count"] += 1
            card["last_error_type"] = "both"
        elif not spelling_correct:
            card["spelling_wrong_count"] += 1
            card["last_error_type"] = "spelling"
        elif not meaning_correct:
            card["meaning_wrong_count"] += 1
            card["last_error_type"] = "meaning"
        else:
            card["last_error_type"] = None

    def _same_day_sm2_blocked(self, card: dict, occurred_at: str) -> bool:
        last_sm2_at = card["last_sm2_at"]
        if last_sm2_at is None:
            return False
        return _parse_iso(occurred_at) - _parse_iso(last_sm2_at) < SAME_DAY_SM2

    def record_stage1_complete(self, session_id: str, words: list[str]) -> None:
        memory = self.store.get_word_memory()
        events: list[dict] = []
        occurred_at = now_iso()
        incomplete_due = (_parse_iso(occurred_at) + INCOMPLETE_DUE).isoformat()

        for word in words:
            card = self._get_card(memory, word)
            if card["first_learned_at"] is None:
                card["first_learned_at"] = occurred_at
            card["learn_count"] += 1
            card["last_prompt_type"] = PROMPT_BY_STAGE[1]
            card["incomplete_due_at"] = incomplete_due
            self._touch_card(card, occurred_at)
            self._refresh_status(card)
            self._append_event(
                events,
                word=card["word"],
                session_id=session_id,
                event_type="stage1_complete",
                stage=1,
                result="seen",
                quality=0,
                detail={},
                occurred_at=occurred_at,
            )

        self._save(memory, events)

    def record_review_context(self, session_id: str, words: list[str]) -> None:
        memory = self.store.get_word_memory()
        events: list[dict] = []
        occurred_at = now_iso()

        for word in words:
            card = self._get_card(memory, word)
            card["last_prompt_type"] = "context_revisit"
            self._touch_card(card, occurred_at)
            self._append_event(
                events,
                word=card["word"],
                session_id=session_id,
                event_type="context_revisit",
                stage=3,
                result="seen",
                quality=0,
                detail={},
                occurred_at=occurred_at,
            )

        self._save(memory, events)

    def record_stage2_submit(self, session_id: str, answers: list[dict]) -> None:
        memory = self.store.get_word_memory()
        events: list[dict] = []
        occurred_at = now_iso()

        for answer in answers:
            if self._is_review_track(session_id, answer["word"]):
                continue

            card = self._get_card(memory, answer["word"])
            quality, result = self._stage_quality_from_answer(answer)
            card["last_prompt_type"] = PROMPT_BY_STAGE[2]
            self._touch_card(card, occurred_at)
            if result != "correct":
                self._record_error_types(card, True, answer["meaning_correct"], answer["skipped"])
            self._append_event(
                events,
                word=card["word"],
                session_id=session_id,
                event_type="stage_submit",
                stage=2,
                result=result,
                quality=quality,
                detail={
                    "user_answer": answer["meaning_answer"],
                    "correct_answer": answer["expected_meaning"],
                    "skipped": answer["skipped"],
                    "meaning_correct": answer["meaning_correct"],
                },
                occurred_at=occurred_at,
            )

        self._save(memory, events)

    def record_stage3_submit(
        self,
        session_id: str,
        graded_items: list[dict],
        answer_map: dict[str, dict],
    ) -> None:
        memory = self.store.get_word_memory()
        events: list[dict] = []
        occurred_at = now_iso()

        for graded in graded_items:
            word_key = graded["word"].lower()
            quality, result = self._grade_quality(
                graded["spelling_correct"],
                graded["meaning_correct"],
            )
            if result == "partial":
                result = "wrong"
                quality = 2

            card = self._get_card(memory, graded["word"])
            card["last_prompt_type"] = PROMPT_BY_STAGE[3]
            self._touch_card(card, occurred_at)
            if result != "correct":
                self._record_error_types(
                    card,
                    graded["spelling_correct"],
                    graded["meaning_correct"],
                    False,
                )
            answer = answer_map[word_key]
            self._append_event(
                events,
                word=card["word"],
                session_id=session_id,
                event_type="stage_submit",
                stage=3,
                result=result,
                quality=quality,
                detail={
                    "user_answer": answer["spelling_answer"],
                    "correct_answer": graded["word"],
                    "spelling_correct": graded["spelling_correct"],
                    "meaning_correct": graded["meaning_correct"],
                    "sentence_correct": graded["sentence_correct"],
                },
                occurred_at=occurred_at,
            )

        self._save(memory, events)

    def record_stage4_submit(
        self,
        session_id: str,
        graded_items: list[dict],
        answer_map: dict[str, dict],
    ) -> list[dict]:
        memory = self.store.get_word_memory()
        events: list[dict] = []
        occurred_at = now_iso()
        summaries: list[dict] = []

        for graded in graded_items:
            word_key = graded["word"].lower()
            stage4_quality, stage4_result = self._grade_quality(
                graded["spelling_correct"],
                graded["meaning_correct"],
            )
            if stage4_result == "partial":
                stage4_result = "wrong"
                stage4_quality = 2

            card = self._get_card(memory, graded["word"])
            review_track = self._is_review_track(session_id, graded["word"])
            composite_quality = self._composite_quality(
                session_id,
                graded["word"],
                stage4_quality,
                review_track,
            )
            skipped = self._session_stage_skipped(session_id, graded["word"])
            if skipped:
                composite_quality = min(composite_quality, 2)

            session_correct = self._session_is_correct(
                session_id,
                graded["word"],
                stage4_result,
                review_track,
            )
            card["last_prompt_type"] = PROMPT_BY_STAGE[4]
            card["review_count"] += 1
            self._touch_card(card, occurred_at)

            if session_correct:
                card["correct_count"] += 1
                card["session_fail_streak"] = 0
            else:
                card["wrong_count"] += 1
                card["session_fail_streak"] = int(card["session_fail_streak"]) + 1
                self._record_error_types(
                    card,
                    graded["spelling_correct"],
                    graded["meaning_correct"],
                    skipped,
                )

            card["mastery"] = round(card["correct_count"] / card["review_count"], 2)
            self._refresh_leech(card)

            same_day_blocked = self._same_day_sm2_blocked(card, occurred_at)
            sm2_applied = False
            if not same_day_blocked:
                sm2_quality = composite_quality if not skipped else min(composite_quality, 2)
                self._apply_sm2(card, sm2_quality, composite_quality, occurred_at)
                sm2_applied = True

            self._refresh_status(card)

            answer = answer_map[word_key]
            self._append_event(
                events,
                word=card["word"],
                session_id=session_id,
                event_type="stage_submit",
                stage=4,
                result=stage4_result,
                quality=stage4_quality,
                detail={
                    "user_answer": answer["spelling_answer"],
                    "correct_answer": graded["word"],
                    "spelling_correct": graded["spelling_correct"],
                    "meaning_correct": graded["meaning_correct"],
                    "composite_quality": composite_quality,
                    "session_correct": session_correct,
                    "review_track": review_track,
                    "skipped_stage2": skipped,
                    "same_day_sm2_blocked": same_day_blocked,
                    "sm2_applied": sm2_applied,
                },
                occurred_at=occurred_at,
            )
            summaries.append(
                {
                    "word": card["word"],
                    "session_correct": session_correct,
                    "next_review_at": card["next_review_at"],
                    "interval_days": card["interval_days"],
                    "mastery": card["mastery"],
                    "is_leech": card["is_leech"],
                    "same_day_sm2_blocked": same_day_blocked,
                }
            )

        self._save(memory, events)
        return summaries

    def is_due(self, card: dict, now: datetime) -> bool:
        self._validate_card(card)
        next_review_at = card["next_review_at"]
        if next_review_at is not None and _parse_iso(next_review_at) <= now:
            return True
        incomplete_due_at = card["incomplete_due_at"]
        if incomplete_due_at is not None and _parse_iso(incomplete_due_at) <= now:
            return True
        return False

    def list_wrong_records(self) -> list[dict]:
        records: list[dict] = []
        for event in self.store.get_word_events():
            if event["result"] not in {"wrong", "partial"}:
                continue
            detail = event["detail"]
            records.append(
                {
                    "word": event["word"],
                    "session_id": event["session_id"],
                    "stage": event["stage"],
                    "user_answer": detail["user_answer"],
                    "correct_answer": detail["correct_answer"],
                    "error_type": f"stage{event['stage']}",
                    "created_at": event["occurred_at"],
                }
            )
        records.sort(key=lambda row: row["created_at"], reverse=True)
        return records

    def get_word_memory(self, word: str) -> dict | None:
        card = self.store.get_word_memory().get(word.lower())
        if card is None:
            return None
        self._validate_card(card)
        return card

    def list_word_events(self, word: str) -> list[dict]:
        key = word.lower()
        return [event for event in self.store.get_word_events() if event["word"].lower() == key]

    def recompute_from_events(self) -> int:
        events = sorted(self.store.get_word_events(), key=lambda item: item["occurred_at"])
        memory: dict[str, dict] = {}
        for event in events:
            word = event["word"]
            card = self._get_card(memory, word)
            occurred_at = event["occurred_at"]
            self._touch_card(card, occurred_at)

            if event["event_type"] == "stage1_complete":
                if card["first_learned_at"] is None:
                    card["first_learned_at"] = occurred_at
                card["learn_count"] += 1
                card["incomplete_due_at"] = (_parse_iso(occurred_at) + INCOMPLETE_DUE).isoformat()
                card["last_prompt_type"] = PROMPT_BY_STAGE[1]
            elif event["event_type"] == "context_revisit":
                card["last_prompt_type"] = "context_revisit"
            elif event["event_type"] == "stage_submit" and event["stage"] == 2:
                card["last_prompt_type"] = PROMPT_BY_STAGE[2]
            elif event["event_type"] == "stage_submit" and event["stage"] == 3:
                card["last_prompt_type"] = PROMPT_BY_STAGE[3]
            elif event["event_type"] == "stage_submit" and event["stage"] == 4:
                detail = event["detail"]
                card["last_prompt_type"] = PROMPT_BY_STAGE[4]
                card["review_count"] += 1
                if detail["session_correct"]:
                    card["correct_count"] += 1
                    card["session_fail_streak"] = 0
                else:
                    card["wrong_count"] += 1
                    card["session_fail_streak"] = int(card["session_fail_streak"]) + 1
                card["mastery"] = round(card["correct_count"] / card["review_count"], 2)
                if detail["sm2_applied"]:
                    card["last_sm2_at"] = occurred_at
                    card["incomplete_due_at"] = None
                self._refresh_leech(card)
                self._refresh_status(card)

        for card in memory.values():
            self._validate_card(card)
        self.store.save_word_memory(memory)
        return len(memory)
