from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_store
from app.schemas.memory import WordLearningEventOut, WordMemoryOut
from app.services.memory_service import MemoryService
from app.storage.protocol import Store

router = APIRouter(prefix="/api/words", tags=["memory"])


@router.get("/{word}/memory", response_model=WordMemoryOut)
def get_word_memory(word: str, store: Store = Depends(get_store)):
    service = MemoryService(store)
    card = service.get_word_memory(word)
    if card is None:
        raise HTTPException(status_code=404, detail=f"尚无学习记录：{word}")
    return WordMemoryOut(**card)


@router.get("/{word}/events", response_model=list[WordLearningEventOut])
def get_word_events(word: str, store: Store = Depends(get_store)):
    service = MemoryService(store)
    events = service.list_word_events(word)
    if not events:
        raise HTTPException(status_code=404, detail=f"尚无学习事件：{word}")
    return [WordLearningEventOut(**event) for event in events]
