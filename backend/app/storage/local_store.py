import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"
WORD_MEMORY_PATH = DATA_DIR / "word_memory.json"
WORD_EVENTS_PATH = DATA_DIR / "word_events.json"
LEARNING_DATA_PATH = DATA_DIR / "learning_data.json"


class LocalStore:
    """本地 JSON 文件存储，实现 Store 协议。"""

    def _read(self, path: Path, default: dict) -> dict:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)

    def get_last_rank(self) -> int:
        data = self._read(SETTINGS_PATH, {"last_learned_rank": 0})
        return int(data["last_learned_rank"])

    def set_last_rank(self, rank: int):
        self._write(SETTINGS_PATH, {"last_learned_rank": rank})

    def get_word_memory(self) -> dict[str, dict]:
        data = self._read(WORD_MEMORY_PATH, {"words": {}})
        return data["words"]

    def save_word_memory(self, words: dict[str, dict]):
        self._write(WORD_MEMORY_PATH, {"words": words})

    def get_word_events(self) -> list[dict]:
        data = self._read(WORD_EVENTS_PATH, {"events": []})
        return data["events"]

    def append_word_events(self, events: list[dict]):
        existing = self.get_word_events()
        existing.extend(events)
        self._write(WORD_EVENTS_PATH, {"events": existing})

    def get_sessions(self) -> dict[str, dict]:
        data = self._read(LEARNING_DATA_PATH, {"sessions": {}})
        return data["sessions"]

    def get_session(self, session_id: str) -> dict:
        sessions = self.get_sessions()
        if session_id not in sessions:
            raise RuntimeError(f"Session 不存在：{session_id}")
        return sessions[session_id]

    def save_session(self, session: dict):
        sessions = self.get_sessions()
        sessions[session["id"]] = session
        self._write(LEARNING_DATA_PATH, {"sessions": sessions})

    def update_session(self, session_id: str, updates: dict[str, Any]):
        session = self.get_session(session_id)
        session.update(updates)
        self.save_session(session)

    def delete_session(self, session_id: str):
        sessions = self.get_sessions()
        if session_id not in sessions:
            raise RuntimeError(f"Session 不存在：{session_id}")
        del sessions[session_id]
        self._write(LEARNING_DATA_PATH, {"sessions": sessions})
