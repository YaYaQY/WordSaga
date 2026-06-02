import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from app.config import ENRICH_MAX_WORKERS, resolve_chapter_word_size
from app.schemas.story import StoryChapterOut, StoryPackageOut, WordOccurrence
from app.schemas.vocabulary import SelectedWord
from app.services.ai_client import chat_completion, iter_chat_completion, parse_json_response
from app.storage.protocol import Store

STORY_PREVIEW_SYSTEM = "你只输出严格 JSON，用于 WordSaga 快速剧情预览。"
STORY_ENRICH_SYSTEM = "你只输出严格 JSON，用于 WordSaga 剧情结构化补全。"
logger = logging.getLogger("wordsaga.story")


@dataclass
class PreviewChapter:
    title: str
    annotated_story_zh: str
    world_context: dict


@dataclass
class EnrichedChapter:
    summary: str
    full_story_en: str
    full_story_zh: str
    annotated_story_en: str
    occurrences: list[dict]
    world_context: dict


class StoryEngine:
    def __init__(self, store: Store):
        self.store = store

    def _split_words(self, words: list[SelectedWord]) -> list[list[SelectedWord]]:
        chunk_size = resolve_chapter_word_size(len(words))
        chunks: list[list[SelectedWord]] = []
        for index in range(0, len(words), chunk_size):
            chunks.append(words[index : index + chunk_size])
        return chunks

    def _word_payload(self, words: list[SelectedWord]) -> list[dict]:
        return [
            {"word": item.word, "meaning": item.meaning, "source": item.source}
            for item in words
        ]

    def _build_preview_prompt(
        self,
        words: list[SelectedWord],
        style: str,
        chapter_index: int,
        chapter_total: int,
        world_context: dict | None,
    ) -> str:
        context_text = json.dumps(world_context or {}, ensure_ascii=False)
        return (
            "为 WordSaga 生成一章沉浸式中文剧情预览，请严格遵守：\n"
            "\n"
            "【剧情要求】\n"
            "1. 微型剧情有开端、转折、收尾，画面感强，拒绝流水账。\n"
            "2. 目标词依托上下文可猜词义，不直白剧透释义。\n"
            "3. 完全原创，禁止影视/小说/游戏 IP。\n"
            "\n"
            "【annotated_story_zh 标注格式 · 必须严格遵守】\n"
            "正文为流畅中文叙事；每个目标英文单词必须以全角括号附在对应中文语段之后。\n"
            "固定格式：中文语段（英文单词）\n"
            "示例：他陷入两难处境（dilemma），靠着敏锐观察（perspective）找到了突破口。\n"
            "禁止：英文单词(中文释义)、中文(中文释义)、半角括号标注释义等其他格式。\n"
            "括号内只能是目标英文单词本身，必须与单词列表完全一致（大小写一致）。\n"
            "\n"
            "【输出 JSON】\n"
            "仅输出以下字段，无 Markdown、无多余说明：\n"
            "{\n"
            '  "title": "章节标题",\n'
            '  "annotated_story_zh": "按上述格式撰写的中文嵌词正文",\n'
            '  "world_context": {"setting":"场景","characters":["人物"],"last_event":"本章收尾"}\n'
            "}\n"
            f"风格：{style}\n"
            f"进度：{chapter_index}/{chapter_total}\n"
            f"世界观：{context_text}\n"
            f"本章目标单词：{json.dumps(self._word_payload(words), ensure_ascii=False)}"
        )

    def _build_enrich_prompt(
        self,
        words: list[SelectedWord],
        style: str,
        chapter_index: int,
        title: str,
        annotated_story_zh: str,
    ) -> str:
        return (
            "根据已有 annotated_story_zh 补全 WordSaga 结构化字段。\n"
            "annotated_story_zh 采用格式：中文语段（英文单词），括号内为目标英文词。\n"
            "要求：\n"
            "1. occurrences 必须覆盖本章全部目标词，含 word/pos/meaning/sentence_en/sentence_zh。\n"
            "2. sentence_zh 与剧情中文一致；sentence_en 含对应英文单词。\n"
            "3. full_story_zh 为去掉全角括号英文标注后的纯中文正文。\n"
            "4. full_story_en / annotated_story_en 为对应英文版本。\n"
            "5. 仅输出 JSON，无 Markdown。\n"
            "{\n"
            '  "summary": "章节摘要",\n'
            '  "full_story_en": "纯英文正文",\n'
            '  "full_story_zh": "纯中文正文",\n'
            '  "annotated_story_en": "英文带标注正文",\n'
            '  "occurrences": [\n'
            '    {"word":"investigate","pos":"v.","meaning":"调查",'
            '"sentence_en":"...","sentence_zh":"..."}\n'
            "  ],\n"
            '  "world_context": {"setting":"...","characters":[],"last_event":"..."}\n'
            "}\n"
            f"风格：{style}\n"
            f"章节：第 {chapter_index} 章 · {title}\n"
            f"已有剧情：{annotated_story_zh}\n"
            f"目标单词：{json.dumps(self._word_payload(words), ensure_ascii=False)}"
        )

    def _collect_stream_content(self, system: str, prompt: str, chapter_index: int):
        parts: list[str] = []
        for delta in iter_chat_completion(system, prompt):
            parts.append(delta)
            yield {"type": "delta", "chapter_index": chapter_index, "text": delta}
        content = "".join(parts)
        if not content.strip():
            logger.warning("第 %s 章流式正文为空，回退非流式", chapter_index)
            content = chat_completion(system, prompt, stream=False)
        return content

    def _parse_preview(self, content: str) -> PreviewChapter:
        data = parse_json_response(content)
        missing = [key for key in ("title", "annotated_story_zh", "world_context") if key not in data]
        if missing:
            raise RuntimeError(f"AI 预览输出缺少字段：{', '.join(missing)}")
        return PreviewChapter(
            title=data["title"],
            annotated_story_zh=data["annotated_story_zh"],
            world_context=data["world_context"],
        )

    def _parse_enrichment(self, content: str) -> EnrichedChapter:
        data = parse_json_response(content)
        required = [
            "summary",
            "full_story_en",
            "full_story_zh",
            "annotated_story_en",
            "occurrences",
            "world_context",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise RuntimeError(f"AI 补全输出缺少字段：{', '.join(missing)}")
        return EnrichedChapter(
            summary=data["summary"],
            full_story_en=data["full_story_en"],
            full_story_zh=data["full_story_zh"],
            annotated_story_en=data["annotated_story_en"],
            occurrences=data["occurrences"],
            world_context=data["world_context"],
        )

    def _preview_chapter_row(self, index: int, preview: PreviewChapter) -> dict:
        return {
            "chapter_index": index,
            "title": preview.title,
            "annotated_story_zh": preview.annotated_story_zh,
            "full_story_en": "",
            "occurrences": [],
            "enriched": False,
        }

    def _persist_preview_story(
        self,
        session_id: str,
        title: str,
        world_context: dict,
        chapter_rows: list[dict],
        *,
        final: bool,
    ):
        story = {
            "title": title,
            "summary": "",
            "world_context": world_context,
            "enrichment_status": "complete" if final and all(row.get("enriched") for row in chapter_rows) else "pending",
            "chapters": chapter_rows,
        }
        updates: dict = {"story": story}
        if final:
            updates["status"] = "stage1"
        self.store.update_session(session_id, updates)

    def iter_generate_for_session(self, session_id: str):
        session = self.store.get_session(session_id)
        if session["story"] is not None:
            raise RuntimeError(f"Session 已生成剧情：{session_id}")

        selected_words = [
            SelectedWord(
                word=row["word"],
                rank=None,
                frequency=0,
                level=session["level"],
                meaning=row["meaning"],
                source=row["source"],
            )
            for row in session["words"]
        ]

        chunks = self._split_words(selected_words)
        chapter_total = len(chunks)
        world_context: dict = {}
        chapter_rows: list[dict] = []
        story_title = ""

        logger.info(
            "开始快速预览 session=%s 词数=%s 章节=%s",
            session_id,
            len(selected_words),
            chapter_total,
        )
        yield {"type": "start", "chapter_total": chapter_total, "session_id": session_id}

        for index, chunk in enumerate(chunks, start=1):
            logger.info("预览第 %s/%s 章，词数=%s", index, chapter_total, len(chunk))
            yield {
                "type": "chapter_start",
                "chapter_index": index,
                "chapter_total": chapter_total,
            }
            prompt = self._build_preview_prompt(
                chunk, session["style"], index, chapter_total, world_context
            )
            preview_gen = self._collect_stream_content(STORY_PREVIEW_SYSTEM, prompt, index)
            raw_content = ""
            try:
                while True:
                    yield next(preview_gen)
            except StopIteration as stop:
                raw_content = stop.value or ""

            preview = self._parse_preview(raw_content)
            world_context = preview.world_context
            if index == 1:
                story_title = preview.title
            chapter_rows.append(self._preview_chapter_row(index, preview))
            self._persist_preview_story(
                session_id,
                story_title,
                world_context,
                chapter_rows,
                final=False,
            )
            logger.info("预览第 %s/%s 章完成：%s", index, chapter_total, preview.title)
            yield {
                "type": "chapter_done",
                "chapter_index": index,
                "chapter_total": chapter_total,
                "title": preview.title,
                "annotated_story_zh": preview.annotated_story_zh,
            }

        self._persist_preview_story(session_id, story_title, world_context, chapter_rows, final=True)
        logger.info("预览完成 session=%s，启动后台补全", session_id)
        self.start_enrichment_background(session_id)
        yield {"type": "done", "session_id": session_id}

    def _enrich_single_chapter(
        self,
        session: dict,
        index: int,
        chunk: list[SelectedWord],
        chapter_row: dict,
    ) -> tuple[int, dict]:
        prompt = self._build_enrich_prompt(
            chunk,
            session["style"],
            index,
            chapter_row["title"],
            chapter_row["annotated_story_zh"],
        )
        raw = chat_completion(STORY_ENRICH_SYSTEM, prompt, stream=False)
        enriched = self._parse_enrichment(raw)
        return index, {
            "summary": enriched.summary,
            "full_story_en": enriched.full_story_en,
            "full_story_zh": enriched.full_story_zh,
            "annotated_story_en": enriched.annotated_story_en,
            "occurrences": enriched.occurrences,
            "world_context": enriched.world_context,
            "enriched": True,
        }

    def enrich_story(self, session_id: str):
        session = self.store.get_session(session_id)
        story = session.get("story")
        if story is None:
            raise RuntimeError(f"Session 尚未生成剧情：{session_id}")
        if story.get("enrichment_status") == "complete":
            return

        self.store.update_session(
            session_id,
            {"story": {**story, "enrichment_status": "running"}},
        )

        selected_words = session["words"]
        chunks = self._split_words(
            [
                SelectedWord(
                    word=row["word"],
                    rank=None,
                    frequency=0,
                    level=session["level"],
                    meaning=row["meaning"],
                    source=row["source"],
                )
                for row in selected_words
            ]
        )
        pending: list[tuple[int, list[SelectedWord], dict]] = []
        for index, (chunk, chapter_row) in enumerate(zip(chunks, story["chapters"]), start=1):
            if chapter_row.get("enriched"):
                continue
            pending.append((index, chunk, chapter_row))

        enriched_by_index: dict[int, dict] = {}
        if pending:
            with ThreadPoolExecutor(max_workers=ENRICH_MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._enrich_single_chapter,
                        session,
                        index,
                        chunk,
                        chapter_row,
                    ): index
                    for index, chunk, chapter_row in pending
                }
                for future in as_completed(futures):
                    index, enriched_data = future.result()
                    enriched_by_index[index] = enriched_data
                    logger.info("补全第 %s/%s 章结构化数据", index, len(chunks))

        story = self.store.get_session(session_id)["story"]
        summary_parts: list[str] = []
        world_context = story.get("world_context") or {}
        for index, chapter_row in enumerate(story["chapters"], start=1):
            if index in enriched_by_index:
                chapter_row.update(enriched_by_index[index])
            if chapter_row.get("summary"):
                summary_parts.append(chapter_row["summary"])
            if chapter_row.get("world_context"):
                world_context = chapter_row["world_context"]

        story["chapters"] = story["chapters"][:]
        story["summary"] = " ".join(part for part in summary_parts if part)
        story["world_context"] = world_context
        story["enrichment_status"] = "complete"
        self.store.update_session(session_id, {"story": story})
        logger.info("补全完成 session=%s", session_id)

    def get_enrichment_status(self, session_id: str) -> dict:
        session = self.store.get_session(session_id)
        story = session.get("story")
        if story is None:
            raise RuntimeError(f"Session 尚未生成剧情：{session_id}")
        chapters = story.get("chapters") or []
        enriched_count = sum(1 for chapter in chapters if chapter.get("enriched"))
        return {
            "session_id": session_id,
            "status": story.get("enrichment_status"),
            "review_mode": bool(story.get("review_mode")),
            "chapter_total": len(chapters),
            "chapter_enriched": enriched_count,
        }

    def start_enrichment_background(self, session_id: str):
        thread = threading.Thread(
            target=self._enrich_story_safe,
            args=(session_id,),
            daemon=True,
        )
        thread.start()

    def _enrich_story_safe(self, session_id: str):
        self.enrich_story(session_id)

    def ensure_enriched(self, session_id: str):
        session = self.store.get_session(session_id)
        story = session.get("story")
        if story is None:
            raise RuntimeError("请先生成剧情")
        if story.get("review_mode"):
            return
        if story.get("enrichment_status") != "complete":
            self.enrich_story(session_id)

    def generate_for_session(self, session_id: str) -> StoryPackageOut:
        for event in self.iter_generate_for_session(session_id):
            if event["type"] == "done":
                break
        self.enrich_story(session_id)
        return self.get_story_package(session_id)

    def get_story_package(self, session_id: str) -> StoryPackageOut:
        session = self.store.get_session(session_id)
        story = session["story"]
        if story is None:
            raise RuntimeError(f"Session 尚未生成剧情：{session_id}")

        chapters = [
            StoryChapterOut(
                chapter_index=row["chapter_index"],
                full_story_en=row.get("full_story_en") or "",
                annotated_story_zh=row["annotated_story_zh"],
                occurrences=[WordOccurrence(**item) for item in row.get("occurrences") or []],
            )
            for row in story["chapters"]
        ]

        return StoryPackageOut(
            session_id=session_id,
            title=story["title"],
            summary=story.get("summary") or "",
            world_context=story.get("world_context") or {},
            chapters=chapters,
        )
