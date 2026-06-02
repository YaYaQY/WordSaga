import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import memory, sessions, stages, vocabulary, wrong_book
from app.deps import get_store
from app.services.vocabulary_engine import VocabularyEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    VocabularyEngine(get_store())
    logging.getLogger("wordsaga").info("词库已预加载")
    yield


app = FastAPI(title="WordSaga API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vocabulary.router)
app.include_router(sessions.router)
app.include_router(stages.router)
app.include_router(memory.router)
app.include_router(wrong_book.router)


@app.get("/health")
def health():
    return {"status": "ok", "storage": "local-json"}


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
