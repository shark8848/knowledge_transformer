"""Celery tasks for ES search service."""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from celery import Celery

from .clients import ESClient
from .config import ServiceSettings, get_settings

logger = logging.getLogger(__name__)

SETTINGS: ServiceSettings = get_settings()
celery_app = Celery(SETTINGS.service_name)
celery_app.conf.update(
    broker_url=SETTINGS.celery.broker_url,
    result_backend=SETTINGS.celery.result_backend,
    task_default_queue=SETTINGS.celery.default_queue,
    task_time_limit=SETTINGS.celery.task_time_limit_sec,
    worker_prefetch_multiplier=SETTINGS.celery.prefetch_multiplier,
)

ES = ESClient(SETTINGS)


@celery_app.task(name="es_search.text_search")
def text_search_task(
    index_name: Optional[str],
    query: str,
    fields: Optional[List[str]] = None,
    filters: Optional[Iterable[Dict[str, Any]]] = None,
    permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
    size: int = 10,
    from_: int = 0,
    highlight_fields: Optional[List[str]] = None,
    source: Optional[List[str]] = None,
) -> Dict[str, Any]:
    index = index_name or SETTINGS.es.read_alias or SETTINGS.es.default_index
    resp = ES.text_search(
        index,
        query,
        fields=fields,
        filters=filters,
        permission_filters=permission_filters,
        size=size,
        from_=from_,
        highlight_fields=highlight_fields,
        source=source,
    )
    if not resp.ok:
        raise RuntimeError(f"Text search failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body}


@celery_app.task(name="es_search.vector_search")
def vector_search_task(
    index_name: Optional[str],
    query_vector: List[float],
    vector_field: Optional[str] = None,
    size: int = 10,
    num_candidates: Optional[int] = None,
    filters: Optional[Iterable[Dict[str, Any]]] = None,
    permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
    source: Optional[List[str]] = None,
) -> Dict[str, Any]:
    index = index_name or SETTINGS.es.read_alias or SETTINGS.es.default_index
    resp = ES.vector_search(
        index,
        query_vector,
        vector_field=vector_field,
        size=size,
        num_candidates=num_candidates,
        filters=filters,
        permission_filters=permission_filters,
        source=source,
    )
    if not resp.ok:
        raise RuntimeError(f"Vector search failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body}


@celery_app.task(name="es_search.hybrid_search")
def hybrid_search_task(
    index_name: Optional[str],
    query: str,
    query_vector: List[float],
    fields: Optional[List[str]] = None,
    vector_field: Optional[str] = None,
    text_weight: float = 1.0,
    vector_weight: float = 1.0,
    size: int = 10,
    from_: int = 0,
    filters: Optional[Iterable[Dict[str, Any]]] = None,
    permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
    source: Optional[List[str]] = None,
) -> Dict[str, Any]:
    index = index_name or SETTINGS.es.read_alias or SETTINGS.es.default_index
    resp = ES.hybrid_search(
        index,
        query,
        query_vector,
        fields=fields,
        vector_field=vector_field,
        text_weight=text_weight,
        vector_weight=vector_weight,
        size=size,
        from_=from_,
        filters=filters,
        permission_filters=permission_filters,
        source=source,
    )
    if not resp.ok:
        raise RuntimeError(f"Hybrid search failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body}
