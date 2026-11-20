"""Validate the complete LLM result before starting a database transaction."""

import json

from pydantic import ValidationError

from app.schemas.quiz import GeneratedQuiz
from app.utils.errors import AppError


def invalid_quiz_response() -> AppError:
    """Keep malformed, incomplete and duplicate model output on one safe contract."""
    return AppError(
        502, "QUIZ_INVALID_RESPONSE",
        "Dữ liệu bài luyện tập chưa hợp lệ. Chưa có bài nào được lưu. Vui lòng tạo lại bài.",
    )


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def validate_generated_quiz(payload: object) -> GeneratedQuiz:
    """Accept a JSON object/string, never silently repair incomplete model output."""
    try:
        if isinstance(payload, str):
            payload = json.loads(payload, object_pairs_hook=_unique_keys)
        if isinstance(payload, GeneratedQuiz):
            # Revalidate even instances built with model_construct/model_copy.
            payload = payload.model_dump()
        return GeneratedQuiz.model_validate(payload)
    except (ValidationError, ValueError, TypeError, RecursionError):
        # Provider output can contain an answer key or PII; never echo it in errors.
        raise invalid_quiz_response() from None
