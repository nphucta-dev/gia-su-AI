"""Quiz reads are private to the authenticated account, including their questions."""

from typing import Annotated
from fastapi import APIRouter, Depends, Path, Request
from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.routes.auth import require_json
from app.schemas.auth import ErrorResponse
from app.schemas.quiz import GenerateQuizRequest, QuizResponse, QuizResultResponse, QuizSubmissionResponse, SubmitQuizAnswersRequest
from app.services.quiz_service import QuizService
from app.utils.errors import AppError
from app.schemas.quiz import QuizResponse, QuizResultResponse, QuizSubmissionResponse, SubmitQuizAnswersRequest




router = APIRouter(
    prefix="/api/quizzes", tags=["quiz"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)},
)
CurrentUser = Annotated[User, Depends(get_current_user)]
QuizId = Annotated[int, Path(ge=1, le=2**31 - 1)]


def get_service(request: Request) -> QuizService:
    return request.app.state.quiz_service


@router.post("", status_code=201, response_model=QuizResponse, dependencies=[Depends(require_json)], summary="Tạo 5 câu luyện tập bằng model AI")
async def generate_quiz(
    payload: GenerateQuizRequest, user: CurrentUser, service: Annotated[QuizService, Depends(get_service)],
) -> QuizResponse:
    return await service.generate_quiz(user, payload.topic_id, payload.difficulty)


@router.get("/{quiz_id}", response_model=QuizResponse, summary="Đọc bài luyện tập của chính mình")
async def get_quiz(
    quiz_id: QuizId, user: CurrentUser, service: Annotated[QuizService, Depends(get_service)],
) -> QuizResponse:
    return await service.get_quiz(user, quiz_id)


@router.get("/{quiz_id}/result", response_model=QuizResultResponse, summary="Kết quả và giải thích của bài đã nộp")
async def get_quiz_result(
    quiz_id: QuizId, user: CurrentUser, service: Annotated[QuizService, Depends(get_service)],
) -> QuizResultResponse:
    return await service.get_result(user, quiz_id)


@router.post(
    "/{quiz_id}/submit",
    response_model=QuizSubmissionResponse,
    dependencies=[Depends(require_json)],
    summary="Nộp và chấm bài luyện tập một lần",
)
async def submit_quiz_answers(
    quiz_id: QuizId,
    payload: SubmitQuizAnswersRequest,
    user: CurrentUser,
    service: Annotated[QuizService, Depends(get_service)],
) -> QuizSubmissionResponse:
    return await service.submit_answers(user, quiz_id, payload)


@router.post("/{quiz_id}/grade", response_model=QuizSubmissionResponse, summary="Chấm một lần các câu trả lời đã lưu trước TK-059")
async def grade_saved_quiz(
    quiz_id: QuizId, request: Request, user: CurrentUser,
    service: Annotated[QuizService, Depends(get_service)],
) -> QuizSubmissionResponse:
    if await request.body():
        raise AppError(422, "VALIDATION_ERROR", "API chấm câu trả lời đã lưu không nhận đáp án mới.")
    return await service.grade_saved_answers(user, quiz_id)
