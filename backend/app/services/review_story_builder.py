from app.storage.protocol import Store

SKIP_REASON_NO_OCCURRENCE = "缺少历史例句，请先完成新学"


class ReviewStoryBuilder:
    def __init__(self, store: Store):
        self.store = store

    def partition_by_occurrences(
        self, session_words: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        found = self._collect_occurrences(
            {row["word"].lower() for row in session_words},
            session_words,
        )
        ready: list[dict] = []
        skipped: list[dict] = []
        for row in session_words:
            key = row["word"].lower()
            if key in found:
                ready.append(row)
            else:
                skipped.append({"word": row["word"], "reason": SKIP_REASON_NO_OCCURRENCE})
        return ready, skipped

    def build_story(self, session_words: list[dict]) -> dict:
        ready, skipped = self.partition_by_occurrences(session_words)
        if skipped:
            words = ", ".join(item["word"] for item in skipped)
            raise RuntimeError(f"复习词缺少历史例句，请先完成新学 session：{words}")
        return self._assemble_story(session_words, self._collect_occurrences(
            {row["word"].lower() for row in session_words},
            session_words,
        ))

    def build_story_for_ready(self, session_words: list[dict]) -> dict:
        occurrences = self._collect_occurrences(
            {row["word"].lower() for row in session_words},
            session_words,
        )
        missing = {row["word"].lower() for row in session_words} - occurrences.keys()
        if missing:
            words = ", ".join(sorted(missing))
            raise RuntimeError(f"内部错误：ready 词仍缺少例句：{words}")
        return self._assemble_story(session_words, occurrences)

    def _assemble_story(self, session_words: list[dict], occurrences: dict[str, dict]) -> dict:
        ordered = [occurrences[row["word"].lower()] for row in session_words]
        return {
            "title": "单词复习",
            "summary": "复用历史剧情例句，巩固记忆。",
            "world_context": {},
            "enrichment_status": "complete",
            "review_mode": True,
            "chapters": [
                {
                    "chapter_index": 1,
                    "title": "复习",
                    "annotated_story_zh": "",
                    "full_story_en": "",
                    "full_story_zh": "",
                    "annotated_story_en": "",
                    "summary": "",
                    "occurrences": ordered,
                    "world_context": {},
                    "enriched": True,
                }
            ],
        }

    def _collect_occurrences(
        self,
        target_words: set[str],
        session_words: list[dict],
    ) -> dict[str, dict]:
        found: dict[str, dict] = {}
        sessions = sorted(
            self.store.get_sessions().values(),
            key=lambda item: item["created_at"],
            reverse=True,
        )

        for session in sessions:
            story = session.get("story")
            if story is None or story.get("review_mode"):
                continue
            if story.get("enrichment_status") != "complete":
                continue
            for chapter in story.get("chapters") or []:
                for occurrence in chapter.get("occurrences") or []:
                    word_key = occurrence["word"].lower()
                    if word_key in target_words and word_key not in found:
                        found[word_key] = occurrence
            if len(found) == len(target_words):
                break

        return found
