import json
import logging
import re
from collections.abc import Iterator
from typing import Literal

from app.config import build_thinking_extra_body, get_ai_client

PREVIEW_MAX_TOKENS = 2048
DEFAULT_MAX_TOKENS = 8192

logger = logging.getLogger("wordsaga.ai")

StreamPartKind = Literal["content", "thinking"]


def _message_payload(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _log_ai_request(
    model: str, system: str, user: str, *, stream: bool, enable_thinking: bool
) -> None:
    logger.info(
        "AI 请求 model=%s stream=%s thinking=%s\n--- system ---\n%s\n--- user ---\n%s",
        model,
        stream,
        enable_thinking,
        system,
        user,
    )


def _log_ai_response(model: str, content: str, *, stream: bool) -> None:
    logger.info(
        "AI 响应 model=%s stream=%s len=%d\n--- content ---\n%s",
        model,
        stream,
        len(content),
        content,
    )


def _completion_kwargs(max_tokens: int, *, enable_thinking: bool) -> dict:
    return {
        "temperature": 0.8,
        "max_tokens": max_tokens,
        "extra_body": build_thinking_extra_body(enable_thinking),
    }


def iter_chat_completion_parts(
    system: str,
    user: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    enable_thinking: bool = False,
) -> Iterator[tuple[StreamPartKind, str]]:
    """yield (kind, text)；thinking 为 reasoning_content，不写入故事 JSON。"""
    client, model = get_ai_client()
    _log_ai_request(model, system, user, stream=True, enable_thinking=enable_thinking)
    response = client.chat.completions.create(
        model=model,
        messages=_message_payload(system, user),
        stream=True,
        **_completion_kwargs(max_tokens, enable_thinking=enable_thinking),
    )
    content_parts: list[str] = []
    for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            content_parts.append(delta.content)
            yield ("content", delta.content)
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield ("thinking", reasoning)
    _log_ai_response(model, "".join(content_parts), stream=True)


def iter_chat_completion(
    system: str,
    user: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    enable_thinking: bool = False,
) -> Iterator[str]:
    for kind, piece in iter_chat_completion_parts(
        system, user, max_tokens=max_tokens, enable_thinking=enable_thinking
    ):
        if kind == "content":
            yield piece


def chat_completion(
    system: str,
    user: str,
    stream: bool = False,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    enable_thinking: bool = False,
) -> str:
    if stream:
        return collect_chat_content(
            system, user, max_tokens=max_tokens, enable_thinking=enable_thinking
        )

    client, model = get_ai_client()
    _log_ai_request(model, system, user, stream=False, enable_thinking=enable_thinking)
    response = client.chat.completions.create(
        model=model,
        messages=_message_payload(system, user),
        **_completion_kwargs(max_tokens, enable_thinking=enable_thinking),
    )
    message = response.choices[0].message
    content = message.content or ""
    if not content.strip():
        reasoning = getattr(message, "reasoning_content", None)
        content = reasoning or ""
    _log_ai_response(model, content, stream=False)
    return content


def collect_chat_content(
    system: str,
    user: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    enable_thinking: bool = False,
) -> str:
    parts = list(
        iter_chat_completion(
            system, user, max_tokens=max_tokens, enable_thinking=enable_thinking
        )
    )
    content = "".join(parts)
    if content.strip():
        return content
    logger.warning("流式响应正文为空，回退非流式请求")
    return chat_completion(
        system, user, stream=False, max_tokens=max_tokens, enable_thinking=enable_thinking
    )


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
