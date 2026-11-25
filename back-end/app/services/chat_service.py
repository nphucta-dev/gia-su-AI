"""Phiên và tin nhắn thật, ngữ cảnh riêng tư, điều phối thang gợi ý 1–3."""

import asyncio
from collections.abc import Awaitable, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any
import unicodedata
from sqlalchemy.exc import SQLAlchemyError
from app.config import Settings
from app.prompts import SocraticTopic
from app.repositories.chat_repository import ChatChangedError, ChatMessageRecord, ChatRepository, ChatSessionRecord
from app.repositories.document_repository import DocumentChunkRecord, DocumentRepository
from app.repositories.ai_quota_repository import InMemoryAiQuotaRepository
from app.repositories.user_repository import User
from app.schemas.chat import (
    ChatMessageItem, ChatMessageListResponse, ChatReplyResponse, ChatSessionItem,
    ChatSessionListResponse, ChatSessionResponse,
    ChatMessageResponse,
)
from app.services.chat_context import build_chat_messages, build_explanation_messages, build_full_solution_messages, redact_sensitive_text
from app.services.ai_quota import AiQuotaService
from app.services.document_retrieval import DocumentRetrievalService
from app.services.llm_client import LLMClient
from app.utils.errors import AppError
from app.utils.async_tasks import finish_pending_task
from app.utils.keywords import text_terms
from app.utils.text import has_visible_text
from collections.abc import Sequence
from app.repositories.chat_repository import (
    ChatChangedError, ChatMessageRecord, ChatRepository, ChatSessionRecord, FeedbackTargetError,
)
from app.schemas.chat import (
    ChatMessageItem, ChatMessageListResponse, ChatMessageResponse, ChatReplyResponse, ChatSessionItem,
    ChatSessionListResponse, ChatSessionResponse,

    ChatMessageItem, ChatMessageListResponse, ChatMessageSourcesResponse, ChatReplyResponse,
    ChatSessionItem, ChatSessionListResponse, ChatSessionResponse, ChatSourceRefItem,
)
from app.services.chat_context import build_chat_messages, build_full_solution_messages, redact_sensitive_text
from app.services.quota_service import DEFAULT_DAILY_AI_LIMIT, QuotaService




def session_item(record: ChatSessionRecord) -> ChatSessionItem:
    values = asdict(record)
    return ChatSessionItem(**{name: values[name] for name in ChatSessionItem.model_fields})


def message_item(record: ChatMessageRecord, available: set[tuple[int, int]] | None = None) -> ChatMessageItem:
    values = asdict(record)
    refs = []
    for source in record.source_refs:
        if not isinstance(source, dict):
            continue
        document_id = source.get("documentId", source.get("document_id"))
        chunk_id = source.get("chunkId", source.get("chunk_id"))
        title = source.get("title")
        chunk_index = source.get("chunkIndex", source.get("chunk_index", 0))
        if type(document_id) is not int or document_id <= 0 or type(chunk_id) is not int or chunk_id <= 0 or not isinstance(title, str) or type(chunk_index) is not int or chunk_index < 0:
            continue
        refs.append({"documentId": document_id, "chunkId": chunk_id, "title": title,
                     "chunkIndex": chunk_index, "available": (document_id, chunk_id) in available if available is not None else True})
    values["source_refs"] = refs
    values["sources_status"] = "available" if any(item["available"] for item in refs) else "unavailable" if refs else "none"
    return ChatMessageItem(**values)


def missing_session() -> AppError:
    return AppError(404, "CHAT_SESSION_NOT_FOUND", "Không tìm thấy phiên chat của bạn.")


def changed_session() -> AppError:
    return AppError(409, "CHAT_CHANGED", "Hội thoại vừa được cập nhật. Hãy xem lại lịch sử trước khi gửi tiếp.")


async def _commit_message(operation: Awaitable[ChatMessageRecord | None]) -> ChatMessageRecord | None:
    # A cancelled HTTP request must not release admission before its SQL worker commits.
    pending = asyncio.ensure_future(operation)
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        try:
            await finish_pending_task(pending)
        except Exception:
            pass
        raise


def validate_message_content(content: str) -> str:
    """Chặn câu hỏi rỗng, chỉ chứa khoảng trắng/ký tự vô hình hoặc ký tự điều khiển."""
    if not isinstance(content, str):
        raise AppError(
            422, "VALIDATION_ERROR", "Nội dung tin nhắn không hợp lệ.",
            {"content": "Nội dung tin nhắn không hợp lệ."},
        )
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in content):
        raise AppError(
            422, "VALIDATION_ERROR", "Nội dung tin nhắn không hợp lệ.",
            {"content": "Nội dung tin nhắn không hợp lệ."},
        )
    cleaned = content.strip()
    if not has_visible_text(cleaned):
        raise AppError(
            422, "VALIDATION_ERROR", "Vui lòng nhập câu hỏi trước khi gửi.",
            {"content": "Vui lòng nhập câu hỏi trước khi gửi."},
        )
    return cleaned



MAX_HINT_LEVEL = 3
MAX_SOURCE_REFS = 5


def build_source_refs(chunks: Sequence[DocumentChunkRecord], *, limit: int = MAX_SOURCE_REFS) -> list[dict[str, Any]]:
    """Chuẩn hóa danh sách nguồn tham khảo để lưu vào chat_messages.source_refs."""
    refs: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for chunk in chunks:
        key = (chunk.document_id, chunk.id)
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {
            "document_id": chunk.document_id,
            "chunk_id": chunk.id,
            "title": chunk.document_title,
            "chunk_index": chunk.chunk_index,
        }
        if chunk.source_url:
            item["source_url"] = chunk.source_url
        refs.append(item)
        if len(refs) >= limit:
            break
    return refs


def resolve_next_hint_level(history: Sequence[ChatMessageRecord]) -> int:
    """Điều phối thang gợi ý 1–3 cho câu hỏi gần nhất; server quyết định mức tiếp theo."""
    question = next((item for item in reversed(history) if item.role == "user"), None)
    if question is None:
        raise AppError(409, "CHAT_QUESTION_REQUIRED", "Hãy gửi một câu hỏi trước khi xin gợi ý.")
    levels = [
        item.hint_level
        for item in history
        if item.role == "assistant" and item.id > question.id and item.hint_level is not None
    ]
    level = max(levels, default=0) + 1
    if level > MAX_HINT_LEVEL:
        raise AppError(409, "HINT_LIMIT_REACHED", "Bạn đã nhận đủ 3 mức gợi ý cho câu hỏi này.")
    return level


RETRYABLE_LLM_CODES = frozenset({"LLM_TIMEOUT", "LLM_RATE_LIMITED", "LLM_UNAVAILABLE", "LLM_INVALID_RESPONSE"})

NO_SOURCE_NOTICE = "Chưa có tài liệu nguồn phù hợp cho phản hồi này."
RETRYABLE_LLM_CODES = frozenset({"LLM_TIMEOUT", "LLM_RATE_LIMITED", "LLM_UNAVAILABLE", "LLM_INVALID_RESPONSE"})

class ChatService:
    def __init__(
        self, repository: ChatRepository, client: LLMClient, settings: Settings, document_repository: DocumentRepository | None = None, *,
        retrieval_service: DocumentRetrievalService | None = None, quota_service: AiQuotaService | None = None,
        daily_ai_limit: int = DEFAULT_DAILY_AI_LIMIT,
    ) -> None:
        self._repository = repository
        self._client = client
        self._settings = settings
        self._retrieval = retrieval_service or (DocumentRetrievalService(document_repository) if document_repository is not None else None)
        self._quota = quota_service or AiQuotaService(InMemoryAiQuotaRepository(repository), limit=daily_ai_limit)
        self._busy: set[int] = set()

    @asynccontextmanager
    async def _generating(self, session_id: int):
        if session_id in self._busy:
            raise AppError(409, "CHAT_BUSY", "Phiên chat đang chờ phản hồi. Vui lòng thử lại sau.")
        self._busy.add(session_id)
        try:
            yield
        finally:
            self._busy.discard(session_id)

    @asynccontextmanager
    async def _operation(self, user_id: int, session_id: int):
        async with self._generating(session_id):
            async with self._quota.generation(user_id):
                yield

    async def _find(self, user_id: int, session_id: int) -> ChatSessionRecord:
        record = await self._repository.find_session(user_id, session_id)
        if record is None:
            raise missing_session()
        return record

    @staticmethod
    def _require_open(session: ChatSessionRecord) -> None:
        if not session.topic_active or not session.subject_active:
            raise AppError(409, "TOPIC_CLOSED", "Môn học hoặc chủ đề đã tắt. Bạn vẫn có thể xem lịch sử.")

    async def create_session(self, user: User, topic_id: int, title: str | None) -> ChatSessionResponse:
        if title is not None:
            if any(unicodedata.category(char) in {"Cc", "Cs"} and not char.isspace() for char in title):
                raise AppError(422, "VALIDATION_ERROR", "Tiêu đề phiên chat không hợp lệ.")
            title = " ".join(title.split()) or None
        record = await self._repository.create_session(user.id, topic_id, title)
        if record is None:
            raise AppError(404, "TOPIC_NOT_FOUND", "Chủ đề không tồn tại hoặc chưa được mở.")
        return ChatSessionResponse(session=session_item(record))

    async def list_sessions(self, user: User, *, limit: int, offset: int) -> ChatSessionListResponse:
        records = await self._repository.list_sessions(user.id, limit=limit + 1, offset=offset)
        return ChatSessionListResponse(
            sessions=[session_item(item) for item in records[:limit]], limit=limit, offset=offset,
            has_more=len(records) > limit,
        )

    async def get_session(self, user: User, session_id: int) -> ChatSessionResponse:
        return ChatSessionResponse(session=session_item(await self._find(user.id, session_id)))

    async def list_messages(self, user: User, session_id: int, *, limit: int, offset: int) -> ChatMessageListResponse:
        session = await self._find(user.id, session_id)
        records = await self._repository.list_messages(user.id, session_id, limit=limit + 1, offset=offset)
        return ChatMessageListResponse(
            session=session_item(session), messages=await self._public_messages(session, records[:limit]),
            limit=limit, offset=offset, has_more=len(records) > limit,
        )

    def _privacy(self, user: User) -> dict:
        # Các giá trị này chỉ dùng để lọc bản sao; không đưa tài khoản vào payload LLM.
        return {
            "known_name": user.name, "known_email": user.email,
            "secret_values": (user.password_hash, self._settings.llm_api_key, self._settings.jwt_secret),
        }

    async def send_message(self, user: User, session_id: int, content: str) -> ChatReplyResponse:
        session = await self._find(user.id, session_id)
        self._require_open(session)
        content = validate_message_content(content)
        async with self._operation(user.id, session_id):
            saved = await _commit_message(self._repository.append_user_message(user.id, session_id, content))
            if saved is None:
                raise missing_session()
            try:
                response = await self._reply(user, session, expected_last_id=saved.id, hint_level=1)
            except AppError as error:
                fields = {**(error.fields or {}), "messageSaved": "true", "sessionId": str(session_id), "userMessageId": str(saved.id)}
                raise AppError(error.status_code, error.code, error.message, fields, error.headers) from None
            response.user_message = message_item(saved)
            return response

    async def next_hint(self, user: User, session_id: int) -> ChatReplyResponse:
        session = await self._find(user.id, session_id)
        self._require_open(session)
        async with self._operation(user.id, session_id):
            history = await self._repository.context_messages(user.id, session_id, limit=24)
            level = resolve_next_hint_level(history)
            return await self._reply(user, session, expected_last_id=history[-1].id, hint_level=level, history=history)

    async def request_full_solution(self, user: User, session_id: int, *, confirmed: bool) -> ChatReplyResponse:
        session = await self._find(user.id, session_id)
        self._require_open(session)
        if confirmed is not True:
            raise AppError(
                422,
                "CONFIRMATION_REQUIRED",
                "Vui lòng xác nhận trước khi xem lời giải đầy đủ.",
                {"confirmed": "Bạn cần xác nhận trước khi xem lời giải đầy đủ."},
            )
        async with self._operation(user.id, session_id):
            history = await self._repository.context_messages(user.id, session_id, limit=24)
            question = next((item for item in reversed(history) if item.role == "user"), None)
            if question is None:
                raise AppError(409, "CHAT_QUESTION_REQUIRED", "Hãy gửi một câu hỏi trước khi xem lời giải.")
            return await self._reply(
                user, session, expected_last_id=history[-1].id,
                hint_level=None, is_full_solution=True, history=history,
            )

    async def retry_message(self, user: User, session_id: int) -> ChatReplyResponse:
        session = await self._find(user.id, session_id)
        self._require_open(session)
        async with self._operation(user.id, session_id):
            history = await self._repository.context_messages(user.id, session_id, limit=24)
            if not history or not any(item.role == "user" for item in history):
                raise AppError(409, "CHAT_QUESTION_REQUIRED", "Hãy gửi một câu hỏi trước khi thử lại.")
            if history[-1].role != "user":
                raise AppError(409, "CHAT_REPLY_EXISTS", "Câu hỏi này đã có phản hồi. Hãy tải lại lịch sử.")
            return await self._reply(user, session, expected_last_id=history[-1].id, hint_level=1, history=history)

    async def explain(self, user: User, session_id: int, mode: str) -> ChatReplyResponse:
        if not isinstance(mode, str) or mode not in {"simplify", "example"}:
            raise AppError(422, "VALIDATION_ERROR", "Kiểu giải thích không hợp lệ.")
        try:
            session = await self._find(user.id, session_id)
            self._require_open(session)
            async with self._operation(user.id, session_id):
                history = await self._repository.context_messages(user.id, session_id, limit=24)
                if not history or not any(item.role == "user" for item in history):
                    raise AppError(409, "CHAT_QUESTION_REQUIRED", "Hãy gửi một câu hỏi trước khi xin giải thích.")
                return await self._reply(user, session, expected_last_id=history[-1].id, explanation=mode, history=history)
        except SQLAlchemyError:
            raise AppError(
                503, "CHAT_UNAVAILABLE", "Chưa thể hoàn tất yêu cầu giải thích. Vui lòng tải lại hội thoại và thử lại.",
            ) from None

    async def update_feedback(self, user: User, session_id: int, message_id: int, feedback: int | None) -> ChatMessageResponse:
        session = await self._find(user.id, session_id)
        if feedback is not None and (type(feedback) is not int or feedback not in {-1, 1}):
            raise AppError(422, "VALIDATION_ERROR", "Đánh giá phải là -1, 1 hoặc null.")
        record = await self._repository.update_feedback(user.id, session_id, message_id, feedback)
        if record is None:
            raise AppError(404, "CHAT_MESSAGE_NOT_FOUND", "Không tìm thấy phản hồi của gia sư trong phiên của bạn.")
        return ChatMessageResponse(message=(await self._public_messages(session, [record]))[0])

    async def _public_messages(self, session: ChatSessionRecord, records: list[ChatMessageRecord]) -> list[ChatMessageItem]:
        if not any(record.source_refs for record in records):
            return [message_item(record) for record in records]
        available = set()
        if self._retrieval is not None:
            try:
                available = {(chunk.document_id, chunk.id) for chunk in await self._retrieval.list_eligible_chunks(session.topic_id)}
            except Exception:
                # A temporary source outage must not hide the user's stored conversation.
                pass
        return [message_item(record, available) for record in records]

    async def _sources(self, user: User, session: ChatSessionRecord, history: list[ChatMessageRecord]) -> tuple[list[dict] | None, tuple[dict, ...]]:
        if self._retrieval is None:
            return None, ()
        question = next(item.content for item in reversed(history) if item.role == "user")
        safe_question = redact_sensitive_text(question, **self._privacy(user))
        terms = list(dict.fromkeys(text_terms(safe_question)))[:20]
        query = " ".join(terms)[:400]
        if not query:
            return [], ()
        found = await self._retrieval.search(session.topic_id, query, limit=3)
        sources, refs = [], []
        for match in found.matches:
            chunk = match.chunk
            sources.append({"title": chunk.document_title, "content": chunk.content})
            refs.append({"documentId": chunk.document_id, "chunkId": chunk.id,
                         "title": chunk.document_title, "chunkIndex": chunk.chunk_index})
        return sources, tuple(refs)

    async def _reply(
        self, user: User, session: ChatSessionRecord, *, expected_last_id: int,
        hint_level: int | None = None, is_full_solution: bool = False,
        explanation: str | None = None,
        history: list[ChatMessageRecord] | None = None,
    ) -> ChatReplyResponse:
        if history is None:
            history = await self._repository.context_messages(user.id, session.id, limit=24)
        if not history or history[-1].id != expected_last_id:
            raise changed_session()
        topic = SocraticTopic(
            subject_name=session.subject_name, topic_name=session.topic_name, grade_level=session.grade_level,
            chapter_name=session.chapter_name, description=session.topic_description,
        )
        history_payload = [{"role": item.role, "content": item.content} for item in history]
        sources, source_refs = await self._sources(user, session, history)
        try:
            if is_full_solution:
                messages = build_full_solution_messages(topic=topic, history=history_payload, sources=sources, **self._privacy(user))
            elif explanation is not None:
                messages = build_explanation_messages(topic=topic, history=history_payload, mode=explanation, sources=sources, **self._privacy(user))
            else:
                messages = build_chat_messages(
                    topic=topic, history=history_payload, hint_level=hint_level or 1, sources=sources, **self._privacy(user),
                )
        except ValueError:
            raise AppError(422, "INVALID_CHAT_CONTEXT", "Ngữ cảnh hội thoại chưa hợp lệ. Tin nhắn đã được lưu.") from None
        try:
            reply = await self._client.generate(messages)
        except AppError as error:
            raise AppError(error.status_code, error.code, error.message + " Tin nhắn đã gửi vẫn được lưu trong lịch sử.", headers=error.headers) from None
        try:
            content = redact_sensitive_text(reply.content, **self._privacy(user))
        except ValueError:
            raise AppError(502, "LLM_INVALID_RESPONSE", "Gia sư chưa trả về nội dung hợp lệ. Câu hỏi của bạn đã được lưu.") from None
        if not has_visible_text(content) or len(content) > 8000:
            raise AppError(502, "LLM_INVALID_RESPONSE", "Gia sư chưa trả về nội dung hợp lệ. Câu hỏi của bạn đã được lưu.")
        try:
            saved = await _commit_message(self._repository.append_assistant_message(
                user.id, session.id, content, hint_level=hint_level, is_full_solution=is_full_solution,
                token_count=reply.token_count, expected_last_id=expected_last_id, source_refs=source_refs,
            ))
        except ChatChangedError:
            raise changed_session() from None
        except SQLAlchemyError:
            raise AppError(503, "CHAT_SAVE_FAILED", "Chưa thể lưu phản hồi. Câu hỏi của bạn vẫn còn trong lịch sử.") from None
        if saved is None:
            raise missing_session()
        current = await self._find(user.id, session.id)
        return ChatReplyResponse(session=session_item(current), assistant_message=(await self._public_messages(current, [saved]))[0])


    async def get_message_sources(self, user: User, message_id: int) -> ChatMessageSourcesResponse:
        """TK-049: Trả về danh sách source_refs hợp lệ và ghi rõ khi không có chunk phù hợp."""
        try:
            record = await self._repository.find_message(user.id, message_id)
        except SQLAlchemyError:
            raise AppError(503, "SOURCES_UNAVAILABLE", "Chưa thể tải nguồn tham khảo. Vui lòng thử lại.") from None
        if record is None:
            raise AppError(404, "CHAT_MESSAGE_NOT_FOUND", "Không tìm thấy tin nhắn của bạn.")
        refs = sanitize_source_refs(record.source_refs) if record.role == "assistant" else []
        available = set()
        if refs and self._retrieval is not None:
            session = await self._find(user.id, record.session_id)
            try:
                available = {(chunk.document_id, chunk.id) for chunk in await self._retrieval.list_eligible_chunks(session.topic_id)}
            except SQLAlchemyError:
                raise AppError(503, "SOURCES_UNAVAILABLE", "Chưa thể tải nguồn tham khảo. Vui lòng thử lại.") from None
        for ref in refs:
            ref.available = (ref.document_id, ref.chunk_id) in available
        has_sources = any(ref.available for ref in refs)
        notice = None if refs and all(ref.available for ref in refs) else (
            "Một số tài liệu nguồn hiện không khả dụng." if has_sources else
            "Tài liệu nguồn đã tắt hoặc hiện không còn khả dụng." if refs else NO_SOURCE_NOTICE
        )
        return ChatMessageSourcesResponse(
            message_id=record.id,
            has_sources=has_sources,
            source_refs=refs,
            notice=notice,
        )


    async def retry_last_message(self, user: User, session_id: int) -> ChatReplyResponse:
        """TK-029: Thử gọi lại AI cho câu hỏi gần nhất đã lưu khi lượt trước gặp lỗi mạng/429/timeout."""
        session = await self._find(user.id, session_id)
        self._require_open(session)
        async with self._operation(user.id, session_id):
            history = await self._repository.context_messages(user.id, session_id, limit=24)
            if not history or history[-1].role != "user":
                raise AppError(409, "CHAT_RETRY_NOT_NEEDED", "Không có câu hỏi nào đang chờ phản hồi để thử lại.")
            pending_question = history[-1]
            response = await self._reply(
                user, session, expected_last_id=pending_question.id, hint_level=1, history=history,
            )
            response.user_message = message_item(pending_question)
            return response


    async def update_message_feedback(self, user: User, message_id: int, feedback: int) -> ChatMessageResponse:
        """TK-074: Cập nhật feedback (-1/1) trên cùng tin nhắn assistant, không tạo bản ghi mới."""
        if feedback not in (-1, 1) or isinstance(feedback, bool):
            raise AppError(
                422, "VALIDATION_ERROR", "Giá trị đánh giá không hợp lệ.",
                {"feedback": "Đánh giá phải là 1 (hữu ích) hoặc -1 (chưa hữu ích)."},
            )
        try:
            updated = await self._repository.update_message_feedback(user.id, message_id, feedback)
        except FeedbackTargetError:
            raise AppError(409, "FEEDBACK_ASSISTANT_ONLY", "Chỉ được đánh giá phản hồi của gia sư AI.") from None
        if updated is None:
            raise AppError(404, "CHAT_MESSAGE_NOT_FOUND", "Không tìm thấy tin nhắn của bạn.")
        return ChatMessageResponse(message=message_item(updated))







def sanitize_source_refs(raw_refs: object) -> list[ChatSourceRefItem]:
    """TK-049: Lọc và chuẩn hóa danh sách source_refs hợp lệ, loại bỏ bản ghi lỗi/trùng."""
    if not isinstance(raw_refs, (list, tuple)):
        return []
    valid: list[ChatSourceRefItem] = []
    seen: set[tuple[int, int]] = set()
    for item in raw_refs:
        if not isinstance(item, dict):
            continue
        doc_id = item.get("document_id", item.get("documentId"))
        chunk_id = item.get("chunk_id", item.get("chunkId"))
        title = item.get("title")
        if (
            not isinstance(doc_id, int) or isinstance(doc_id, bool) or doc_id <= 0
            or not isinstance(chunk_id, int) or isinstance(chunk_id, bool) or chunk_id <= 0
            or not isinstance(title, str) or not title.strip()
        ):
            continue
        key = (doc_id, chunk_id)
        if key in seen:
            continue
        seen.add(key)
        chunk_index = item.get("chunk_index", item.get("chunkIndex"))
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool) or chunk_index < 0:
            chunk_index = None
        source_url = item.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            source_url = None
        valid.append(ChatSourceRefItem(
            document_id=doc_id,
            chunk_id=chunk_id,
            title=title.strip(),
            chunk_index=chunk_index,
            source_url=source_url,
        ))
    return valid
