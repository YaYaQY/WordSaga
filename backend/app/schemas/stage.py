from pydantic import BaseModel


class Stage1Out(BaseModel):
    session_id: str
    status: str
    title: str
    summary: str
    chapters: list[dict]


class Stage2Out(BaseModel):
    session_id: str
    status: str
    chapters: list[dict]
    words: list[str]


class Stage2Answer(BaseModel):
    word: str
    meaning_answer: str = ""
    skipped: bool = False


class Stage2SubmitRequest(BaseModel):
    answers: list[Stage2Answer]


class WordCard(BaseModel):
    word: str
    pos: str
    meaning: str
    sentence_en: str
    sentence_en_highlighted: str
    sentence_zh: str
    next_review_at: str | None
    incomplete_due_at: str | None
    mastery: float
    is_leech: bool


class Stage3Out(BaseModel):
    session_id: str
    status: str
    cards: list[WordCard]


class Stage3Answer(BaseModel):
    word: str
    spelling_answer: str
    meaning_answer: str
    sentence_answer: str = ""


class Stage3SubmitRequest(BaseModel):
    answers: list[Stage3Answer]


class GradeResult(BaseModel):
    word: str
    spelling_correct: bool
    meaning_correct: bool
    sentence_correct: bool
    errors: list[str]
    suggestions: list[str]


class Stage3SubmitResponse(BaseModel):
    session_id: str
    status: str
    results: list[GradeResult]


class Stage4Out(BaseModel):
    session_id: str
    status: str
    words: list[str]


class Stage4Answer(BaseModel):
    word: str
    spelling_answer: str
    meaning_answer: str


class Stage4SubmitRequest(BaseModel):
    answers: list[Stage4Answer]


class WordSessionSummary(BaseModel):
    word: str
    session_correct: bool
    next_review_at: str | None
    interval_days: int
    mastery: float
    is_leech: bool
    same_day_sm2_blocked: bool


class Stage4SubmitResponse(BaseModel):
    session_id: str
    status: str
    results: list[GradeResult]
    word_summaries: list[WordSessionSummary]


class WrongRecordOut(BaseModel):
    word: str
    session_id: str
    stage: int
    user_answer: str
    correct_answer: str
    error_type: str
    created_at: str
