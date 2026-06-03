import unittest

from app.services.memory_service import MemoryService


class MemoryStoreStub:
    def __init__(self):
        self.memory: dict[str, dict] = {}
        self.events: list[dict] = []
        self.sessions: dict[str, dict] = {}

    def get_word_memory(self):
        return self.memory

    def save_word_memory(self, words):
        self.memory = words

    def get_word_events(self):
        return self.events

    def append_word_events(self, items):
        self.events.extend(items)

    def get_session(self, session_id: str):
        return self.sessions[session_id]

    def save_session(self, session: dict):
        self.sessions[session["id"]] = session


class MemoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStoreStub()
        self.service = MemoryService(self.store)
        self.store.sessions["s1"] = {
            "id": "s1",
            "words": [{"word": "alpha", "source": "new", "meaning": "甲"}],
        }

    def _full_session_correct(self, word="alpha", meaning="甲"):
        self.service.record_stage2_submit(
            "s1",
            [
                {
                    "word": word,
                    "meaning_answer": meaning,
                    "expected_meaning": meaning,
                    "skipped": False,
                    "meaning_correct": True,
                }
            ],
        )
        self.service.record_stage3_submit(
            "s1",
            [
                {
                    "word": word,
                    "spelling_correct": True,
                    "meaning_correct": True,
                    "sentence_correct": True,
                }
            ],
            {word: {"spelling_answer": word, "meaning_answer": meaning, "sentence_answer": ""}},
        )
        self.service.record_stage4_submit(
            "s1",
            [{"word": word, "spelling_correct": True, "meaning_correct": True}],
            {word: {"spelling_answer": word, "meaning_answer": meaning}},
        )

    def test_stage1_sets_incomplete_due(self):
        self.service.record_stage1_complete("s1", ["alpha"])
        card = self.store.memory["alpha"]
        self.assertIsNotNone(card["incomplete_due_at"])
        self.assertIsNone(card["next_review_at"])

    def test_sm2_updates_once_at_stage4(self):
        self._full_session_correct()
        card = self.store.memory["alpha"]
        self.assertEqual(card["review_count"], 1)
        self.assertEqual(card["repetitions"], 1)
        self.assertIsNotNone(card["next_review_at"])
        self.assertIsNone(card["incomplete_due_at"])

    def test_stage2_miss_marks_session_wrong(self):
        self.service.record_stage2_submit(
            "s1",
            [
                {
                    "word": "alpha",
                    "meaning_answer": "错",
                    "expected_meaning": "甲",
                    "skipped": False,
                    "meaning_correct": False,
                }
            ],
        )
        self.service.record_stage3_submit(
            "s1",
            [
                {
                    "word": "alpha",
                    "spelling_correct": True,
                    "meaning_correct": True,
                    "sentence_correct": True,
                }
            ],
            {"alpha": {"spelling_answer": "alpha", "meaning_answer": "甲", "sentence_answer": ""}},
        )
        self.service.record_stage4_submit(
            "s1",
            [{"word": "alpha", "spelling_correct": True, "meaning_correct": True}],
            {"alpha": {"spelling_answer": "alpha", "meaning_answer": "甲"}},
        )
        card = self.store.memory["alpha"]
        self.assertEqual(card["wrong_count"], 1)
        self.assertEqual(card["correct_count"], 0)
        self.assertEqual(card["meaning_wrong_count"], 1)

    def test_skip_forces_session_wrong(self):
        self.service.record_stage2_submit(
            "s1",
            [
                {
                    "word": "alpha",
                    "meaning_answer": "",
                    "expected_meaning": "甲",
                    "skipped": True,
                    "meaning_correct": False,
                }
            ],
        )
        self.service.record_stage3_submit(
            "s1",
            [
                {
                    "word": "alpha",
                    "spelling_correct": True,
                    "meaning_correct": True,
                    "sentence_correct": True,
                }
            ],
            {"alpha": {"spelling_answer": "alpha", "meaning_answer": "甲", "sentence_answer": ""}},
        )
        self.service.record_stage4_submit(
            "s1",
            [{"word": "alpha", "spelling_correct": True, "meaning_correct": True}],
            {"alpha": {"spelling_answer": "alpha", "meaning_answer": "甲"}},
        )
        card = self.store.memory["alpha"]
        self.assertEqual(card["wrong_count"], 1)
        self.assertEqual(card["last_error_type"], "skip")
        self.assertEqual(card["repetitions"], 0)

    def test_same_day_sm2_blocked(self):
        self._full_session_correct()
        first_next = self.store.memory["alpha"]["next_review_at"]
        self._full_session_correct()
        card = self.store.memory["alpha"]
        self.assertEqual(card["review_count"], 2)
        self.assertEqual(card["next_review_at"], first_next)

    def test_review_track_skips_stage2_memory(self):
        self.store.sessions["s2"] = {
            "id": "s2",
            "words": [{"word": "beta", "source": "review", "meaning": "乙"}],
        }
        self.service.record_stage2_submit(
            "s2",
            [
                {
                    "word": "beta",
                    "meaning_answer": "错",
                    "expected_meaning": "乙",
                    "skipped": False,
                    "meaning_correct": False,
                }
            ],
        )
        self.assertEqual(len(self.store.events), 0)

    def test_is_due_includes_incomplete(self):
        self.service.record_stage1_complete("s1", ["alpha"])
        card = self.store.memory["alpha"]
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc) + timedelta(days=2)
        self.assertTrue(self.service.is_due(card, now))

    def test_save_rejects_incomplete_card(self):
        self.service.record_stage1_complete("s1", ["alpha"])
        memory = self.store.memory
        del memory["alpha"]["is_leech"]
        with self.assertRaises(RuntimeError):
            self.service._save(memory, [])


if __name__ == "__main__":
    unittest.main()
