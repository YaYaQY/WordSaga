import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import APIConnectionError, APIError, AuthenticationError, OpenAI


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VOCAB_PATH = DATA_DIR / "cet_full_list.json"
PROGRESS_PATH = DATA_DIR / "progress.json"
SESSIONS_PATH = DATA_DIR / "sessions.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_env_file():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def read_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def normalize_word(word):
    return word.strip().lower()


def load_vocabulary():
    data = read_json(VOCAB_PATH, {})
    words = data.get("四六级词汇词频排序表")
    if not isinstance(words, list):
        raise RuntimeError(f"词库格式不正确：{VOCAB_PATH}")

    normalized = []
    for item in words:
        word = normalize_word(str(item.get("单词", "")))
        if not word:
            continue
        normalized.append(
            {
                "rank": item.get("序号"),
                "frequency": int(item.get("词频") or 0),
                "level": "cet6" if item.get("六级") == "★" else "basic",
                "word": word,
                "meaning": str(item.get("释义") or "").strip(),
                "alternate_spellings": item.get("其他拼写"),
            }
        )

    normalized.sort(key=lambda item: (item["rank"] is None, item["rank"] or 0))
    return normalized


def build_vocabulary_index(vocabulary):
    return {item["word"]: item for item in vocabulary}


def filter_vocabulary(vocabulary, level):
    if level == "basic":
        return [item for item in vocabulary if item["level"] == "basic"]
    if level == "cet6":
        return [item for item in vocabulary if item["level"] == "cet6"]
    return list(vocabulary)


def load_progress():
    return read_json(PROGRESS_PATH, {"version": 1, "words": {}})


def load_sessions():
    return read_json(SESSIONS_PATH, {"version": 1, "sessions": []})


def parse_seen_days(record):
    last_seen = record.get("last_seen")
    if not last_seen:
        return 9999
    try:
        previous = datetime.fromisoformat(last_seen)
    except ValueError:
        return 9999
    delta = datetime.now(timezone.utc) - previous
    return max(0, delta.days)


def plan_session_words(vocabulary, progress, count, level):
    filtered = filter_vocabulary(vocabulary, level)
    records = progress.get("words", {})

    review_candidates = []
    new_candidates = []
    for item in filtered:
        record = records.get(item["word"])
        if record:
            days = parse_seen_days(record)
            wrong_count = int(record.get("wrong_count") or 0)
            review_score = wrong_count * 100000 + days * 1000 + item["frequency"]
            if wrong_count > 0 or days >= 1:
                review_candidates.append((review_score, item))
        else:
            new_candidates.append(item)

    review_candidates.sort(key=lambda pair: pair[0], reverse=True)
    new_candidates.sort(key=lambda item: item["frequency"], reverse=True)

    review_count = min(len(review_candidates), count // 2)
    selected = [item for _, item in review_candidates[:review_count]]

    used_words = {item["word"] for item in selected}
    for item in new_candidates:
        if len(selected) >= count:
            break
        if item["word"] not in used_words:
            selected.append(item)
            used_words.add(item["word"])

    if len(selected) < count:
        for _, item in review_candidates[review_count:]:
            if len(selected) >= count:
                break
            if item["word"] not in used_words:
                selected.append(item)
                used_words.add(item["word"])

    return selected


def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def ask_int(prompt, default, minimum=1, maximum=20):
    while True:
        value = ask(prompt, str(default))
        try:
            number = int(value)
        except ValueError:
            print("请输入数字。")
            continue
        if minimum <= number <= maximum:
            return number
        print(f"请输入 {minimum} 到 {maximum} 之间的数字。")


def choose_level():
    print("\n词库范围")
    print("1. 四级/基础")
    print("2. 六级")
    print("3. 全部")
    choice = ask("请选择", "1")
    if choice == "2":
        return "cet6"
    if choice == "3":
        return "all"
    return "basic"


def parse_word_list(text):
    return [normalize_word(part) for part in re.split(r"[\s,，;；]+", text) if part.strip()]


def choose_words(vocabulary, progress):
    index = build_vocabulary_index(vocabulary)

    print("\n学习模式")
    print("1. 按词频计划自动学习")
    print("2. 从词库指定单词")
    print("3. 输入自定义单词")
    mode = ask("请选择", "1")

    level = choose_level()
    count = ask_int("本轮学习词数", 5, minimum=1, maximum=12)

    if mode == "2":
        raw = ask("请输入要学习的单词，用空格或逗号分隔")
        words = parse_word_list(raw)
        selected = []
        for word in words:
            item = index.get(word)
            if item:
                selected.append(item)
            else:
                print(f"词库未找到：{word}")
        return selected[:count], level, "selected"

    if mode == "3":
        raw = ask("请输入自定义单词，用空格或逗号分隔")
        selected = []
        for word in parse_word_list(raw):
            meaning = ask(f"请输入 {word} 的中文释义，可留空", "")
            selected.append(
                {
                    "rank": None,
                    "frequency": 0,
                    "level": "custom",
                    "word": word,
                    "meaning": meaning,
                    "alternate_spellings": None,
                }
            )
        return selected[:count], level, "custom"

    return plan_session_words(vocabulary, progress, count, level), level, "auto"


def create_ai_client():
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL")

    if not api_key or not model or "your_api" in api_key:
        raise RuntimeError(
            "缺少 AI 配置。请设置 OPENAI_API_KEY 和 OPENAI_MODEL；"
            "如使用兼容接口，也请设置 OPENAI_BASE_URL。"
        )

    return OpenAI(api_key=api_key, base_url=base_url), model


def require_ai_config():
    client, model = create_ai_client()
    return client, model


def build_story_prompt(words, style, difficulty, memory_level):
    word_payload = [
        {
            "word": item["word"],
            "meaning": item["meaning"],
            "frequency": item["frequency"],
            "level": item["level"],
        }
        for item in words
    ]

    return (
        "你是 WordSaga 的 Narrative Vocabulary Learning 引擎。\n"
        "请生成一段原创剧情化英语词汇学习内容。不要使用现成影视、小说或游戏的受版权保护角色。\n"
        "要求：\n"
        "1. 单词必须自然成为剧情事件的一部分，不要写成孤立例句。\n"
        "2. 剧情中文为主，目标英文单词嵌入句子中。\n"
        "3. story_with_meanings 必须包含每个目标词，格式为 word（中文释义）。\n"
        "4. 每个目标词至少出现一次，且含义要能从上下文推理出来。\n"
        "5. 输出必须是严格 JSON，不要 Markdown，不要代码块。\n"
        "JSON 结构：\n"
        "{\n"
        '  "title": "标题",\n'
        '  "summary": "一句话剧情摘要",\n'
        '  "story_with_meanings": "带 word（释义） 的剧情正文",\n'
        '  "embedded_words": [\n'
        '    {"word": "investigate", "meaning": "调查", "sentence": "含该词的剧情句", "clue": "帮助记忆的剧情线索"}\n'
        "  ],\n"
        '  "dialogue_questions": ["一个需要用目标词回答的剧情问题"]\n'
        "}\n"
        f"故事风格：{style}\n"
        f"难度：{difficulty}\n"
        f"记忆阶段：{memory_level}\n"
        f"目标词：{json.dumps(word_payload, ensure_ascii=False)}"
    )


def call_openai_compatible(prompt, stream=True):
    client, model = require_ai_config()
    messages = [
        {
            "role": "system",
            "content": "你只输出严格 JSON，用于命令行程序解析。",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        if stream:
            print("生成中：", end="", flush=True)
            content_parts = []
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.8,
                max_tokens=4096,
                stream=True,
            )
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    print(delta.content, end="", flush=True)
                    content_parts.append(delta.content)
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    print(reasoning, end="", flush=True)
                    content_parts.append(reasoning)
            print()
            content = "".join(content_parts)
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.8,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
    except AuthenticationError as error:
        raise RuntimeError(f"AI 认证失败，请检查 OPENAI_API_KEY：{error}") from error
    except APIConnectionError as error:
        raise RuntimeError(f"AI 接口连接失败，请检查 OPENAI_BASE_URL：{error}") from error
    except APIError as error:
        raise RuntimeError(f"AI 接口请求失败：{error}") from error

    if not content.strip():
        raise RuntimeError("AI 返回内容为空。")

    return parse_ai_json(content)


def parse_ai_json(content):
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"AI 输出不是严格 JSON：\n{content}") from error

    required = ["title", "summary", "story_with_meanings", "embedded_words"]
    missing = [key for key in required if key not in parsed]
    if missing:
        raise RuntimeError(f"AI 输出缺少字段：{', '.join(missing)}")

    return parsed


def mask_meanings(story, words):
    masked = story
    for item in words:
        word = re.escape(item["word"])
        masked = re.sub(rf"({word})（[^）]*）", r"\1（ ）", masked, flags=re.IGNORECASE)
    return masked


def print_words(words):
    for index, item in enumerate(words, start=1):
        meaning = item["meaning"] or "未提供释义"
        print(f"{index}. {item['word']} - {meaning}")


def run_recall_flow(story, words):
    print("\n========== Stage 1：语境学习 ==========")
    print(f"\n《{story['title']}》")
    print(story["story_with_meanings"])
    input("\n读完后按 Enter 进入 Stage 2。")

    print("\n========== Stage 2：隐藏中文释义 ==========")
    print(mask_meanings(story["story_with_meanings"], words))
    input("\n尝试回忆括号里的中文释义，完成后按 Enter 进入 Stage 3。")

    print("\n========== Stage 3：脱离剧情回忆 ==========")
    print("只看单词，回忆它们刚才在剧情里发生了什么。")
    for item in words:
        print(f"- {item['word']}")
    recalled_scene = ask("\n请用一句话写下你记住的剧情线索", "")

    print("\n========== Stage 4：拼写与释义输出 ==========")
    answers = []
    for item in words:
        print(f"\n目标释义：{item['meaning'] or '自定义词，按你刚才学习的含义作答'}")
        spelling = normalize_word(ask("请输入对应英文单词"))
        spelling_correct = spelling == item["word"]
        meaning_answer = ask("请输入你记住的中文释义", "")
        self_mark = ask("你认为释义答对了吗？y/n", "y").lower()
        meaning_correct = self_mark.startswith("y")
        answers.append(
            {
                "word": item["word"],
                "spelling_answer": spelling,
                "spelling_correct": spelling_correct,
                "meaning_answer": meaning_answer,
                "meaning_correct": meaning_correct,
            }
        )
        status = "正确" if spelling_correct and meaning_correct else "需要复习"
        print(f"结果：{status}")

    question_answers = []
    questions = story.get("dialogue_questions") or []
    if questions:
        print("\n========== Stage 5：剧情互动表达 ==========")
        for question in questions:
            print(f"\nAI 问题：{question}")
            question_answers.append({"question": question, "answer": ask("你的回答", "")})

    return {"recalled_scene": recalled_scene, "answers": answers, "dialogue": question_answers}


def update_progress(progress, words, story, recall_result):
    records = progress.setdefault("words", {})
    answer_map = {answer["word"]: answer for answer in recall_result["answers"]}
    timestamp = now_iso()

    for item in words:
        word = item["word"]
        answer = answer_map.get(word, {})
        correct = bool(answer.get("spelling_correct")) and bool(answer.get("meaning_correct"))
        record = records.setdefault(
            word,
            {
                "word": word,
                "meaning": item["meaning"],
                "level": item["level"],
                "frequency": item["frequency"],
                "seen_count": 0,
                "wrong_count": 0,
                "correct_count": 0,
                "mastery": 0.0,
                "related_stories": [],
            },
        )

        record["meaning"] = item["meaning"] or record.get("meaning", "")
        record["level"] = item["level"]
        record["frequency"] = item["frequency"]
        record["seen_count"] = int(record.get("seen_count") or 0) + 1
        record["last_seen"] = timestamp
        if correct:
            record["correct_count"] = int(record.get("correct_count") or 0) + 1
        else:
            record["wrong_count"] = int(record.get("wrong_count") or 0) + 1

        seen_count = max(1, int(record.get("seen_count") or 1))
        correct_count = int(record.get("correct_count") or 0)
        record["mastery"] = round(correct_count / seen_count, 2)

        related = record.setdefault("related_stories", [])
        related.append(
            {
                "title": story["title"],
                "summary": story["summary"],
                "seen_at": timestamp,
            }
        )
        record["related_stories"] = related[-5:]

    write_json(PROGRESS_PATH, progress)


def append_session(sessions, mode, level, words, story, recall_result):
    sessions.setdefault("sessions", []).append(
        {
            "created_at": now_iso(),
            "mode": mode,
            "level": level,
            "words": [item["word"] for item in words],
            "story": {
                "title": story["title"],
                "summary": story["summary"],
            },
            "recall": recall_result,
        }
    )
    sessions["sessions"] = sessions["sessions"][-100:]
    write_json(SESSIONS_PATH, sessions)


def main():
    print("WordSaga - AI 剧情化记忆学习系统")
    print("本地 MVP：词频计划 / 指定词 / 自定义词 + AI 剧情 + 主动回忆\n")

    vocabulary = load_vocabulary()
    progress = load_progress()
    sessions = load_sessions()

    print(f"已加载词库：{len(vocabulary)} 个词")
    words, level, mode = choose_words(vocabulary, progress)
    if not words:
        print("本轮没有可学习的单词。")
        return

    print("\n本轮单词：")
    print_words(words)

    style = ask("故事风格", "原创唐朝悬疑")
    difficulty = ask("难度", "CET4/CET6")
    memory_level = "first_time" if mode != "auto" else "planned_by_frequency"

    print("\n正在调用 AI 生成剧情...")
    prompt = build_story_prompt(words, style, difficulty, memory_level)
    story = call_openai_compatible(prompt)

    recall_result = run_recall_flow(story, words)
    update_progress(progress, words, story, recall_result)
    append_session(sessions, mode, level, words, story, recall_result)

    print("\n本轮学习已保存。")
    print(f"- 进度：{PROGRESS_PATH}")
    print(f"- 会话：{SESSIONS_PATH}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出。")
        sys.exit(130)
    except Exception as error:
        print(f"\n错误：{error}")
        sys.exit(1)
