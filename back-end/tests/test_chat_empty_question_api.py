"""TK-027: API từ chối câu hỏi rỗng, chỉ chứa khoảng trắng hoặc ký tự vô hình."""

import pytest

from app.services.chat_service import validate_message_content
from app.utils.errors import AppError
from test_chat_api import ROOT, api, create_session, history


@pytest.mark.parametrize("blank", [
    "",
    " ",
    "   \t\n\r  ",
    "\u00a0",
    "\u200b",
    "\ufeff \u200b\u2060 ",
])
def test_validate_message_content_rejects_empty_and_whitespace_only(blank):
    with pytest.raises(AppError) as caught:
        validate_message_content(blank)
    assert caught.value.status_code == 422
    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.fields == {"content": "Vui lòng nhập câu hỏi trước khi gửi."}


@pytest.mark.parametrize("invalid", ["abc\x00def", "abc\x07def", "abc\ud800def"])
def test_validate_message_content_rejects_control_and_surrogate_chars(invalid):
    with pytest.raises(AppError) as caught:
        validate_message_content(invalid)
    assert caught.value.status_code == 422
    assert caught.value.code == "VALIDATION_ERROR"


def test_validate_message_content_trims_valid_question():
    assert validate_message_content("  Giải x² − 5x + 6 = 0  ") == "Giải x² − 5x + 6 = 0"


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [
    {"content": ""},
    {"content": "   "},
    {"content": "\n\t\r "},
    {"content": "\u00a0\u200b\ufeff"},
    {},
    {"content": None},
    {"content": 123},
])
async def test_send_message_api_rejects_blank_question_without_saving_or_calling_llm(payload):
    async with api() as state:
        session = await create_session(state)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert await history(state, session["id"]) == []
        assert state.model.calls == []
