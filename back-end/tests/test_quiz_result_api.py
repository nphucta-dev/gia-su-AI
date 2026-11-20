"""TK-061: API kết quả quiz trả từng lựa chọn, đúng/sai, explanation."""

import pytest

from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.quiz_repository import InMemoryQuizRepository
from app.repositories.user_repository import User
from app.schemas.quiz import SubmitQuizAnswersRequest, SubmittedAnswerInput
from app.services.quiz_service import QuizService
from app.utils.errors import AppError


def make_user(user_id: int) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        name=f"User {user_id}",
        password_hash="hash",
        role="LEARNER",
        created_at="2026-11-20T00:00:00Z",
        is_active=True,
        birth_year=2002,
    )


def sample_generated_payload():
    return {
        "questions": [
            {
                "question_text": f"Câu hỏi {idx}",
                "options": {"A": "Đáp án A", "B": "Đáp án B", "C": "Đáp án C", "D": "Đáp án D"},
                "correct_answer": "A",
                "explanation": f"Giải thích chi tiết cho câu {idx}.",
            }
            for idx in range(1, 6)
        ]
    }


@pytest.mark.anyio
async def test_get_quiz_result_blocks_unsubmitted_and_returns_full_details_after_submit():
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phép cộng")
    repo = InMemoryQuizRepository(catalog)
    service = QuizService(repo)
    owner = make_user(1)
    other = make_user(2)

    created = (await service.save_generated_quiz(owner, topic_id, "easy", sample_generated_payload())).quiz

    # Chưa nộp bài không được lộ đáp án đúng / explanation
    with pytest.raises(AppError) as unsubmitted:
        await service.get_quiz_result(owner, created.id)
    assert unsubmitted.value.status_code == 409
    assert unsubmitted.value.code == "QUIZ_NOT_COMPLETED"

    # Nộp bài: đúng 3 câu, sai 2 câu
    choices = ["A", "A", "A", "B", "C"]
    payload = SubmitQuizAnswersRequest(answers=[
        SubmittedAnswerInput(questionId=q.id, userAnswer=choice)
        for q, choice in zip(created.questions, choices)
    ])
    await service.submit_answers(owner, created.id, payload)

    res = (await service.get_quiz_result(owner, created.id)).result
    assert res.correct_count == 3
    assert res.total_count == 5
    assert res.score == 60.0
    assert [(q.user_answer, q.correct_answer, q.is_correct) for q in res.questions] == [
        ("A", "A", True),
        ("A", "A", True),
        ("A", "A", True),
        ("B", "A", False),
        ("C", "A", False),
    ]
    assert res.questions[0].explanation == "Giải thích chi tiết cho câu 1."

    # Tài khoản khác không xem được
    with pytest.raises(AppError) as forbidden:
        await service.get_quiz_result(other, created.id)
    assert forbidden.value.status_code == 404
