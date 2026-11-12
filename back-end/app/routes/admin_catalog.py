"""API quản lý môn học/chủ đề chỉ dành cho tài khoản ADMIN đang hoạt động."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path, Request

from app.dependencies.auth import require_roles
from app.routes.auth import require_json
from app.schemas.admin_catalog import (
    AdminSubjectListResponse, AdminSubjectResponse,
    AdminTopicListResponse, AdminTopicResponse,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_catalog_service import AdminCatalogService


router = APIRouter(
    prefix="/api/admin", tags=["admin catalog"],
    dependencies=[Depends(require_roles("ADMIN"))],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 415, 422)},
)


def get_service(request: Request) -> AdminCatalogService:
    return request.app.state.admin_catalog_service


Service = Annotated[AdminCatalogService, Depends(get_service)]
CatalogId = Annotated[int, Path(ge=1, le=2**31 - 1)]


def body_docs(*, topic: bool = False, partial: bool = False) -> dict:
    properties: dict = {"name": {"type": "string", "minLength": 1, "maxLength": 180 if topic else 120}}
    if topic:
        properties.update({
            "subjectId": {"type": "integer", "minimum": 1, "maximum": 2**31 - 1},
            "chapterName": {"type": "string", "minLength": 1, "maxLength": 150},
            "description": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        })
        required = ["name", "subjectId", "chapterName"]
    else:
        properties["gradeLevel"] = {"type": "string", "minLength": 1, "maxLength": 50}
        required = ["name", "gradeLevel"]
    if partial:
        properties["isActive"] = {"type": "boolean"}
    schema = {"type": "object", "minProperties": 1, "additionalProperties": False, "properties": properties}
    if not partial:
        schema["required"] = required
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}}


@router.get("/subjects", response_model=AdminSubjectListResponse, summary="Tất cả môn học, kể cả môn đã tắt/chưa có chủ đề")
async def list_subjects(service: Service) -> AdminSubjectListResponse:
    return AdminSubjectListResponse(subjects=await service.list_subjects())


@router.post(
    "/subjects", status_code=201, response_model=AdminSubjectResponse,
    summary="Tạo môn học", dependencies=[Depends(require_json)], openapi_extra=body_docs(),
)
async def create_subject(service: Service, payload: Annotated[Any, Body()] = None) -> AdminSubjectResponse:
    return AdminSubjectResponse(subject=await service.save_subject(payload))


@router.patch(
    "/subjects/{subject_id}", response_model=AdminSubjectResponse,
    summary="Sửa môn học hoặc bật/tắt bằng isActive", dependencies=[Depends(require_json)],
    openapi_extra=body_docs(partial=True),
)
async def update_subject(subject_id: CatalogId, service: Service, payload: Annotated[Any, Body()] = None) -> AdminSubjectResponse:
    return AdminSubjectResponse(subject=await service.save_subject(payload, subject_id))


@router.get("/topics", response_model=AdminTopicListResponse, summary="Tất cả chủ đề, kể cả chủ đề và môn đã tắt")
async def list_topics(service: Service) -> AdminTopicListResponse:
    return AdminTopicListResponse(topics=await service.list_topics())


@router.post(
    "/topics", status_code=201, response_model=AdminTopicResponse,
    summary="Tạo chủ đề", dependencies=[Depends(require_json)], openapi_extra=body_docs(topic=True),
)
async def create_topic(service: Service, payload: Annotated[Any, Body()] = None) -> AdminTopicResponse:
    return AdminTopicResponse(topic=await service.save_topic(payload))


@router.patch(
    "/topics/{topic_id}", response_model=AdminTopicResponse,
    summary="Sửa chủ đề hoặc bật/tắt bằng isActive", dependencies=[Depends(require_json)],
    openapi_extra=body_docs(topic=True, partial=True),
)
async def update_topic(topic_id: CatalogId, service: Service, payload: Annotated[Any, Body()] = None) -> AdminTopicResponse:
    return AdminTopicResponse(topic=await service.save_topic(payload, topic_id))
