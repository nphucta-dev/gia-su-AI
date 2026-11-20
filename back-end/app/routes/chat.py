"""API chat riêng từng tài khoản; model chỉ được gọi qua service ở backend."""

from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query, Request
from app.dependencies.auth import get_current_user
from app.dependencies.quota import require_ai_quota
from app.repositories.user_repository import User
from app.routes.auth import require_json
from app.schemas.auth import ErrorResponse
from app.schemas.chat import (
    ChatMessageListResponse, ChatReplyResponse, ChatSessionListResponse, ChatSessionResponse,
    CreateChatSessionRequest, RequestFullSolutionRequest, SendChatMessageRequest,
    RequestExplanation, UpdateFeedbackRequest, ChatMessageResponse,
)
from app.services.chat_service import ChatService
from app.schemas.chat import (
    ChatMessageListResponse, ChatMessageResponse, ChatReplyResponse, ChatSessionListResponse, ChatSessionResponse,
    CreateChatSessionRequest, RequestFullSolutionRequest, SendChatMessageRequest, UpdateMessageFeedbackRequest,

    ChatMessageListResponse, ChatMessageSourcesResponse, ChatReplyResponse, ChatSessionListResponse,
    ChatSessionResponse, CreateChatSessionRequest, RequestFullSolutionRequest, SendChatMessageRequest,
)



router = APIRouter(prefix="/api/chat", tags=["chat"], responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 502, 503, 504)})
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionId = Annotated[int, Path(ge=1, le=2**31 - 1)]
Offset = Annotated[int, Query(ge=0, le=100000)]


def get_service(request: Request) -> ChatService:
    return request.app.state.chat_service


Service = Annotated[ChatService, Depends(get_service)]


@router.post("/sessions", status_code=201, response_model=ChatSessionResponse, dependencies=[Depends(require_json)], summary="Tạo phiên chat theo chủ đề đang mở")
async def create_session(payload: CreateChatSessionRequest, user: CurrentUser, service: Service) -> ChatSessionResponse:
    return await service.create_session(user, payload.topic_id, payload.title)


@router.get("/sessions", response_model=ChatSessionListResponse, summary="Lịch sử phiên chat của tài khoản hiện tại")
async def list_sessions(user: CurrentUser, service: Service, limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Offset = 0) -> ChatSessionListResponse:
    return await service.list_sessions(user, limit=limit, offset=offset)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(session_id: SessionId, user: CurrentUser, service: Service) -> ChatSessionResponse:
    return await service.get_session(user, session_id)


@router.get("/sessions/{session_id}/messages", response_model=ChatMessageListResponse, summary="Tin nhắn trong phiên chat của chính mình")
async def list_messages(session_id: SessionId, user: CurrentUser, service: Service, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Offset = 0) -> ChatMessageListResponse:
    return await service.list_messages(user, session_id, limit=limit, offset=offset)


@router.post("/sessions/{session_id}/messages", status_code=201, response_model=ChatReplyResponse, dependencies=[Depends(require_json), Depends(require_ai_quota)], summary="Lưu câu hỏi và gọi gia sư với ngữ cảnh gần nhất")
async def send_message(session_id: SessionId, payload: SendChatMessageRequest, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.send_message(user, session_id, payload.content)


@router.post("/sessions/{session_id}/hints", status_code=201, response_model=ChatReplyResponse, dependencies=[Depends(require_ai_quota)], summary="Gợi ý tiếp theo; server quyết định mức 1–3")
async def next_hint(session_id: SessionId, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.next_hint(user, session_id)


@router.post(
    "/sessions/{session_id}/solution",
    status_code=201,
    response_model=ChatReplyResponse,
    dependencies=[Depends(require_json), Depends(require_ai_quota)],
    summary="Xem lời giải đầy đủ sau khi người học xác nhận",
)
async def request_full_solution(
    session_id: SessionId, payload: RequestFullSolutionRequest, user: CurrentUser, service: Service,
) -> ChatReplyResponse:
    return await service.request_full_solution(user, session_id, confirmed=payload.confirmed)


@router.post("/sessions/{session_id}/retry", status_code=201, response_model=ChatReplyResponse, summary="Thử lại câu hỏi chưa có phản hồi, không lưu câu hỏi lần nữa")
async def retry_message(session_id: SessionId, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.retry_message(user, session_id)


@router.post(
    "/sessions/{session_id}/explanations", status_code=201, response_model=ChatReplyResponse,
    dependencies=[Depends(require_json)], summary="Giải thích đơn giản hơn hoặc cho ví dụ theo hội thoại",
    description="Dùng ngữ cảnh phiên thuộc tài khoản đăng nhập, lưu một phản hồi assistant; giữ nguyên mức gợi ý và luồng xác nhận lời giải.",
    responses={415: {"model": ErrorResponse, "description": "Yêu cầu phải gửi JSON"}},
)
async def explain(session_id: SessionId, payload: RequestExplanation, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.explain(user, session_id, payload.mode)


@router.patch("/sessions/{session_id}/messages/{message_id}/feedback", response_model=ChatMessageResponse, dependencies=[Depends(require_json)])
async def update_feedback(
    session_id: SessionId, message_id: Annotated[int, Path(ge=1, le=2**31 - 1)],
    payload: UpdateFeedbackRequest, user: CurrentUser, service: Service,
) -> ChatMessageResponse:
    return await service.update_feedback(user, session_id, message_id, payload.feedback)


@router.get("/messages/{message_id}/sources", response_model=ChatMessageSourcesResponse, summary="Nguồn trích dẫn hợp lệ của tin nhắn AI hoặc thông báo khi không có chunk")
async def get_message_sources(
    message_id: Annotated[int, Path(ge=1, le=2**31 - 1)],
    user: CurrentUser,
    service: Service,
) -> ChatMessageSourcesResponse:
    return await service.get_message_sources(user, message_id)

async def retry_last_message(session_id: SessionId, user: CurrentUser, service: Service) -> ChatReplyResponse:
    return await service.retry_last_message(user, session_id)

@router.patch(
    "/messages/{message_id}/feedback",
    response_model=ChatMessageResponse,
    dependencies=[Depends(require_json)],
    summary="Cập nhật đánh giá hữu ích (1) hoặc chưa hữu ích (-1) trên cùng tin nhắn AI",
)
async def update_message_feedback(
    message_id: Annotated[int, Path(ge=1, le=2**31 - 1)],
    payload: UpdateMessageFeedbackRequest,
    user: CurrentUser,
    service: Service,
) -> ChatMessageResponse:
    return await service.update_message_feedback(user, message_id, payload.feedback)
