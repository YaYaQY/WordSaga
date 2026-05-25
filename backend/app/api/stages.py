from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_store
from app.schemas.stage import (
    Stage1Out,
    Stage2Out,
    Stage2SubmitRequest,
    Stage3Out,
    Stage3SubmitRequest,
    Stage3SubmitResponse,
    Stage4Out,
    Stage4SubmitRequest,
    Stage4SubmitResponse,
)
from app.services.stage_controller import StageController
from app.storage.protocol import Store

router = APIRouter(prefix="/api/sessions", tags=["stages"])


@router.get("/{session_id}/stage/1", response_model=Stage1Out)
def get_stage1(session_id: str, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.get_stage1(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{session_id}/stage/1/complete", response_model=Stage1Out)
def complete_stage1(session_id: str, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.complete_stage1(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{session_id}/stage/2", response_model=Stage2Out)
def get_stage2(session_id: str, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.get_stage2(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{session_id}/stage/2/submit", response_model=Stage2Out)
def submit_stage2(session_id: str, payload: Stage2SubmitRequest, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.submit_stage2(session_id, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{session_id}/stage/3", response_model=Stage3Out)
def get_stage3(session_id: str, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.get_stage3(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{session_id}/stage/3/submit", response_model=Stage3SubmitResponse)
def submit_stage3(session_id: str, payload: Stage3SubmitRequest, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.submit_stage3(session_id, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{session_id}/stage/4", response_model=Stage4Out)
def get_stage4(session_id: str, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.get_stage4(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{session_id}/stage/4/submit", response_model=Stage4SubmitResponse)
def submit_stage4(session_id: str, payload: Stage4SubmitRequest, store: Store = Depends(get_store)):
    controller = StageController(store)
    try:
        return controller.submit_stage4(session_id, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
