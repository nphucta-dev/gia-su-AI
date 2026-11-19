"""TK-032: điều phối thang gợi ý 1–3 và lưu hint_level cho tin nhắn AI."""

import pytest

from app.repositories.chat_repository import ChatMessageRecord
from app.services.chat_service import MAX_HINT_LEVEL, resolve_next_hint_level
from app.utils.errors import AppError
from test_chat_api import ROOT, api, create_session, history


def msg(msg_id: int, role: str, hint_level: int | None = None) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=msg_id,
        session_id=1,
        role=role,
        content=f"msg-{msg_id}",
        created_at="2026-11-18T00:00:00Z",
        hint_level=hint_level,
    )


def test_resolve_next_hint_level_requires_a_user_question():
    for empty_or_no_user in ([], [msg(1, "assistant", hint_level=1)]):
        with pytest.raises(AppError) as caught:
            resolve_next_hint_level(empty_or_no_user)
        assert caught.value.status_code == 409
        assert caught.value.code == "CHAT_QUESTION_REQUIRED"


def test_resolve_next_hint_level_progresses_1_to_3_and_stops():
    assert MAX_HINT_LEVEL == 3
    assert resolve_next_hint_level([msg(1, "user")]) == 1
    assert resolve_next_hint_level([msg(1, "user"), msg(2, "assistant", 1)]) == 2
    assert resolve_next_hint_level([msg(1, "user"), msg(2, "assistant", 1), msg(3, "assistant", 2)]) == 3

    with pytest.raises(AppError) as caught:
        resolve_next_hint_level([
            msg(1, "user"),
            msg(2, "assistant", 1),
            msg(3, "assistant", 2),
            msg(4, "assistant", 3),
        ])
    assert caught.value.status_code == 409
    assert caught.value.code == "HINT_LIMIT_REACHED"


def test_resolve_next_hint_level_resets_after_new_user_question():
    records = [
        msg(1, "user"),
        msg(2, "assistant", 1),
        msg(3, "assistant", 2),
        msg(4, "assistant", 3),
        msg(5, "user"),
    ]
    assert resolve_next_hint_level(records) == 1
    records.append(msg(6, "assistant", None))
    assert resolve_next_hint_level(records) == 1
    records.append(msg(7, "assistant", 1))
    assert resolve_next_hint_level(records) == 2


@pytest.mark.anyio
async def test_hint_orchestration_persists_levels_1_to_3_and_blocks_fourth():
    async with api() as state:
        session = await create_session(state)
        first = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Giải x² − 5x + 6 = 0"})
        assert first.status_code == 201
        assert first.json()["userMessage"]["hintLevel"] is None
        assert first.json()["assistantMessage"]["hintLevel"] == 1

        second = await state.client.post(f"{ROOT}/{session['id']}/hints")
        assert second.status_code == 201
        assert second.json()["assistantMessage"]["hintLevel"] == 2

        third = await state.client.post(f"{ROOT}/{session['id']}/hints")
        assert third.status_code == 201
        assert third.json()["assistantMessage"]["hintLevel"] == 3

        fourth = await state.client.post(f"{ROOT}/{session['id']}/hints")
        assert fourth.status_code == 409
        assert fourth.json()["error"]["code"] == "HINT_LIMIT_REACHED"

        stored = await history(state, session["id"])
        assert [item["hintLevel"] for item in stored] == [None, 1, 2, 3]
