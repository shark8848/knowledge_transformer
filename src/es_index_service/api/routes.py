"""FastAPI routes for ES schema/index service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from ..config import ServiceSettings, get_settings
from ..tasks import (
    _apply_overrides,
    _load_mapping,
    alias_switch_task,
    bulk_ingest_task,
    create_index_task,
    ingest_docindex_task,
    rebuild_full_task,
    rebuild_partial_task,
)

router = APIRouter()


class MappingOverride(BaseModel):
    number_of_shards: Optional[int] = None
    number_of_replicas: Optional[int] = None
    refresh_interval: Optional[str] = None


class CreateIndexRequest(BaseModel):
    index_name: Optional[str] = None
    overrides: Optional[MappingOverride] = None


class AliasSwitchRequest(BaseModel):
    new_index: str
    old_index: Optional[str] = None
    read_alias: Optional[str] = None
    write_alias: Optional[str] = None


class BulkIngestRequest(BaseModel):
    index_name: Optional[str] = None
    refresh: Optional[str] = None
    docs: List[Dict[str, Any]]


class DocIndexIngestRequest(BaseModel):
    index_name: Optional[str] = None
    refresh: Optional[str] = None
    doc_index_list: List[Dict[str, Any]]


class RebuildFullRequest(BaseModel):
    source_alias: Optional[str] = None
    target_version: Optional[str] = None
    overrides: Optional[MappingOverride] = None


class RebuildPartialRequest(BaseModel):
    index_name: Optional[str] = None
    query: Dict[str, Any]
    docs: List[Dict[str, Any]]
    refresh: Optional[str] = None


def get_settings_dep() -> ServiceSettings:
    return get_settings()


@router.get("/health")
def health(settings: ServiceSettings = Depends(get_settings_dep)) -> Dict[str, Any]:
    return {"status": "ok", "service": settings.service_name, "version": settings.api_version}


@router.post("/schemas/render")
def render_schema(
    overrides: Optional[MappingOverride] = Body(None, embed=True),
    settings: ServiceSettings = Depends(get_settings_dep),
) -> Dict[str, Any]:
    try:
        mapping = _load_mapping(settings.es.mapping_path)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rendered = _apply_overrides(mapping, overrides.model_dump(exclude_none=True) if overrides else None)
    return {"mapping_applied": True, "index": settings.es.default_index, "mapping": rendered}


@router.post("/indices/create")
def create_index(payload: CreateIndexRequest) -> Dict[str, Any]:
    result = create_index_task.delay(
        payload.index_name,
        payload.overrides.model_dump(exclude_none=True) if payload.overrides else None,
    )
    return {"task_id": result.id, "status": "submitted"}


@router.post("/indices/alias/switch")
def alias_switch(payload: AliasSwitchRequest) -> Dict[str, Any]:
    result = alias_switch_task.delay(
        payload.new_index,
        payload.read_alias,
        payload.write_alias,
        payload.old_index,
    )
    return {"task_id": result.id, "status": "submitted"}


@router.post("/ingest/bulk")
def bulk_ingest(payload: BulkIngestRequest) -> Dict[str, Any]:
    result = bulk_ingest_task.delay(payload.index_name, payload.docs, payload.refresh)
    return {"task_id": result.id, "status": "submitted"}


@router.post("/ingest/docindex")
def ingest_docindex(payload: DocIndexIngestRequest) -> Dict[str, Any]:
    result = ingest_docindex_task.delay(payload.doc_index_list, payload.index_name, payload.refresh)
    return {"task_id": result.id, "status": "submitted"}


@router.post("/indices/rebuild")
def rebuild_full(payload: RebuildFullRequest) -> Dict[str, Any]:
    result = rebuild_full_task.delay(
        payload.source_alias,
        payload.target_version,
        payload.overrides.model_dump(exclude_none=True) if payload.overrides else None,
    )
    return {"task_id": result.id, "status": "submitted"}


@router.post("/indices/rebuild/partial")
def rebuild_partial(payload: RebuildPartialRequest) -> Dict[str, Any]:
    result = rebuild_partial_task.delay(
        payload.index_name,
        payload.query,
        payload.docs,
        payload.refresh,
    )
    return {"task_id": result.id, "status": "submitted"}


@router.get("/tasks/{task_id}")
def task_status(task_id: str) -> Dict[str, Any]:
    from ..tasks import celery_app

    async_result = celery_app.AsyncResult(task_id)
    info: Any = None
    try:
        if async_result.result:
            info = async_result.result
    except Exception:  # backend may be disabled; return state only
        info = None
    return {"id": task_id, "state": async_result.state, "result": info}
