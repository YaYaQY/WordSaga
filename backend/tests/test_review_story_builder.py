import unittest

from app.services.review_story_builder import ReviewStoryBuilder


class MemoryStoreStub:
    def __init__(self, sessions: dict):
        self.sessions = sessions

    def get_sessions(self):
        return self.sessions


class ReviewStoryBuilderTests(unittest.TestCase):
    def test_partition_splits_missing_occurrences(self):
        sessions = {
            "s1": {
                "id": "s1",
                "created_at": "2026-01-02T00:00:00+00:00",
                "story": {
                    "review_mode": False,
                    "enrichment_status": "complete",
                    "chapters": [
                        {
                            "occurrences": [
                                {
                                    "word": "alpha",
                                    "sentence_en": "Alpha sentence.",
                                    "sentence_zh": "甲",
                                }
                            ]
                        }
                    ],
                },
            }
        }
        builder = ReviewStoryBuilder(MemoryStoreStub(sessions))
        ready, skipped = builder.partition_by_occurrences(
            [
                {"word": "alpha", "source": "review", "meaning": "甲"},
                {"word": "beta", "source": "review", "meaning": "乙"},
            ]
        )
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["word"], "alpha")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["word"], "beta")


if __name__ == "__main__":
    unittest.main()
