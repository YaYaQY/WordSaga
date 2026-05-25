import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import get_store
from app.schemas.session import CreateSessionRequest, SessionOut
from app.schemas.story import StoryPackageOut
from app.services.session_service import SessionService
from app.services.story_engine import StoryEngine
from app.storage.protocol import Store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _pull_stream_event(generator):
    try:
        return next(generator)
    except StopIteration:
        return None


@router.post("", response_model=SessionOut)
def create_session(payload: CreateSessionRequest, store: Store = Depends(get_store)):
    service = SessionService(store)
    try:
        return service.create_session(payload)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, store: Store = Depends(get_store)):
    service = SessionService(store)
    try:
        return service.get_session(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{session_id}/generate", response_model=StoryPackageOut)
def generate_story(session_id: str, store: Store = Depends(get_store)):
    engine = StoryEngine(store)
    try:
        return engine.generate_for_session(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{session_id}/generate/stream")
async def generate_story_stream(session_id: str, store: Store = Depends(get_store)):
    engine = StoryEngine(store)

    async def event_stream():
        generator = engine.iter_generate_for_session(session_id)
        loop = asyncio.get_running_loop()
        while True:
            try:
                event = await loop.run_in_executor(None, _pull_stream_event, generator)
            except RuntimeError as error:
                payload = json.dumps({"type": "error", "message": str(error)}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                break
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}/story", response_model=StoryPackageOut)
def get_story(session_id: str, store: Store = Depends(get_store)):
    engine = StoryEngine(store)
    try:
        return engine.get_story_package(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
