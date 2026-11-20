"""TK-088: real registration/login tokens protect the complete five-question flow.

Uses isolated repositories and a deterministic provider; no database or model API.
"""

from copy import deepcopy
import json

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.quiz_repository import InMemoryQuizRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.llm_client import LLMReply
from test_quiz_validation import valid_payload


@pytest.mark.anyio
async def test_registered_learners_generate_submit_once_and_keep_results_private():
    class QuizProvider:
        calls = 0

        async def generate(self, messages):
            self.calls += 1
            return LLMReply(json.dumps(valid_payload(), ensure_ascii=False), 50)

    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phép cộng")
    quizzes, provider = InMemoryQuizRepository(catalog), QuizProvider()
    app = create_app(
        user_repository=users, catalog_repository=catalog, quiz_repository=quizzes,
        llm_client=provider, settings=Settings(jwt_secret="tk-088-workflow-" + "x" * 40),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
    ) as client:
        headers = []
        user_ids = []
        for name in ("owner", "other"):
            credentials = {"email": f"{name}@example.com", "password": "MatKhau@123"}
            registered = await client.post("/api/auth/register", json={
                **credentials, "name": f"Người học {name}",
                "confirmPassword": credentials["password"], "consent": True,
            })
            assert registered.status_code == 201, registered.text
            user_ids.append(registered.json()["user"]["id"])
            signed_in = await client.post("/api/auth/login", json=credentials)
            assert signed_in.status_code == 200, signed_in.text
            headers.append({"Authorization": "Bearer " + signed_in.json()["access_token"]})

        selection = {"topicId": topic_id, "difficulty": "medium"}
        guest = await client.post("/api/quizzes", json=selection)
        assert guest.status_code == 401 and provider.calls == 0
        generated = await client.post("/api/quizzes", headers=headers[0], json=selection)
        assert generated.status_code == 201, generated.text
        quiz = generated.json()["quiz"]
        quiz_id = quiz["id"]
        assert quizzes._quizzes[quiz_id].user_id == user_ids[0]
        assert len(quiz["questions"]) == 5
        assert [question["position"] for question in quiz["questions"]] == [1, 2, 3, 4, 5]
        assert all(set(question["options"]) == {"A", "B", "C", "D"} for question in quiz["questions"])
        assert "correctAnswer" not in generated.text and "explanation" not in generated.text
        path = f"/api/quizzes/{quiz_id}"
        awaiting = await client.get(path + "/result", headers=headers[0])
        assert awaiting.status_code == 409
        assert awaiting.json()["error"]["code"] == "QUIZ_NOT_COMPLETED"

        payload = {"answers": [
            {"questionId": question["id"], "userAnswer": "B" if index < 3 else "A"}
            for index, question in enumerate(quiz["questions"])
        ]}
        for suffix, method in (("", "GET"), ("/result", "GET"), ("/submit", "POST"), ("/grade", "POST")):
            options = {"json": payload} if suffix == "/submit" else {}
            forbidden = await client.request(method, path + suffix, headers=headers[1], **options)
            assert forbidden.status_code == 404
            assert forbidden.headers["cache-control"] == "no-store"
        assert quizzes._answers == {} and quizzes.progress_repository._records == {}

        incomplete = await client.post(path + "/submit", headers=headers[0], json={"answers": payload["answers"][:4]})
        assert incomplete.status_code == 422 and quizzes._answers == {}
        completed = await client.post(path + "/submit", headers=headers[0], json=payload)
        assert completed.status_code == 200, completed.text
        assert completed.json()["submission"]["score"] == 60
        assert completed.json()["submission"]["quizStatus"] == "completed"
        answers, progress = deepcopy(quizzes._answers), deepcopy(quizzes.progress_repository._records)
        changed = {"answers": [{**answer, "userAnswer": "B"} for answer in payload["answers"]]}
        repeated = await client.post(path + "/submit", headers=headers[0], json=changed)
        assert repeated.status_code == 409
        assert repeated.json()["error"]["code"] == "ALREADY_SUBMITTED"
        assert quizzes._answers == answers and quizzes.progress_repository._records == progress

        result = await client.get(path + "/result", headers=headers[0])
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        details = result.json()["result"]
        assert (details["correctCount"], details["totalCount"], details["score"]) == (3, 5, 60)
        assert [question["userAnswer"] for question in details["questions"]] == ["B", "B", "B", "A", "A"]
        assert all(question["correctAnswer"] == "B" and question["explanation"] for question in details["questions"])
        foreign_result = await client.get(path + "/result", headers=headers[1])
        assert foreign_result.status_code == 404
        assert provider.calls == 1
