from pydantic import BaseModel


class WordOccurrence(BaseModel):
    word: str
    pos: str
    meaning: str
    sentence_en: str
    sentence_zh: str


class StoryChapterOut(BaseModel):
    chapter_index: int
    full_story_en: str
    annotated_story_zh: str
    occurrences: list[WordOccurrence]


class StoryPackageOut(BaseModel):
    session_id: str
    title: str
    summary: str
    world_context: dict
    chapters: list[StoryChapterOut]


class StoryEnrichmentOut(BaseModel):
    session_id: str
    status: str | None
    review_mode: bool
    chapter_total: int
    chapter_enriched: int
