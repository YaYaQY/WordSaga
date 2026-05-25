import json
import logging
import re
from collections.abc import Iterator

from app.config import get_ai_client

logger = logging.getLogger("wordsaga.ai")


def _message_payload(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def iter_chat_completion(system: str, user: str) -> Iterator[str]:
    """仅 yield 正文 content，不包含 reasoning，避免污染 JSON 输出。"""
    client, model = get_ai_client()
    response = client.chat.completions.create(
        model=model,
        messages=_message_payload(system, user),
        temperature=0.8,
        max_tokens=8192,
        stream=True,
    )
    for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def chat_completion(system: str, user: str, stream: bool = False) -> str:
    if stream:
        return collect_chat_content(system, user)

    client, model = get_ai_client()
    response = client.chat.completions.create(
        model=model,
        messages=_message_payload(system, user),
        temperature=0.8,
        max_tokens=8192,
    )
    message = response.choices[0].message
    content = message.content or ""
    if content.strip():
        return content
    reasoning = getattr(message, "reasoning_content", None)
    return reasoning or ""


def collect_chat_content(system: str, user: str) -> str:
    parts = list(iter_chat_completion(system, user))
    content = "".join(parts)
    if content.strip():
        return content
    logger.warning("流式响应正文为空，回退非流式请求")
    return chat_completion(system, user, stream=False)


def parse_json_response(content: str) -> dict:
    stripped = content.strip()
    if not stripped:
        raise RuntimeError("AI 返回内容为空，请检查模型配置或稍后重试")

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        preview = stripped[:240].replace("\n", " ")
        raise RuntimeError(f"AI 返回不是有效 JSON：{preview}")
