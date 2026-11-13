"""TK-030: tạo system/user messages cho lượt đầu, dùng được khi chưa có model.

Chỉ nhận ngữ cảnh học tập. Không nhận User/ORM object, lịch sử hội thoại, tài liệu
RAG hoặc cờ cho lời giải đầy đủ; các luồng đó được tích hợp ở task tương ứng.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PROMPT_VERSION = "socratic-first-turn-v1"
SOCRATIC_SYSTEM_PROMPT = Path(__file__).with_name("socratic_system.txt").read_text(encoding="utf-8").strip()
MAX_QUESTION_CHARS = 4000
MAX_ATTEMPT_CHARS = 4000
MAX_TOPIC_DESCRIPTION_CHARS = 2000


@dataclass(frozen=True)
class SocraticTopic:
    subject_name: str
    topic_name: str
    grade_level: str = ""
    chapter_name: str = ""
    description: str | None = None


def _text(value: str, *, name: str, limit: int | None = None, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} phải là chuỗi ký tự.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip().lstrip("\ufeff").strip()
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\t" for char in value):
        raise ValueError(f"{name} chứa ký tự không hợp lệ.")
    if required and not any(not char.isspace() and unicodedata.category(char) != "Cf" for char in value):
        raise ValueError(f"{name} không được để trống.")
    if limit is not None and len(value) > limit:
        raise ValueError(f"{name} tối đa {limit} ký tự.")
    return value


def _topic_data(topic: SocraticTopic) -> dict[str, str]:
    if not isinstance(topic, SocraticTopic):
        raise ValueError("Ngữ cảnh chủ đề phải là SocraticTopic.")
    fields = (
        ("subjectName", topic.subject_name, 120, True),
        ("topicName", topic.topic_name, 180, True),
        ("gradeLevel", topic.grade_level, 50, False),
        ("chapterName", topic.chapter_name, 150, False),
    )
    data = {}
    for key, value, limit, required in fields:
        clean = _text(value, name=key, required=required)
        clean = " ".join(clean.split())
        if len(clean) > limit:
            raise ValueError(f"{key} tối đa {limit} ký tự.")
        data[key] = clean
    if topic.description is not None:
        description = _text(topic.description, name="description", required=False)
        if description:
            data["description"] = description[:MAX_TOPIC_DESCRIPTION_CHARS]
    return data


def build_first_turn_messages(
    *, question: str, topic: SocraticTopic, learner_attempt: str | None = None,
) -> list[dict[str, str]]:
    """Tạo messages để truyền cho adapter LLM sau này, không gọi API.

    System prompt cố định; dữ liệu không tin cậy chỉ nằm trong JSON của user.
    Việc phân tách này không thay cho bộ lọc PII hoặc kiểm thử hành vi model.
    """
    data = {
        "turn": "first",
        "topic": _topic_data(topic),
        "question": _text(question, name="Câu hỏi", limit=MAX_QUESTION_CHARS),
    }
    if learner_attempt is not None:
        attempt = _text(learner_attempt, name="Bài làm đã thử", limit=MAX_ATTEMPT_CHARS, required=False)
        if attempt:
            data["learnerAttempt"] = attempt
    return [
        {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False, indent=2)},
    ]
