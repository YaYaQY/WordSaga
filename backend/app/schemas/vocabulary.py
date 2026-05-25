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
