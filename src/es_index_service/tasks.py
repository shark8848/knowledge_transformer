"""Celery tasks for ES schema/index service."""
from __future__ import annotations

import json
import logging
from pathlib import Path
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


# Field translation from external docIndex payload to ES schema (kb_chunks_v1_mapping.json)
DOCINDEX_TRANSLATION = {
    "zj_id": "primary_id",
    "docid": "knowledge_id",
    "attachId": "file_id",
    "doctitle": "title",
    "klg_type": "knowledge_type",
    "item_value": "content",
    "item_value_vector": "embedding",
    "item_value_img": "content_image",
    "item_values": "content_values",
    "itemvaluess": "content_values_s",
    "klg_user_ids": "knowledge_user_ids",
    "klg_role_ids": "knowledge_role_ids",
    "group_id": "chunk_id",
    "depar_id": "department_id",
    "org_id": "enterprise_id",
    "ep_id": "tenant_id",
    "ct_id": "knowledge_base_id",
    "ct_id0": "kb_tree_id_0",
    "ct_id1": "kb_tree_id_1",
    "ct_id2": "kb_tree_id_2",
    "ct_id3": "kb_tree_id_3",
    "parent_path_id": "parent_path_id",
    "city_id": "city_id",
    "up_city_id": "parent_city_id",
    "doc_status": "document_status",
    "life_status": "lifecycle_status",
    "crt_userid": "created_user_id",
    "tags": "tags",
    "keywords": "keywords",
    "summary": "summary",
    "faq": "faq",
    "rel_classify_id": "external_classify_id",
    "rel_klg_id": "external_knowledge_id",
    "rel_attach_id": "external_attach_id",
    "attributes": "attributes",
    "metaData": "metadata",
    "role": "visibility_scope",
    "deptPermission": "permitted_department_ids",
    "userPermission": "permitted_user_ids",
    "item_type": "item_type",
}


def _load_mapping(template_path: Path) -> Dict[str, Any]:
    if not template_path.exists():
        raise FileNotFoundError(f"Mapping template not found: {template_path}")
    with template_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _apply_overrides(body: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not overrides:
        return body
    result = json.loads(json.dumps(body))
    settings = result.setdefault("settings", {})
    if "number_of_shards" in overrides and overrides["number_of_shards"] is not None:
        settings["number_of_shards"] = overrides["number_of_shards"]
    if "number_of_replicas" in overrides and overrides["number_of_replicas"] is not None:
        settings["number_of_replicas"] = overrides["number_of_replicas"]
    if "refresh_interval" in overrides and overrides["refresh_interval"] is not None:
        settings["refresh_interval"] = overrides["refresh_interval"]
    return result


def _coerce_vector(value: Any) -> Optional[List[float]]:
    """Convert incoming vector payload to float list for dense_vector."""

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        try:
            return [float(v) for v in value]
        except Exception:  # pragma: no cover - defensive
            return None
    if isinstance(value, str):
        # try JSON or comma split
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [float(v) for v in parsed]
        except Exception:
            pass
        try:
            parts = [p for p in value.replace(";", ",").split(",") if p.strip()]
            return [float(p) for p in parts]
        except Exception:
            return None
    return None


def _transform_doc_index(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map upstream docIndex payload to kb_chunks schema fields."""

    transformed: Dict[str, Any] = {}
    for src, dest in DOCINDEX_TRANSLATION.items():
        if src not in raw:
            continue
        val = raw.get(src)
        if val is None:
            continue
        if dest == "embedding":
            vector = _coerce_vector(val)
            if vector is not None:
                transformed[dest] = vector
            continue
        transformed[dest] = val
    return transformed


@celery_app.task(name="es_schema.create_index")
def create_index_task(
    index_name: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    target = index_name or SETTINGS.es.default_index
    body = _load_mapping(SETTINGS.es.mapping_path)
    body = _apply_overrides(body, overrides)
    logger.info("Creating index", extra={"index": target, "overrides": overrides})
    resp = ES.create_index(target, body)
    if not resp.ok:
        raise RuntimeError(f"Create index failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body}


@celery_app.task(name="es_schema.alias_switch")
def alias_switch_task(
    new_index: str,
    read_alias: Optional[str] = None,
    write_alias: Optional[str] = None,
    old_index: Optional[str] = None,
) -> Dict[str, Any]:
    read_alias = read_alias or SETTINGS.es.read_alias
    write_alias = write_alias or SETTINGS.es.write_alias
    resp = ES.alias_switch(
        read_alias=read_alias,
        write_alias=write_alias,
        new_index=new_index,
        old_index=old_index,
    )
    if not resp.ok:
        raise RuntimeError(f"Alias switch failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body}


@celery_app.task(name="es_schema.bulk_ingest")
def bulk_ingest_task(
    index_name: Optional[str],
    docs: Iterable[Dict[str, Any]],
    refresh: Optional[str] = None,
) -> Dict[str, Any]:
    target = index_name or SETTINGS.es.write_alias or SETTINGS.es.default_index
    doc_list: List[Dict[str, Any]] = list(docs)
    if not doc_list:
        return {"status": 200, "body": {"took": 0, "ingested": 0}}
    resp = ES.bulk(target, doc_list, refresh=refresh)
    if not resp.ok:
        raise RuntimeError(f"Bulk ingest failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body}


@celery_app.task(name="es_schema.ingest_docindex")
def ingest_docindex_task(
    doc_index_list: Iterable[Dict[str, Any]],
    index_name: Optional[str] = None,
    refresh: Optional[str] = None,
) -> Dict[str, Any]:
    """Transform docIndex payloads into kb_chunks schema and bulk ingest."""

    target = index_name or SETTINGS.es.write_alias or SETTINGS.es.default_index
    transformed: List[Dict[str, Any]] = []
    for item in doc_index_list or []:
        mapped = _transform_doc_index(item)
        if mapped:
            transformed.append(mapped)
    if not transformed:
        return {"status": 200, "body": {"took": 0, "ingested": 0}, "ingested": 0}

    resp = ES.bulk(target, transformed, refresh=refresh)
    if not resp.ok:
        raise RuntimeError(f"DocIndex ingest failed: {resp.status} {resp.body}")
    return {"status": resp.status, "body": resp.body, "ingested": len(transformed)}


@celery_app.task(name="es_schema.rebuild_full")
def rebuild_full_task(
    source_alias: Optional[str] = None,
    target_version: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = SETTINGS.es.base_index
    version = target_version or "v2"
    new_index = f"{base}_{version}" if not base.endswith(version) else base
    create_index_task(index_name=new_index, overrides=overrides)
    # Placeholder for full copy; in practice, stream from source to new index.
    alias_switch_task(new_index=new_index, old_index=source_alias)
    return {"status": "scheduled", "index": new_index}


@celery_app.task(name="es_schema.rebuild_partial")
def rebuild_partial_task(
    index_name: Optional[str],
    query: Dict[str, Any],
    docs: Iterable[Dict[str, Any]],
    refresh: Optional[str] = None,
) -> Dict[str, Any]:
    target = index_name or SETTINGS.es.write_alias or SETTINGS.es.default_index
    delete_resp = ES.delete_by_query(target, query)
    if not delete_resp.ok:
        raise RuntimeError(f"Delete by query failed: {delete_resp.status} {delete_resp.body}")
    ingest_resp = bulk_ingest_task(index_name=target, docs=list(docs), refresh=refresh)
    return {
        "status": "completed",
        "delete_status": delete_resp.status,
        "ingest": ingest_resp,
    }
