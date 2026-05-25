from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    mode: str
    level: str = "basic"
    style: str = "原创唐朝悬疑"
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
