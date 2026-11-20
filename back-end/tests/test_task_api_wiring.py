"""Grading must update the same progress store exposed by the application."""

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.quiz_repository import InMemoryQuizRepository
from app.repositories.user_repository import InMemoryUserRepository
from test_quiz_validation import valid_payload


@pytest.mark.anyio
@pytest.mark.parametrize("inject_quiz_repository", [False, True])
async def test_submit_grade_is_visible_in_owned_progress_without_extra_wiring(inject_quiz_repository):
    users = InMemoryUserRepository()
    owner = await users.create(name="Người học", email="grading@example.com", password_hash="test-only", role="LEARNER")
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình")
    quiz_repository = InMemoryQuizRepository(catalog) if inject_quiz_repository else None
    app = create_app(
        user_repository=users, catalog_repository=catalog, quiz_repository=quiz_repository,
        settings=Settings(jwt_secret="task-wiring-tests-" + "x" * 40),
    )
    saved = await app.state.quiz_service.save_generated_quiz(owner, topic_id, "medium", valid_payload())
    token = app.state.token_service.create_access_token(owner.id).access_token
    payload = {"answers": [
        {"questionId": item.id, "userAnswer": "B" if index < 3 else "A"}
        for index, item in enumerate(saved.quiz.questions)
    ]}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        submission = await client.post(f"/api/quizzes/{saved.quiz.id}/submit", json=payload)
        assert submission.status_code == 200, submission.text
        assert submission.json()["submission"]["status"] == "accepted"
        assert submission.json()["submission"]["score"] == 60
        progress = (await client.get("/api/progress")).json()
        assert len(progress["progress"]) == 1
        row = progress["progress"][0]
        assert row["topicId"] == topic_id
        assert (row["totalQuizzes"], row["correctCount"], row["totalCount"], row["masteryPercent"]) == (1, 3, 5, 60)
        assert row["lastStudiedAt"] is not None
        duplicate = await client.post(f"/api/quizzes/{saved.quiz.id}/submit", json=payload)
        assert duplicate.status_code == 409
        assert (await client.get("/api/progress")).json() == progress
        own_quiz = await client.get(f"/api/quizzes/{saved.quiz.id}")
        assert own_quiz.json()["quiz"]["status"] == "completed"
        assert "correctAnswer" not in own_quiz.text and "explanation" not in own_quiz.text
