from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_store
from app.schemas.vocabulary import (
    DueWordOut,
    FrequencySelectRequest,
    ManualSelectRequest,
    ReviewDueResponse,
    SelectWordsResponse,
    WordMemoryBrief,
)
from app.services.vocabulary_engine import VocabularyEngine
from app.storage.protocol import Store

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


@router.get("/count")
def vocabulary_count(store: Store = Depends(get_store)):
    engine = VocabularyEngine(store)
    return {"count": engine.vocabulary_count(), "source": "cet_full_list.json"}


@router.get("/weak/count")
def weak_word_count(
    level: str = Query(default="basic"),
    store: Store = Depends(get_store),
):
    engine = VocabularyEngine(store)
    return {"level": level, "weak_count": engine.count_weak_words(level=level)}


@router.get("/review/due", response_model=ReviewDueResponse)
def list_due_words(
    level: str = Query(default="basic"),
    limit: int = Query(default=50, ge=1, le=300),
    store: Store = Depends(get_store),
):
    engine = VocabularyEngine(store)
    rows = engine.list_due_words(level=level, limit=limit)
    words = [
        DueWordOut(
            word=row["word"],
            rank=row["rank"],
            frequency=row["frequency"],
            level=row["level"],
            meaning=row["meaning"],
            memory=WordMemoryBrief(**row["memory"]),
        )
        for row in rows
    ]
    return ReviewDueResponse(
        level=level,
        due_count=engine.count_due_words(level=level),
        words=words,
    )


@router.post("/select/frequency", response_model=SelectWordsResponse)
def select_by_frequency(payload: FrequencySelectRequest, store: Store = Depends(get_store)):
    engine = VocabularyEngine(store)
    try:
        words = engine.select_by_frequency(payload.count, payload.level, payload.start_rank)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return SelectWordsResponse(words=words, level=payload.level, mode="frequency")


@router.post("/select/manual", response_model=SelectWordsResponse)
def select_manual(payload: ManualSelectRequest, store: Store = Depends(get_store)):
    engine = VocabularyEngine(store)
    try:
        words = engine.select_manual(payload.words)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return SelectWordsResponse(words=words, level="all", mode="manual")
