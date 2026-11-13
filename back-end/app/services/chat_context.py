"""Ngữ cảnh hội thoại có giới hạn và bản sao đã ẩn dữ liệu trước khi gửi LLM.

Không sửa nội dung lưu trong database. Bộ lọc xử lý thông tin tài khoản đã biết,
email và các giá trị được đánh dấu rõ là thông tin cá nhân/bí mật. Tên hoặc mật
khẩu bất kỳ không có nhãn không thể được nhận diện đầy đủ chỉ bằng biểu thức mẫu.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Callable

from app.prompts.socratic import SocraticTopic, build_first_turn_messages

MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS = 20_000
MAX_REDACTED_TOPIC_DESCRIPTION = 2000

CONVERSATION_SYSTEM_PROMPT = (
    Path(__file__).resolve().parents[1] / "prompts" / "socratic_conversation.txt"
).read_text(encoding="utf-8").strip()

HINT_INSTRUCTIONS = {
    1: "Ứng dụng chọn gợi ý mức 1: một câu hỏi gợi mở hoặc một gợi nhắc nhỏ về khái niệm/dữ kiện để người học tự bắt đầu.",
    2: "Ứng dụng chọn gợi ý mức 2: dựa vào câu hỏi và bước đã thử, chỉ rõ quy tắc hoặc hướng biến đổi cần kiểm tra; chưa tính hết hoặc cho đáp án.",
    3: "Ứng dụng chọn gợi ý mức 3: hướng dẫn cụ thể hơn một bước tiếp theo từ chỗ người học đang vướng, để họ tự thực hiện phần còn lại; vẫn không đưa lời giải đầy đủ hay đáp án cuối cùng.",
}

_MASKS = re.compile(r"(\[(?:NAME|EMAIL|SECRET)\])")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[\w-]{2,}(?![\w-])", re.UNICODE)
_JWT = re.compile(r"(?<![\w-])eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![\w-])")
_BEARER = re.compile(r"\bBearer[ \t]+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
_VALUE = r'''(?P<value>"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)'''
_AUTHORIZATION = re.compile(
    r'''(?P<label>["']?\bauthorization\b["']?\s*[:=]\s*)(?P<value>"[^"\r\n]*"|'[^'\r\n]*'|(?:Bearer|Basic)[ \t]+[^\s,;]+|[^\s,;]+)''',
    re.IGNORECASE,
)
_SECRET_LABEL = re.compile(
    r'''(?P<label>["']?\b(?:password|passwd|pwd|mật\s*khẩu|mat\s*khau|api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|token|authorization)\b["']?\s*[:=]\s*)'''
    + _VALUE, re.IGNORECASE,
)
_SELF_SECRET = re.compile(
    r"(?P<label>\b(?:(?:mật\s*khẩu|mat\s*khau)\s+của\s+(?:tôi|em)\s+là|my\s+(?:password|api\s+key|token)\s+is)\s+)"
    + _VALUE, re.IGNORECASE,
)
_NAME_VALUE = r'''(?P<value>"[^"\r\n]*"|'[^'\r\n]*'|[^\n,;.!?]{1,120})'''
_NAME_LABEL = re.compile(
    r'''(?P<label>["']?\b(?:họ\s*(?:và\s*)?tên|full[\s_-]*name)\b["']?\s*[:=]\s*)'''
    + _NAME_VALUE, re.IGNORECASE,
)
_SELF_NAME = re.compile(
    r"(?P<label>\b(?:(?:tôi|em)\s+tên(?:\s+là)?|tên\s+(?:của\s+)?(?:tôi|em)(?:\s+là)?|my\s+name\s+is)\s+)"
    + _NAME_VALUE, re.IGNORECASE,
)
_NAME_TAIL = re.compile(r"\s+(?:và|đang|muốn|cần|hỏi|xin|cho|chưa|nhưng|nên|and|but|because|I|i)\b")


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Nội dung ngữ cảnh phải là chuỗi ký tự.")
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\t" for char in value):
        raise ValueError("Nội dung ngữ cảnh chứa ký tự không hợp lệ.")
    return value


def _unmasked(text: str, transform: Callable[[str], str]) -> str:
    return "".join(part if _MASKS.fullmatch(part) else transform(part) for part in _MASKS.split(text))


def _replace_labeled(match: re.Match, marker: str) -> str:
    value = match.group("value")
    if value[:1] in {'"', "'"} and value[-1:] == value[:1]:
        marker = value[0] + marker + value[-1]
    elif marker == "[NAME]":
        tail = _NAME_TAIL.search(value)
        if tail is not None:
            marker += value[tail.start():]
    return match.group("label") + marker


def redact_sensitive_text(
    text: str, *, known_name: str = "", known_email: str = "", secret_values: Sequence[str] = (),
) -> str:
    """Ẩn dữ liệu trong bản sao đầu vào/đầu ra, không lưu hay ghi log giá trị gốc."""
    text = _text(text)
    name, email = " ".join(_text(known_name).split()), _text(known_email).strip()
    if isinstance(secret_values, (str, bytes)) or not isinstance(secret_values, Sequence):
        raise ValueError("Danh sách giá trị bí mật không hợp lệ.")
    if any(not isinstance(value, str) for value in secret_values):
        raise ValueError("Danh sách giá trị bí mật không hợp lệ.")
    secrets = sorted({_text(value) for value in secret_values if value}, key=len, reverse=True)
    if email:
        pattern = re.compile(re.escape(email), re.IGNORECASE)
        text = _unmasked(text, lambda part: pattern.sub("[EMAIL]", part))
    text = _unmasked(text, lambda part: _EMAIL.sub("[EMAIL]", part))
    if name:
        pattern = re.compile(r"(?<!\w)" + r"\s+".join(re.escape(word) for word in name.split()) + r"(?!\w)", re.IGNORECASE)
        text = _unmasked(text, lambda part: pattern.sub("[NAME]", part))
    text = _NAME_LABEL.sub(lambda match: _replace_labeled(match, "[NAME]"), text)
    text = _SELF_NAME.sub(lambda match: _replace_labeled(match, "[NAME]"), text)
    text = _AUTHORIZATION.sub(lambda match: _replace_labeled(match, "[SECRET]"), text)
    text = _SECRET_LABEL.sub(lambda match: _replace_labeled(match, "[SECRET]"), text)
    text = _SELF_SECRET.sub(lambda match: _replace_labeled(match, "[SECRET]"), text)
    text = _unmasked(text, lambda part: _JWT.sub("[SECRET]", part))
    text = _unmasked(text, lambda part: _BEARER.sub("Bearer [SECRET]", part))
    for secret in secrets:
        text = _unmasked(text, lambda part, value=secret: part.replace(value, "[SECRET]"))
    return text


def _history(messages: Sequence[dict[str, str]], redact: Callable[[str], str]) -> list[dict[str, str]]:
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence) or not messages:
        raise ValueError("Ngữ cảnh hội thoại phải có tin nhắn của người học.")
    result = []
    for message in messages:
        if not isinstance(message, Mapping) or set(message) != {"role", "content"} or not isinstance(message["role"], str) or message["role"] not in {"user", "assistant"}:
            raise ValueError("Ngữ cảnh chỉ nhận nội dung và vai trò user/assistant.")
        content = redact(message["content"]).strip()
        if not content:
            raise ValueError("Ngữ cảnh có tin nhắn không có nội dung.")
        result.append({"role": message["role"], "content": content})
    if not any(message["role"] == "user" for message in result):
        raise ValueError("Ngữ cảnh hội thoại phải có câu hỏi của người học.")
    return result


def _safe_topic(topic: SocraticTopic, redact: Callable[[str], str]) -> SocraticTopic:
    if not isinstance(topic, SocraticTopic):
        raise ValueError("Ngữ cảnh chủ đề phải là SocraticTopic.")
    return SocraticTopic(
        subject_name=redact(topic.subject_name)[:120],
        topic_name=redact(topic.topic_name)[:180],
        grade_level=redact(topic.grade_level)[:50],
        chapter_name=redact(topic.chapter_name)[:150],
        description=redact(topic.description)[:MAX_REDACTED_TOPIC_DESCRIPTION] if topic.description is not None else None,
    )


def _bounded_history(
    history: list[dict[str, str]], *, question_index: int, slots: int, characters: int,
) -> list[dict[str, str]]:
    if slots < 1:
        raise ValueError("Giới hạn ngữ cảnh phải giữ được câu hỏi của người học.")
    selected = list(range(max(0, len(history) - slots), len(history)))
    if question_index not in selected:
        selected[0] = question_index
    # Tin nhắn trợ lý bị cắt khỏi câu hỏi trước nó không mở đầu phần lịch sử.
    while len(selected) > 1 and history[selected[0]]["role"] == "assistant":
        selected.pop(0)
    while sum(len(history[index]["content"]) for index in selected) > characters and len(selected) > 1:
        removable = next(index for index in selected if index != question_index)
        selected.remove(removable)
    while len(selected) > 1 and history[selected[0]]["role"] == "assistant":
        selected.pop(0)
    if len(history[question_index]["content"]) > characters:
        raise ValueError("Câu hỏi vượt quá giới hạn ngữ cảnh gửi model.")
    return [dict(history[index]) for index in selected]


def build_chat_messages(
    *, topic: SocraticTopic, history: Sequence[dict[str, str]], hint_level: int = 1,
    known_name: str = "", known_email: str = "", secret_values: Sequence[str] = (),
) -> list[dict[str, str]]:
    """Tạo tối đa 12 messages/20.000 ký tự, luôn giữ câu hỏi mới nhất.

    Giới hạn áp dụng cho toàn bộ payload messages, kể cả system và ngữ cảnh môn.
    Mức gợi ý được chọn bởi service; dữ liệu người học không được chọn mức này.
    """
    if type(hint_level) is not int or hint_level not in HINT_INSTRUCTIONS:
        raise ValueError("Mức gợi ý phải từ 1 đến 3.")

    def redact(value: str) -> str:
        return redact_sensitive_text(value, known_name=known_name, known_email=known_email, secret_values=secret_values)

    clean = _history(history, redact)
    safe_topic = _safe_topic(topic, redact)
    question_index = max(index for index, message in enumerate(clean) if message["role"] == "user")
    first = build_first_turn_messages(question=clean[question_index]["content"], topic=safe_topic)
    if len(clean) == 1 and hint_level == 1:
        if sum(len(message["content"]) for message in first) > MAX_CONTEXT_CHARS:
            raise ValueError("Câu hỏi vượt quá giới hạn ngữ cảnh gửi model.")
        return first
    topic_data = json.loads(first[1]["content"])["topic"]
    prefix = [
        {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT + "\n\n" + HINT_INSTRUCTIONS[hint_level]},
        {"role": "user", "content": json.dumps({"type": "academic_context", "topic": topic_data}, ensure_ascii=False)},
    ]
    request = {"role": "user", "content": json.dumps({
        "type": "learning_request", "hintLevel": hint_level,
        "action": "respond_to_latest_question" if clean[-1]["role"] == "user" else "continue_hint",
    }, ensure_ascii=False)}
    characters = MAX_CONTEXT_CHARS - sum(len(message["content"]) for message in [*prefix, request])
    if characters <= 0:
        raise ValueError("Ngữ cảnh môn vượt quá giới hạn gửi model.")
    selected = _bounded_history(clean, question_index=question_index, slots=MAX_CONTEXT_MESSAGES - 3, characters=characters)
    return [*prefix, *selected, request]
