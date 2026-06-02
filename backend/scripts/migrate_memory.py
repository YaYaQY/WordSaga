"""一次性导入旧数据，并补全 word_memory 完整字段。

用法：
    cd backend
    python scripts/migrate_memory.py
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
WORD_PROGRESS_PATH = DATA_DIR / "word_progress.json"
WRONG_RECORDS_PATH = DATA_DIR / "wrong_records.json"
WORD_MEMORY_PATH = DATA_DIR / "word_memory.json"
WORD_EVENTS_PATH = DATA_DIR / "word_events.json"

FULL_CARD_TEMPLATE = {
    "first_learned_at": None,
    "last_seen_at": None,
    "learn_count": 0,
    "review_count": 0,
    "correct_count": 0,
    "wrong_count": 0,
    "spelling_wrong_count": 0,
    "meaning_wrong_count": 0,
    "last_error_type": None,
    "last_prompt_type": None,
    "mastery": 0.0,
    "repetitions": 0,
    "interval_days": 0,
    "ease_factor": 2.5,
    "next_review_at": None,
    "incomplete_due_at": None,
    "last_sm2_at": None,
    "session_fail_streak": 0,
    "is_leech": False,
    "status": "new",
}


def normalize_card(word: str, partial: dict) -> dict:
    card = {"word": word, **FULL_CARD_TEMPLATE, **partial}
    missing = [key for key in {**FULL_CARD_TEMPLATE, "word": word} if key not in card]
    if missing:
        raise RuntimeError(f"normalize 后仍缺字段 {word}：{', '.join(missing)}")
    return card


def main():
    memory = {"words": {}}
    if WORD_MEMORY_PATH.exists():
        raw = json.loads(WORD_MEMORY_PATH.read_text(encoding="utf-8"))["words"]
        for word, record in raw.items():
            memory["words"][word] = normalize_card(record["word"], record)

    if WORD_PROGRESS_PATH.exists():
        progress = json.loads(WORD_PROGRESS_PATH.read_text(encoding="utf-8"))["words"]
        for word, record in progress.items():
            key = word.lower()
            if key in memory["words"]:
                continue
            memory["words"][key] = normalize_card(
                record["word"],
                {
                    "first_learned_at": record["last_seen"],
                    "last_seen_at": record["last_seen"],
                    "learn_count": 1 if record["seen_count"] > 0 else 0,
                    "review_count": record["seen_count"],
                    "correct_count": record["correct_count"],
                    "wrong_count": record["wrong_count"],
                    "mastery": record["mastery"],
                    "interval_days": 1,
                    "next_review_at": record["last_seen"],
                    "status": "review" if record["seen_count"] > 0 else "new",
                },
            )

    events = {"events": []}
    if WORD_EVENTS_PATH.exists():
        events = json.loads(WORD_EVENTS_PATH.read_text(encoding="utf-8"))

    existing_event_ids = {event["id"] for event in events["events"]}
    if WRONG_RECORDS_PATH.exists():
        wrong_records = json.loads(WRONG_RECORDS_PATH.read_text(encoding="utf-8"))["records"]
        for index, record in enumerate(wrong_records):
            event_id = f"legacy-wrong-{index}"
            if event_id in existing_event_ids:
                continue
            events["events"].append(
                {
                    "id": event_id,
                    "word": record["word"],
                    "session_id": record["session_id"],
                    "event_type": "stage_submit",
                    "stage": record["stage"],
                    "result": "wrong",
                    "quality": 1,
                    "detail": {
                        "user_answer": record["user_answer"],
                        "correct_answer": record["correct_answer"],
                    },
                    "occurred_at": record["created_at"],
                }
            )

    WORD_MEMORY_PATH.write_text(json.dumps({"words": memory["words"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    WORD_EVENTS_PATH.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"memory={len(memory['words'])} events={len(events['events'])}")


if __name__ == "__main__":
    main()
