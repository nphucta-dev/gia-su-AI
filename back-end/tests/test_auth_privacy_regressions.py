"""Actual API regressions for invalid registration Unicode and prompt redaction."""

import json

import pytest

from app.services.chat_context import redact_sensitive_text
from test_chat_api import FakeLLM, api as chat_api, create_session, history
from test_register_api import REGISTER, api as register_api, fast_hasher, valid_body

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("field", ["name", "email", "password"])
@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"], ids=["high-surrogate", "low-surrogate"])
async def test_invalid_registration_unicode_returns_422_without_hashing_or_creating_account(field, surrogate):
    hashed = []

    def hasher(value):
        hashed.append(value)
        return fast_hasher(value)

    async with register_api(password_hasher=hasher) as (client, repository):
        body = valid_body()
        body[field] = {"name": "Name" + surrogate, "email": "audit" + surrogate + "@example.com",
                       "password": "Password" + surrogate}[field]
        if field == "password":
            body["confirmPassword"] = body[field]
        # Explicit JSON escaping sends an invalid Unicode scalar to the API,
        # rather than failing in the HTTP client's own UTF-8 encoder.
        response = await client.post(REGISTER, content=json.dumps(body), headers={"Content-Type": "application/json"})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert field in response.json()["error"]["fields"]
        assert not hashed and repository._users == {}
        valid = await client.post(REGISTER, json=valid_body())
        assert valid.status_code == 201 and len(repository._users) == 1
        signed_in = await client.post("/api/auth/login", json={"email": valid_body()["email"], "password": valid_body()["password"]})
        assert signed_in.status_code == 200


async def test_valid_unicode_name_and_spaced_password_still_register_and_login():
    async with register_api() as (client, repository):
        password = "mật khẩu 😀 có khoảng trắng"
        body = valid_body(name="Người học 😀", password=password, confirmPassword=password)
        registered = await client.post(REGISTER, json=body)
        assert registered.status_code == 201
        assert registered.json()["user"]["name"] == body["name"]
        stored = await repository.find_by_email(body["email"])
        assert stored.password_hash.startswith("scrypt$")
        signed_in = await client.post("/api/auth/login", json={"email": body["email"], "password": password})
        assert signed_in.status_code == 200


SECRETS = [
    ("password: two words secret; explain algebra", "password: [SECRET]; explain algebra"),
    ("mật khẩu: hai tu bi mat, giải x = 1", "mật khẩu: [SECRET], giải x = 1"),
    ("Mật khẩu của em là hai tu bi mat\nGiải thích phương trình.", "Mật khẩu của em là [SECRET]\nGiải thích phương trình."),
    ("my password is two words secret\nExplain algebra", "my password is [SECRET]\nExplain algebra"),
    ('password: "two words secret"; explain algebra', 'password: "[SECRET]"; explain algebra'),
    ("pwd='two words secret'; explain algebra", "pwd='[SECRET]'; explain algebra"),
    (r'password: "two \"quoted\" words"; explain algebra', 'password: "[SECRET]"; explain algebra'),
    ('password: "two; words, secret"; explain algebra', 'password: "[SECRET]"; explain algebra'),
    ("api_key: a private key with spaces; explain algebra", "api_key: [SECRET]; explain algebra"),
]


@pytest.mark.parametrize("text,expected", SECRETS)
async def test_multiword_labeled_secrets_are_fully_masked_without_losing_delimited_learning_text(text, expected):
    assert redact_sensitive_text(text) == expected
    assert redact_sensitive_text(expected) == expected
    model = FakeLLM(content="A safe hint.")
    async with chat_api(model=model) as state:
        session = await create_session(state)
        response = await state.client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": text})
        assert response.status_code == 201, response.text
        sent = json.loads(model.calls[0][-1]["content"])
        assert sent["question"] == expected
        stored = await history(state, session["id"])
        assert stored[0]["content"] == text  # Privacy filtering changes only the model-bound copy.


async def test_multiword_secret_is_masked_in_provider_output_as_well_as_input():
    model = FakeLLM(content="password: two words secret; try the first step.")
    async with chat_api(model=model) as state:
        session = await create_session(state)
        response = await state.client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "Explain algebra."})
        assert response.status_code == 201, response.text
        assert response.json()["assistantMessage"]["content"] == "password: [SECRET]; try the first step."
