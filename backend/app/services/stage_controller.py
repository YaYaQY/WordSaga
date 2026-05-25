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
    WrongRecordOut,
)
from app.services.card_engine import CardEngine
from app.services.grading_service import GradingService
from app.services.story_engine import StoryEngine
from app.storage.protocol import Store
from app.storage.util import now_iso


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

    def _require_story(self, session: dict) -> dict:
        story = session.get("story")
        if story is None:
            raise RuntimeError("请先生成剧情")
        return story

    def _session_words(self, session: dict) -> list[str]:
        return [row["word"] for row in session["words"]]

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
        StoryEngine(self.store).ensure_enriched(session_id)
        session = self.store.get_session(session_id)
        story = session["story"]
        cards = self.card_engine.build_cards(story, session["words"])
        return Stage3Out(
            session_id=session_id,
            status=session["status"],
            cards=[WordCard(**card) for card in cards],
        )

    def submit_stage3(self, session_id: str, payload: Stage3SubmitRequest) -> Stage3SubmitResponse:
        session = self.store.get_session(session_id)
        self._require_story(session)
        StoryEngine(self.store).ensure_enriched(session_id)
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
        wrong_records = self.store.get_wrong_records()
        answer_map = {item.word.lower(): item for item in payload.answers}

        for graded in graded_items:
            result = GradeResult(**graded)
            results.append(result)
            if not (graded["spelling_correct"] and graded["meaning_correct"]):
                wrong_records.append(
                    {
                        "word": graded["word"],
                        "session_id": session_id,
                        "stage": 3,
                        "user_answer": answer_map[graded["word"].lower()].spelling_answer,
                        "correct_answer": graded["word"],
                        "error_type": "stage3",
                        "created_at": now_iso(),
                    }
                )

        self.store.save_wrong_records(wrong_records)
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
        StoryEngine(self.store).ensure_enriched(session_id)
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
        wrong_records = self.store.get_wrong_records()
        progress = self.store.get_word_progress()
        answer_map = {item.word.lower(): item for item in payload.answers}

        for graded in graded_items:
            word = graded["word"].lower()
            card = cards[word]
            result = GradeResult(**graded)
            results.append(result)

            correct = graded["spelling_correct"] and graded["meaning_correct"]
            record = progress.get(
                word,
                {
                    "word": card["word"],
                    "seen_count": 0,
                    "wrong_count": 0,
                    "correct_count": 0,
                    "mastery": 0.0,
                    "last_seen": None,
                },
            )
            record["seen_count"] = int(record["seen_count"]) + 1
            record["last_seen"] = now_iso()
            if correct:
                record["correct_count"] = int(record["correct_count"]) + 1
            else:
                record["wrong_count"] = int(record["wrong_count"]) + 1
                wrong_records.append(
                    {
                        "word": card["word"],
                        "session_id": session_id,
                        "stage": 4,
                        "user_answer": answer_map[word].spelling_answer,
                        "correct_answer": card["word"],
                        "error_type": "stage4",
                        "created_at": now_iso(),
                    }
                )
            seen_count = max(1, int(record["seen_count"]))
            record["mastery"] = round(int(record["correct_count"]) / seen_count, 2)
            progress[word] = record

        self.store.save_word_progress(progress)
        self.store.save_wrong_records(wrong_records)
        self.store.update_session(
            session_id,
            {
                "stage4_results": [item.model_dump() for item in results],
                "status": "done",
            },
        )
        return Stage4SubmitResponse(session_id=session_id, status="done", results=results)

    def list_wrong_records(self) -> list[WrongRecordOut]:
        records = self.store.get_wrong_records()
        return [WrongRecordOut(**record) for record in records]
