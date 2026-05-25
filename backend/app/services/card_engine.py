import re


def highlight_word(sentence: str, word: str) -> str:
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    return pattern.sub(lambda match: f"<u>{match.group(0)}</u>", sentence, count=1)


class CardEngine:
    def build_cards(self, story: dict, session_words: list[dict]) -> list[dict]:
        if story is None:
            raise RuntimeError("Session 尚未生成剧情")

        occurrence_map: dict[str, dict] = {}
        for chapter in story["chapters"]:
            for item in chapter["occurrences"]:
                word = item["word"].lower()
                if word not in occurrence_map:
                    occurrence_map[word] = item

        cards: list[dict] = []
        for row in session_words:
            word = row["word"].lower()
            occurrence = occurrence_map.get(word)
            if occurrence is None:
                raise RuntimeError(f"剧情中缺少单词：{word}")
            cards.append(
                {
                    "word": occurrence["word"],
                    "pos": occurrence["pos"],
                    "meaning": occurrence["meaning"],
                    "sentence_en": occurrence["sentence_en"],
                    "sentence_en_highlighted": highlight_word(
                        occurrence["sentence_en"], occurrence["word"]
                    ),
                    "sentence_zh": occurrence["sentence_zh"],
                }
            )
        return cards
