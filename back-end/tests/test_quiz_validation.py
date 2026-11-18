"""Reject the whole generated quiz when any question/answer/explanation is invalid."""

from copy import deepcopy
import json

import pytest

from app.schemas.quiz import GeneratedQuiz, GeneratedQuizQuestion, QuizOptions
from app.utils.errors import AppError
from app.validators.quiz import validate_generated_quiz


def valid_payload():
    return {"questions": [{
        "question_text": f"Câu {position}: 1 + 1 = ?",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "correct_answer": "B", "explanation": "Một cộng một bằng hai.",
    } for position in range(1, 6)]}


def test_valid_dict_and_json_keep_five_ordered_questions_and_trim_text():
    payload = valid_payload()
    payload["questions"][0]["question_text"] = "  Câu hỏi đầu tiên\n"
    payload["questions"][0]["options"]["A"] = "  Một  "
    payload["questions"][0]["explanation"] = "  Vì phép cộng.  "
    result = validate_generated_quiz(payload)
    assert len(result.questions) == 5
    assert result.questions[0].question_text == "Câu hỏi đầu tiên"
    assert result.questions[0].options.A == "Một"
    assert result.questions[0].explanation == "Vì phép cộng."
    assert result == validate_generated_quiz(json.dumps(payload, ensure_ascii=False))
    # Validation works on a copy, without changing the provider's original object.
    assert payload["questions"][0]["options"]["A"] == "  Một  "


def invalid_payloads():
    for count in (0, 1, 4, 6):
        payload = valid_payload()
        payload["questions"] = (payload["questions"] * 2)[:count]
        yield f"count-{count}", payload
    for key in ("question_text", "options", "correct_answer", "explanation"):
        payload = valid_payload()
        del payload["questions"][4][key]
        yield f"missing-{key}", payload
    for key in ("question_text", "explanation"):
        for value in (None, 12, True, [], "", " \n\t ", "\ud800", "text\x00", "x" * 8001):
            payload = valid_payload()
            payload["questions"][4][key] = value
            yield f"bad-{key}-{repr(value)[:25]}", payload
    for value in (None, 1, [], "A", {}, {"A": "1", "B": "2", "C": "3"}, {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}):
        payload = valid_payload()
        payload["questions"][4]["options"] = value
        yield f"bad-options-{repr(value)[:25]}", payload
    for value in (None, 1, True, {}, [], "", " \n ", "x" * 2001, "\ud800", "text\x00"):
        payload = valid_payload()
        payload["questions"][4]["options"]["D"] = value
        yield f"bad-option-D-{repr(value)[:25]}", payload
    for value in ("a", "E", "AB", ["A", "B"], True, 0, None, " A "):
        payload = valid_payload()
        payload["questions"][4]["correct_answer"] = value
        yield f"bad-answer-{value}", payload
    for key in ("position", "id", "is_correct"):
        payload = valid_payload()
        payload["questions"][4][key] = 1
        yield f"extra-question-{key}", payload
    for key in ("user_id", "topic_id", "difficulty", "status", "score"):
        payload = valid_payload()
        payload[key] = 1
        yield f"extra-quiz-{key}", payload
    for payload in (None, [], "not json", '{"questions":', "```json\n{}\n```", {"questions": "five"}):
        yield f"bad-root-{repr(payload)[:25]}", payload


CASES = list(invalid_payloads())


@pytest.mark.parametrize("payload", [payload for _, payload in CASES], ids=[name for name, _ in CASES])
def test_any_invalid_question_rejects_entire_quiz_with_safe_error(payload):
    with pytest.raises(AppError) as caught:
        validate_generated_quiz(deepcopy(payload))
    assert caught.value.status_code == 502
    assert caught.value.code == "QUIZ_INVALID_RESPONSE"
    assert caught.value.fields is None


def test_duplicate_json_keys_are_not_silently_overwritten():
    raw = json.dumps(valid_payload()).replace('"correct_answer": "B"', '"correct_answer": "A", "correct_answer": "B"', 1)
    with pytest.raises(AppError, match="Dữ liệu bài luyện tập"):
        validate_generated_quiz(raw)


def test_constructed_or_copied_models_do_not_bypass_validation():
    invalid = GeneratedQuiz.model_construct(questions=())
    with pytest.raises(AppError):
        validate_generated_quiz(invalid)
    valid = validate_generated_quiz(valid_payload())
    with pytest.raises(AppError):
        validate_generated_quiz(valid.model_copy(update={"questions": valid.questions[:4]}))


def test_nested_model_instances_do_not_bypass_complete_validation():
    payload = valid_payload()
    payload["questions"][4] = GeneratedQuizQuestion.model_construct(**{**payload["questions"][4], "explanation": " "})
    with pytest.raises(AppError):
        validate_generated_quiz(payload)
    payload = valid_payload()
    payload["questions"][4]["options"] = QuizOptions.model_construct(A="1", B="2", C="3", D=" ")
    with pytest.raises(AppError):
        validate_generated_quiz(payload)
