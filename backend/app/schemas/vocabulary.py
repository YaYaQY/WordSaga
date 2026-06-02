from pydantic import BaseModel, Field


class FrequencySelectRequest(BaseModel):
    mode: str = "frequency"
    level: str = "basic"
    count: int = Field(ge=1, le=300)
    start_rank: int | None = None


class ManualSelectRequest(BaseModel):
    mode: str = "manual"
    words: list[str] = Field(min_length=1)


class SelectedWord(BaseModel):
    word: str
    rank: int | None
    frequency: int
    level: str
    meaning: str
    source: str


class SelectWordsResponse(BaseModel):
    words: list[SelectedWord]
    level: str
    mode: str


class WordMemoryBrief(BaseModel):
    first_learned_at: str | None
    last_seen_at: str | None
    learn_count: int
    review_count: int
    correct_count: int
    wrong_count: int
    spelling_wrong_count: int
    meaning_wrong_count: int
    last_error_type: str | None
    is_leech: bool
    incomplete_due_at: str | None
    mastery: float
    repetitions: int
    interval_days: int
    ease_factor: float
    next_review_at: str | None
    status: str


class DueWordOut(BaseModel):
    word: str
    rank: int
    frequency: int
    level: str
    meaning: str
    memory: WordMemoryBrief


class ReviewDueResponse(BaseModel):
    level: str
    due_count: int
    words: list[DueWordOut]
