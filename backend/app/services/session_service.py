import uuid

from app.schemas.session import CreateSessionRequest, SessionOut, SessionWordOut
from app.services.vocabulary_engine import VocabularyEngine
from app.storage.protocol import Store
from app.storage.util import now_iso


class SessionService:
    def __init__(self, store: Store):
        self.store = store
        self.vocabulary_engine = VocabularyEngine(store)

    def create_session(self, payload: CreateSessionRequest) -> SessionOut:
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
        elif payload.mode == "manual":
            if not payload.words:
                raise RuntimeError("manual 模式必须提供 words")
            words = self.vocabulary_engine.select_manual(payload.words)
        else:
            raise RuntimeError(f"未知 mode：{payload.mode}")

        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "mode": payload.mode,
            "level": payload.level,
            "style": payload.style,
            "word_count": len(words),
            "status": "created",
            "created_at": now_iso(),
            "words": [
                {"word": item.word, "source": item.source, "meaning": item.meaning}
                for item in words
            ],
            "story": None,
        }
        self.store.save_session(session)
        return self.get_session(session_id)

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
