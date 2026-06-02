from pydantic import BaseModel


class WordMemoryOut(BaseModel):
    word: str
    first_learned_at: str | None
    last_seen_at: str | None
    learn_count: int
    review_count: int
    correct_count: int
    wrong_count: int
    spelling_wrong_count: int
    meaning_wrong_count: int
    last_error_type: str | None
    last_prompt_type: str | None
    mastery: float
    repetitions: int
    interval_days: int
    ease_factor: float
    next_review_at: str | None
    incomplete_due_at: str | None
    last_sm2_at: str | None
    session_fail_streak: int
    is_leech: bool
    status: str


class WordLearningEventOut(BaseModel):
    id: str
    word: str
    session_id: str
    event_type: str
    stage: int
    result: str
    quality: int
    detail: dict
    occurred_at: str
