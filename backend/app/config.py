import os
from pathlib import Path

from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "wordsaga.db"
VOCAB_JSON_PATH = DATA_DIR / "cet_full_list.json"
ENV_PATH = ROOT_DIR / ".env"

ENRICH_MAX_WORKERS = 3


def resolve_chapter_word_size(word_count: int) -> int:
    if word_count <= 10:
        return word_count
    if word_count <= 30:
        return (word_count + 1) // 2
    return 20


def load_env():
    if not ENV_PATH.exists():
        raise RuntimeError(f"缺少配置文件：{ENV_PATH}")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_ai_client() -> tuple[OpenAI, str]:
    load_env()
    api_key = os.environ["OPENAI_API_KEY"]
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise RuntimeError(
            f"OPENAI_BASE_URL 必须以 http:// 或 https:// 开头，当前为：{base_url!r}"
        )
    model = os.environ["OPENAI_MODEL"]
    return OpenAI(api_key=api_key, base_url=base_url), model


def build_thinking_extra_body(enable_thinking: bool) -> dict:
    return {"thinking": {"type": "enabled" if enable_thinking else "disabled"}}
