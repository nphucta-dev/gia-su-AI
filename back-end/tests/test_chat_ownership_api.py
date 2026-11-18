"""TK-082: neither another learner nor an administrator owns private chats."""

from copy import deepcopy
from dataclasses import replace

import pytest

from test_chat_api import ROOT, api, create_session

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("foreign_role", ["LEARNER", "ADMIN"])
async def test_private_chat_access_ignores_forged_owner_and_never_writes(foreign_role):
    async with api() as state:
        state.users._users[state.other.id] = replace(state.other, role=foreign_role)
        session = await create_session(state)
        await state.repository.append_user_message(state.current.id, session["id"], "PRIVATE_OWNER_QUESTION")
        before = (deepcopy(state.repository._sessions), deepcopy(state.repository._messages))
        forged_query = f"?user_id={state.current.id}&userId={state.current.id}"

        listing = await state.client.get(ROOT + forged_query, headers=state.other_headers)
        assert listing.status_code == 200
        assert listing.json()["sessions"] == []

        for method, suffix, body in (
            ("GET", "", None),
            ("GET", "/messages", None),
            ("POST", "/messages", {"content": "FOREIGN_WRITE_ATTEMPT"}),
            ("POST", "/hints", None),
        ):
            options = {"json": body} if body is not None else {}
            foreign = await state.client.request(
                method, f"{ROOT}/{session['id']}{suffix}{forged_query}",
                headers={**state.other_headers, "X-User-Id": str(state.current.id)}, **options,
            )
            missing = await state.client.request(
                method, f"{ROOT}/{2**31 - 1}{suffix}{forged_query}",
                headers=state.other_headers, **options,
            )
            assert foreign.status_code == missing.status_code == 404
            assert foreign.json() == missing.json()
            assert foreign.headers["cache-control"] == "no-store"
            assert "PRIVATE_OWNER_QUESTION" not in foreign.text

        assert state.repository._sessions == before[0]
        assert state.repository._messages == before[1]
        assert state.model.calls == []
        own_history = await state.client.get(f"{ROOT}/{session['id']}/messages")
        assert own_history.status_code == 200
        assert own_history.json()["messages"][0]["content"] == "PRIVATE_OWNER_QUESTION"


@pytest.mark.parametrize("owner_field", ["user_id", "userId"])
async def test_client_cannot_choose_chat_owner_when_creating_session(owner_field):
    async with api() as state:
        forged = await state.client.post(
            ROOT, headers=state.other_headers,
            json={"topicId": state.topic_id, owner_field: state.current.id},
        )
        assert forged.status_code == 422
        assert state.repository._sessions == {}
        created = await state.client.post(ROOT, headers=state.other_headers, json={"topicId": state.topic_id})
        assert created.status_code == 201
        session_id = created.json()["session"]["id"]
        assert state.repository._sessions[session_id].user_id == state.other.id
        assert (await state.client.get(f"{ROOT}/{session_id}")).status_code == 404
