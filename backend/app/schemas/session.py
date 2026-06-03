from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    mode: str
    level: str = "basic"
    style: str = "原创唐朝悬疑"
    enable_thinking: bool = False
    count: int | None = Field(default=None, ge=1, le=300)
    start_rank: int | None = None
    words: list[str] | None = None


class SessionWordOut(BaseModel):
    word: str
    source: str
    meaning: str


class SessionOut(BaseModel):
    id: str
    mode: str
    level: str
    style: str
    word_count: int
    status: str
    words: list[SessionWordOut]


class SkippedWordOut(BaseModel):
    word: str
    reason: str


class CreateSessionResponse(BaseModel):
    session: SessionOut
    skipped_words: list[SkippedWordOut]


class ResumableSessionOut(BaseModel):
    id: str
    mode: str
    level: str
    status: str
    word_count: int
    words: list[SessionWordOut]
    story_title: str | None
    resume_kind: str
