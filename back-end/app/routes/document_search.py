"""TK-044: authenticated keyword lookup within an open learning topic."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies.auth import get_current_user
from app.schemas.auth import ErrorResponse
from app.schemas.document_search import ChunkSearchItem, ChunkSearchResponse
from app.services.document_retrieval import DocumentRetrievalService
from app.utils.errors import AppError
from app.utils.keywords import MAX_QUERY_LENGTH


router = APIRouter(
    prefix="/api/catalog", tags=["catalog"], dependencies=[Depends(get_current_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)


def get_service(request: Request) -> DocumentRetrievalService:
    service = request.app.state.document_retrieval_service
    if service is None:
        raise AppError(503, "SOURCES_UNAVAILABLE", "Chưa có kết nối dữ liệu tài liệu.")
    return service


@router.get(
    "/topics/{topic_id}/chunks", response_model=ChunkSearchResponse,
    summary="Tìm đoạn tài liệu theo từ khóa trong chủ đề đang mở",
)
async def search_chunks(
    topic_id: Annotated[int, Path(ge=1, le=2**31 - 1)],
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
    service: Annotated[DocumentRetrievalService, Depends(get_service)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> ChunkSearchResponse:
    result = await service.search(topic_id, q, limit=limit)
    return ChunkSearchResponse(
        topic_id=result.topic_id, query=result.query, limit=result.limit,
        chunks=[ChunkSearchItem(
            id=match.chunk.id, document_id=match.chunk.document_id,
            document_title=match.chunk.document_title, topic_id=match.chunk.topic_id,
            chunk_index=match.chunk.chunk_index, content=match.chunk.content, score=match.score,
        ) for match in result.matches],
    )
