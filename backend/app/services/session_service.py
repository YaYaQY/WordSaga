import uuid

from app.schemas.session import (
    CreateSessionRequest,
    CreateSessionResponse,
    ResumableSessionOut,
    SessionOut,
    SessionWordOut,
    SkippedWordOut,
)
from app.schemas.vocabulary import SelectedWord
from app.services.review_story_builder import ReviewStoryBuilder
from app.services.vocabulary_engine import VocabularyEngine
from app.storage.protocol import Store
from app.storage.util import now_iso

STAGE_RESUMABLE = frozenset({"stage1", "stage2", "stage3", "stage4"})
RECALL_MODES = frozenset({"review", "weak"})


class SessionService:
    def __init__(self, store: Store):
        self.store = store
        self.vocabulary_engine = VocabularyEngine(store)

    def create_session(self, payload: CreateSessionRequest) -> CreateSessionResponse:
        if payload.mode == "frequency":
            if payload.count is None:
                raise RuntimeError("frequency 模式必须提供 count")
            words = self.vocabulary_engine.select_by_frequency(
                count=payload.count,
                level=payload.level,
                start_rank=payload.start_rank,
            )
            max_rank = max(item.rank for item in words if item.rank is not None)
            self.store.set_last_rank(max_rank)
            story = None
            status = "created"
            skipped_words: list[SkippedWordOut] = []
        elif payload.mode == "manual":
            if not payload.words:
                raise RuntimeError("manual 模式必须提供 words")
            words = self.vocabulary_engine.select_manual(payload.words)
            story = None
            status = "created"
            skipped_words = []
        elif payload.mode == "review":
            if payload.count is None:
                raise RuntimeError("review 模式必须提供 count")
            words = self.vocabulary_engine.select_due_review(
                count=payload.count,
                level=payload.level,
            )
            words, skipped_words, story, status = self._prepare_recall_session(words)
        elif payload.mode == "weak":
            if payload.count is None:
                raise RuntimeError("weak 模式必须提供 count")
            words = self.vocabulary_engine.select_weak_words(
                count=payload.count,
                level=payload.level,
            )
            words, skipped_words, story, status = self._prepare_recall_session(words)
        else:
            raise RuntimeError(f"未知 mode：{payload.mode}")

        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "mode": payload.mode,
            "level": payload.level,
            "style": payload.style,
            "enable_thinking": payload.enable_thinking,
            "word_count": len(words),
            "status": status,
            "created_at": now_iso(),
            "words": [
                {"word": item.word, "source": item.source, "meaning": item.meaning}
                for item in words
            ],
            "story": story,
        }
        self.store.save_session(session)
        return CreateSessionResponse(
            session=self.get_session(session_id),
            skipped_words=skipped_words,
        )

    def _prepare_recall_session(
        self, words: list[SelectedWord]
    ) -> tuple[list[SelectedWord], list[SkippedWordOut], dict, str]:
        session_words = [
            {"word": item.word, "source": item.source, "meaning": item.meaning}
            for item in words
        ]
        builder = ReviewStoryBuilder(self.store)
        ready_rows, skipped_rows = builder.partition_by_occurrences(session_words)
        if not ready_rows:
            raise RuntimeError("所选单词均缺少历史例句，请先完成新学。")

        ready_keys = {row["word"].lower() for row in ready_rows}
        ready_words = [item for item in words if item.word.lower() in ready_keys]
        story = builder.build_story_for_ready(ready_rows)
        skipped_words = [SkippedWordOut(**row) for row in skipped_rows]
        return ready_words, skipped_words, story, "stage3"

    def get_session(self, session_id: str) -> SessionOut:
        session = self.store.get_session(session_id)
        return SessionOut(
            id=session["id"],
            mode=session["mode"],
            level=session["level"],
            style=session["style"],
            word_count=session["word_count"],
            status=session["status"],
            words=[
                SessionWordOut(word=row["word"], source=row["source"], meaning=row["meaning"])
                for row in session["words"]
            ],
        )

    def _resume_kind(self, session: dict) -> str | None:
        status = session["status"]
        if status in STAGE_RESUMABLE:
            return "stage"
        if status != "created":
            return None
        if session.get("story") is not None:
            return "generating_interrupted"
        return "generating"

    def get_resumable(self) -> ResumableSessionOut | None:
        candidates: list[tuple[str, dict]] = []
        for session in self.store.get_sessions().values():
            kind = self._resume_kind(session)
            if kind is not None:
                candidates.append((kind, session))
        if not candidates:
            return None
        kind, session = max(candidates, key=lambda item: item[1]["created_at"])
        story = session.get("story")
        story_title = story["title"] if story is not None else None
        return ResumableSessionOut(
            id=session["id"],
            mode=session["mode"],
            level=session["level"],
            status=session["status"],
            word_count=session["word_count"],
            words=[
                SessionWordOut(word=row["word"], source=row["source"], meaning=row["meaning"])
                for row in session["words"]
            ],
            story_title=story_title,
            resume_kind=kind,
        )

    def reset_story(self, session_id: str) -> SessionOut:
        session = self.store.get_session(session_id)
        if session["status"] != "created":
            raise RuntimeError("仅生成阶段的 session 可重置故事")
        if session.get("story") is None:
            raise RuntimeError("当前 session 没有半成品故事")
        self.store.update_session(session_id, {"story": None})
        return self.get_session(session_id)

    def abandon_session(self, session_id: str) -> None:
        session = self.store.get_session(session_id)
        if session["status"] != "created":
            raise RuntimeError("仅生成阶段的 session 可放弃")
        self.store.delete_session(session_id)
