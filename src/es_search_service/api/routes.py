"""FastAPI routes for ES search service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from ..config import ServiceSettings, get_settings
from ..tasks import hybrid_search_task, text_search_task, vector_search_task

router = APIRouter()


class BaseSearchRequest(BaseModel):
    index_name: Optional[str] = None
    filters: Optional[List[Dict[str, Any]]] = None
    permission_filters: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="访问控制过滤，优先级高于匹配度 (bool.filter)",
    )
    source: Optional[List[str]] = Field(default=None, alias="_source")


class TextSearchRequest(BaseSearchRequest):
    query: str
    fields: Optional[List[str]] = None
    from_: int = Field(default=0, alias="from")
    size: int = Field(default=10, ge=1, le=200)
    highlight_fields: Optional[List[str]] = None


class VectorSearchRequest(BaseSearchRequest):
    query_vector: List[float]
    vector_field: Optional[str] = None
    size: int = Field(default=10, ge=1, le=200)
    num_candidates: Optional[int] = Field(default=None, ge=10, le=10000)


class HybridSearchRequest(BaseSearchRequest):
    query: str
    query_vector: List[float]
    fields: Optional[List[str]] = None
    vector_field: Optional[str] = None
    text_weight: float = Field(default=1.0, ge=0.0)
    vector_weight: float = Field(default=1.0, ge=0.0)
    from_: int = Field(default=0, alias="from")
    size: int = Field(default=10, ge=1, le=200)


class TaskSubmitResponse(BaseModel):
    task_id: str
    status: str


def get_settings_dep() -> ServiceSettings:
    return get_settings()


@router.get("/health")
def health(settings: ServiceSettings = Depends(get_settings_dep)) -> Dict[str, Any]:
    return {"status": "ok", "service": settings.service_name, "version": settings.api_version}


@router.post("/search/text", response_model=TaskSubmitResponse)
def search_text(payload: TextSearchRequest = Body(...)) -> TaskSubmitResponse:
    result = text_search_task.delay(
        payload.index_name,
        payload.query,
        payload.fields,
        payload.filters,
        payload.permission_filters,
        payload.size,
        payload.from_,
        payload.highlight_fields,
        payload.source,
    )
    return TaskSubmitResponse(task_id=result.id, status="submitted")


@router.post("/search/vector", response_model=TaskSubmitResponse)
def search_vector(payload: VectorSearchRequest = Body(...)) -> TaskSubmitResponse:
    result = vector_search_task.delay(
        payload.index_name,
        payload.query_vector,
        payload.vector_field,
        payload.size,
        payload.num_candidates,
        payload.filters,
        payload.permission_filters,
        payload.source,
    )
    return TaskSubmitResponse(task_id=result.id, status="submitted")


@router.post("/search/hybrid", response_model=TaskSubmitResponse)
def search_hybrid(payload: HybridSearchRequest = Body(...)) -> TaskSubmitResponse:
    result = hybrid_search_task.delay(
        payload.index_name,
        payload.query,
        payload.query_vector,
        payload.fields,
        payload.vector_field,
        payload.text_weight,
        payload.vector_weight,
        payload.size,
        payload.from_,
        payload.filters,
        payload.permission_filters,
        payload.source,
    )
    return TaskSubmitResponse(task_id=result.id, status="submitted")


@router.get("/tasks/{task_id}")
def task_status(task_id: str) -> Dict[str, Any]:
    from ..tasks import celery_app

    async_result = celery_app.AsyncResult(task_id)
    info: Any = async_result.result if async_result.result else None
    return {"id": task_id, "state": async_result.state, "result": info}
