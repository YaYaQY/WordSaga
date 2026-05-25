import json

from app.services.ai_client import chat_completion, parse_json_response

GRADE_SYSTEM = "你只输出严格 JSON，用于 WordSaga 学习批改。"


class GradingService:
    def _normalize_result(self, item: dict, word: str) -> dict:
        required = ["spelling_correct", "meaning_correct", "sentence_correct", "errors", "suggestions"]
        missing = [key for key in required if key not in item]
        if missing:
            raise RuntimeError(f"AI 批改输出缺少字段：{', '.join(missing)}")
        return {
            "word": word,
            "spelling_correct": bool(item["spelling_correct"]),
            "meaning_correct": bool(item["meaning_correct"]),
            "sentence_correct": bool(item["sentence_correct"]),
            "errors": item["errors"],
            "suggestions": item["suggestions"],
        }

    def grade(self, payload: dict) -> dict:
        results = self.grade_batch([payload])
        return results[0]

    def grade_batch(self, payloads: list[dict]) -> list[dict]:
        if not payloads:
            return []

        prompt = (
            "批改用户的单词学习作答，一次处理全部单词。\n"
            "要求：\n"
            "1. 判断每项的拼写、释义、整句英文是否正确。\n"
            "2. 释义允许同义表达，语义一致即可判对。\n"
            "3. user_sentence 为空时，sentence_correct 记为 true。\n"
            "4. 仅输出 JSON，不要 Markdown。\n"
            "JSON 结构：\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "word": "与输入一致",\n'
            '      "spelling_correct": true,\n'
            '      "meaning_correct": true,\n'
            '      "sentence_correct": true,\n'
            '      "errors": ["错误说明"],\n'
            '      "suggestions": ["修正建议"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            f"批改数据：{json.dumps(payloads, ensure_ascii=False)}"
        )
        content = chat_completion(GRADE_SYSTEM, prompt, stream=False)
        data = parse_json_response(content)
        if "results" not in data or not isinstance(data["results"], list):
            raise RuntimeError("AI 批改输出缺少 results 数组")

        by_word = {str(item.get("word", "")).lower(): item for item in data["results"]}
        graded: list[dict] = []
        for payload in payloads:
            word = payload["word"]
            item = by_word.get(word.lower())
            if item is None:
                raise RuntimeError(f"AI 批改结果缺少单词：{word}")
            graded.append(self._normalize_result(item, word))
        return graded
