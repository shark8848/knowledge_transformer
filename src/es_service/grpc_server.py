"""Lightweight gRPC JSON bridge for ES schema/index service.

This uses generic handlers to avoid compiled stubs; request/response payloads are JSON
objects serialized to bytes. The service name is `es.schema.IndexService` with methods:
- CreateIndex
- AliasSwitch
- Rebuild
- RebuildPartial
- BulkIngest
- Health
"""
from __future__ import annotations

import json
import logging
from concurrent import futures
from typing import Any, Dict

import grpc

from .config import get_settings
from .tasks import alias_switch_task, bulk_ingest_task, create_index_task, rebuild_full_task, rebuild_partial_task

logger = logging.getLogger(__name__)


def _deserialize(request: bytes) -> Dict[str, Any]:
    if not request:
        return {}
    try:
        return json.loads(request.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("Invalid JSON payload") from exc


def _serialize(response: Dict[str, Any]) -> bytes:
    return json.dumps(response, ensure_ascii=False).encode("utf-8")


def _unary(handler, request, context):
    data = _deserialize(request)
    result = handler(data)
    return _serialize(result)


def _create_index(data: Dict[str, Any]) -> Dict[str, Any]:
    task = create_index_task.delay(data.get("index_name"), data.get("overrides"))
    return {"task_id": task.id, "status": "submitted"}


def _alias_switch(data: Dict[str, Any]) -> Dict[str, Any]:
    task = alias_switch_task.delay(
        data.get("new_index"),
        data.get("read_alias"),
        data.get("write_alias"),
        data.get("old_index"),
    )
    return {"task_id": task.id, "status": "submitted"}


def _bulk_ingest(data: Dict[str, Any]) -> Dict[str, Any]:
    task = bulk_ingest_task.delay(data.get("index_name"), data.get("docs", []), data.get("refresh"))
    return {"task_id": task.id, "status": "submitted"}


def _rebuild(data: Dict[str, Any]) -> Dict[str, Any]:
    task = rebuild_full_task.delay(
        data.get("source_alias"),
        data.get("target_version"),
        data.get("overrides"),
    )
    return {"task_id": task.id, "status": "submitted"}


def _rebuild_partial(data: Dict[str, Any]) -> Dict[str, Any]:
    task = rebuild_partial_task.delay(
        data.get("index_name"),
        data.get("query", {}),
        data.get("docs", []),
        data.get("refresh"),
    )
    return {"task_id": task.id, "status": "submitted"}


def _health(_data: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok"}


def _build_generic_handler():
    return grpc.method_handlers_generic_handler(
        "es.schema.IndexService",
        {
            "CreateIndex": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_create_index, req, ctx),
            ),
            "AliasSwitch": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_alias_switch, req, ctx),
            ),
            "BulkIngest": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_bulk_ingest, req, ctx),
            ),
            "Rebuild": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_rebuild, req, ctx),
            ),
            "RebuildPartial": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_rebuild_partial, req, ctx),
            ),
            "Health": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_health, req, ctx),
            ),
        },
    )


def serve() -> None:
    settings = get_settings()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    server.add_generic_rpc_handlers([_build_generic_handler()])
    listen_addr = f"0.0.0.0:{settings.grpc_port}"
    server.add_insecure_port(listen_addr)
    logger.info("Starting gRPC server", extra={"listen": listen_addr})
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
