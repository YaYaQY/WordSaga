from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_store
from app.schemas.vocabulary import FrequencySelectRequest, ManualSelectRequest, SelectWordsResponse
from app.services.vocabulary_engine import VocabularyEngine
from app.storage.protocol import Store

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


@router.get("/count")
def vocabulary_count(store: Store = Depends(get_store)):
    engine = VocabularyEngine(store)
    return {"count": engine.vocabulary_count(), "source": "cet_full_list.json"}


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
