from fastapi import APIRouter, Depends

from app.deps import get_store
from app.schemas.stage import WrongRecordOut
from app.services.stage_controller import StageController
from app.storage.protocol import Store

router = APIRouter(prefix="/api", tags=["wrong-book"])


@router.get("/wrong-book", response_model=list[WrongRecordOut])
def get_wrong_book(store: Store = Depends(get_store)):
    controller = StageController(store)
    return controller.list_wrong_records()
