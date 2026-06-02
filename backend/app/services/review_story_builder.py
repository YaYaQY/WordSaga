from app.storage.protocol import Store


class ReviewStoryBuilder:
    def __init__(self, store: Store):
        self.store = store

    def build_story(self, session_words: list[dict]) -> dict:
        target_words = {row["word"].lower() for row in session_words}
        occurrences = self._collect_occurrences(target_words, session_words)

        return {
            "title": "单词复习",
            "summary": "到期复习，复用历史剧情例句。",
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
                    "occurrences": list(occurrences.values()),
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

        missing = target_words - found.keys()
        if missing:
            words = ", ".join(sorted(missing))
            raise RuntimeError(f"复习词缺少历史例句，请先完成新学 session：{words}")

        ordered: dict[str, dict] = {}
        for row in session_words:
            ordered[row["word"].lower()] = found[row["word"].lower()]
        return ordered
