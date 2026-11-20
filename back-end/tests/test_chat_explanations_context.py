"""TK-034: explanation prompts keep the actual reply they are explaining."""

from copy import deepcopy
import json

import pytest

from app.prompts.socratic import SocraticTopic
from app.services import chat_context
from app.services.chat_context import (
    EXPLANATION_TRUNCATION, MAX_CONTEXT_CHARS, MAX_CONTEXT_MESSAGES, build_explanation_messages,
)

TOPIC = SocraticTopic("Toán", "Phương trình", "THPT", "Đại số", "D" * 2000)


@pytest.mark.parametrize("mode", ["simplify", "example"])
def test_latest_question_and_reply_survive_dense_context_without_mutating_history(mode):
    question = "LATEST_QUESTION " + "Q" * (4000 - len("LATEST_QUESTION "))
    answer = "LATEST_REPLY " + "A" * (8000 - len("LATEST_REPLY "))
    history = [{"role": role, "content": f"Old {index} " + "X" * 2000}
               for index in range(12) for role in ("user", "assistant")]
    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    original = deepcopy(history)
    sources = [{"title": "T" * 160, "content": "S" * 1000} for _ in range(3)]
    messages = build_explanation_messages(topic=TOPIC, history=history, mode=mode, sources=sources)
    assert len(messages) <= MAX_CONTEXT_MESSAGES
    assert sum(len(item["content"]) for item in messages) <= MAX_CONTEXT_CHARS
    assert {"role": "user", "content": question} in messages
    latest = next(item for item in messages if item["role"] == "assistant" and item["content"].startswith("LATEST_REPLY"))
    assert latest["content"].endswith(EXPLANATION_TRUNCATION) and len(latest["content"]) < len(answer)
    assert len(json.loads(messages[2]["content"])["sources"]) == 3
    assert json.loads(messages[-1]["content"]) == {
        "type": "learning_request", "action": mode, "target": "latest_assistant_response",
    }
    assert history == original


@pytest.mark.parametrize("mode", ["simplify", "example"])
def test_unanswered_latest_question_is_the_target_instead_of_an_older_reply(mode):
    history = [{"role": "user", "content": "Câu hỏi cũ"}, {"role": "assistant", "content": "Giải thích cũ"},
               {"role": "user", "content": "Câu hỏi mới về hệ số a"}]
    messages = build_explanation_messages(topic=TOPIC, history=history, mode=mode)
    assert history[-1] in messages
    request = json.loads(messages[-1]["content"])
    assert request["action"] == mode and request["target"] == "latest_question"


@pytest.mark.parametrize("variable,value", [("MAX_CONTEXT_CHARS", 100), ("MAX_CONTEXT_MESSAGES", 4)])
def test_too_small_budget_is_rejected_instead_of_silently_dropping_the_target(monkeypatch, variable, value):
    monkeypatch.setattr(chat_context, variable, value)
    with pytest.raises(ValueError):
        build_explanation_messages(topic=TOPIC, history=[{"role": "user", "content": "Câu hỏi"},
                                                        {"role": "assistant", "content": "Phản hồi cần giải thích"}],
                                   mode="simplify")
