import re

from app.schemas.stage import (
    GradeResult,
    Stage1Out,
    Stage2Out,
    Stage2SubmitRequest,
    Stage3Out,
    Stage3SubmitRequest,
    Stage3SubmitResponse,
    Stage4Out,
    Stage4SubmitRequest,
    Stage4SubmitResponse,
    WordCard,
    WordSessionSummary,
    WrongRecordOut,
)
from app.services.card_engine import CardEngine
from app.services.grading_service import GradingService
from app.services.memory_service import MemoryService
from app.services.story_engine import StoryEngine
from app.storage.protocol import Store


def mask_annotated_story(text: str, words: list[str]) -> str:
    masked = text
    for word in words:
        pattern = re.compile(rf"（{re.escape(word)}）", re.IGNORECASE)
        masked = pattern.sub("（ ）", masked)
    return masked


class StageController:
    def __init__(self, store: Store):
        self.store = store
        self.card_engine = CardEngine()
        self.grader = GradingService()
        self.memory = MemoryService(store)

    def _require_story(self, session: dict) -> dict:
        story = session.get("story")
        if story is None:
            raise RuntimeError("请先生成剧情")
        return story

    def _session_words(self, session: dict) -> list[str]:
        return [row["word"] for row in session["words"]]

    def _meaning_map(self, session: dict) -> dict[str, str]:
        return {row["word"].lower(): row["meaning"] for row in session["words"]}

    def _ensure_story_enriched(self, session_id: str) -> None:
        StoryEngine(self.store).ensure_enriched(session_id)

    def _memory_fields(self, word: str) -> dict:
        memory = self.memory.get_word_memory(word)
        if memory is None:
            raise RuntimeError(f"缺少记忆卡片：{word}")
        return {
            "next_review_at": memory["next_review_at"],
            "incomplete_due_at": memory["incomplete_due_at"],
            "mastery": memory["mastery"],
            "is_leech": memory["is_leech"],
        }

    def get_stage1(self, session_id: str) -> Stage1Out:
        session = self.store.get_session(session_id)
        story = self._require_story(session)
        chapters = [
            {
                "chapter_index": chapter["chapter_index"],
                "annotated_story_zh": chapter["annotated_story_zh"],
            }
            for chapter in story["chapters"]
        ]
        return Stage1Out(
            session_id=session_id,
            status=session["status"],
            title=story["title"],
            summary=story["summary"],
            chapters=chapters,
        )

    def complete_stage1(self, session_id: str) -> Stage1Out:
        session = self.store.get_session(session_id)
        self._require_story(session)
        new_words = [
            row["word"]
            for row in session["words"]
            if row["source"] not in {"review", "wrong", "weak"}
        ]
        self.memory.record_stage1_complete(session_id, new_words)
        self.store.update_session(session_id, {"status": "stage2"})
        return self.get_stage1(session_id)

    def get_stage2(self, session_id: str) -> Stage2Out:
        session = self.store.get_session(session_id)
        story = self._require_story(session)
        words = self._session_words(session)
        chapters = [
            {
                "chapter_index": chapter["chapter_index"],
                "masked_story": mask_annotated_story(chapter["annotated_story_zh"], words),
            }
            for chapter in story["chapters"]
        ]
        return Stage2Out(
            session_id=session_id,
            status=session["status"],
            chapters=chapters,
            words=words,
        )

    def submit_stage2(self, session_id: str, payload: Stage2SubmitRequest) -> Stage2Out:
        session = self.store.get_session(session_id)
        self._require_story(session)
        meanings = self._meaning_map(session)

        grade_payloads = []
        for item in payload.answers:
            if item.skipped:
                continue
            grade_payloads.append(
                {
                    "word": item.word,
                    "expected_meaning": meanings[item.word.lower()],
                    "user_meaning": item.meaning_answer,
                }
            )

        graded_map = {
            row["word"].lower(): row["meaning_correct"]
            for row in self.grader.grade_meaning_batch(grade_payloads)
        }

        stage2_answers = []
        for item in payload.answers:
            stage2_answers.append(
                {
                    "word": item.word,
                    "meaning_answer": item.meaning_answer,
                    "expected_meaning": meanings[item.word.lower()],
                    "skipped": item.skipped,
                    "meaning_correct": graded_map[item.word.lower()] if not item.skipped else False,
                }
            )

        self.memory.record_stage2_submit(session_id, stage2_answers)
        self.store.update_session(
            session_id,
            {
                "stage2_answers": [item.model_dump() for item in payload.answers],
                "status": "stage3",
            },
        )
        return self.get_stage2(session_id)

    def get_stage3(self, session_id: str) -> Stage3Out:
        session = self.store.get_session(session_id)
        story = self._require_story(session)
        self._ensure_story_enriched(session_id)
        session = self.store.get_session(session_id)
        story = session["story"]
        if session.get("mode") in {"review", "weak"}:
            context_words = self._session_words(session)
        else:
            context_words = [
                row["word"] for row in session["words"] if row["source"] in {"review", "wrong", "weak"}
            ]
        if context_words:
            self.memory.record_review_context(session_id, context_words)
        cards = self.card_engine.build_cards(story, session["words"])
        enriched_cards = [{**card, **self._memory_fields(card["word"])} for card in cards]
        return Stage3Out(
            session_id=session_id,
            status=session["status"],
            cards=[WordCard(**card) for card in enriched_cards],
        )

    def submit_stage3(self, session_id: str, payload: Stage3SubmitRequest) -> Stage3SubmitResponse:
        session = self.store.get_session(session_id)
        self._require_story(session)
        self._ensure_story_enriched(session_id)
        session = self.store.get_session(session_id)
        story = session["story"]
        cards = {card["word"].lower(): card for card in self.card_engine.build_cards(story, session["words"])}

        grade_payloads = []
        for answer in payload.answers:
            word = answer.word.lower()
            card = cards[word]
            grade_payloads.append(
                {
                    "word": card["word"],
                    "expected_meaning": card["meaning"],
                    "reference_sentence": card["sentence_en"],
                    "user_spelling": answer.spelling_answer,
                    "user_meaning": answer.meaning_answer,
                    "user_sentence": answer.sentence_answer,
                }
            )

        graded_items = self.grader.grade_batch(grade_payloads)
        results: list[GradeResult] = []
        answer_map = {
            item.word.lower(): {
                "spelling_answer": item.spelling_answer,
                "meaning_answer": item.meaning_answer,
                "sentence_answer": item.sentence_answer,
            }
            for item in payload.answers
        }

        for graded in graded_items:
            results.append(GradeResult(**graded))

        self.memory.record_stage3_submit(session_id, graded_items, answer_map)
        self.store.update_session(
            session_id,
            {
                "stage3_results": [item.model_dump() for item in results],
                "status": "stage4",
            },
        )
        return Stage3SubmitResponse(session_id=session_id, status="stage4", results=results)

    def get_stage4(self, session_id: str) -> Stage4Out:
        session = self.store.get_session(session_id)
        self._require_story(session)
        return Stage4Out(
            session_id=session_id,
            status=session["status"],
            words=self._session_words(session),
        )

    def submit_stage4(self, session_id: str, payload: Stage4SubmitRequest) -> Stage4SubmitResponse:
        session = self.store.get_session(session_id)
        self._require_story(session)
        self._ensure_story_enriched(session_id)
        session = self.store.get_session(session_id)
        story = session["story"]
        cards = {card["word"].lower(): card for card in self.card_engine.build_cards(story, session["words"])}

        grade_payloads = [
            {
                "word": cards[answer.word.lower()]["word"],
                "expected_meaning": cards[answer.word.lower()]["meaning"],
                "reference_sentence": cards[answer.word.lower()]["sentence_en"],
                "user_spelling": answer.spelling_answer,
                "user_meaning": answer.meaning_answer,
                "user_sentence": "",
            }
            for answer in payload.answers
        ]
        graded_items = self.grader.grade_batch(grade_payloads)

        results: list[GradeResult] = []
        answer_map = {
            item.word.lower(): {
                "spelling_answer": item.spelling_answer,
                "meaning_answer": item.meaning_answer,
            }
            for item in payload.answers
        }

        for graded in graded_items:
            results.append(GradeResult(**graded))

        word_summaries = self.memory.record_stage4_submit(session_id, graded_items, answer_map)
        self.store.update_session(
            session_id,
            {
                "stage4_results": [item.model_dump() for item in results],
                "status": "done",
            },
        )
        return Stage4SubmitResponse(
            session_id=session_id,
            status="done",
            results=results,
            word_summaries=[WordSessionSummary(**row) for row in word_summaries],
        )

    def list_wrong_records(self) -> list[WrongRecordOut]:
        records = self.memory.list_wrong_records()
        return [WrongRecordOut(**record) for record in records]
