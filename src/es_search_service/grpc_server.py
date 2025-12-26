"""Lightweight gRPC JSON bridge for ES search service."""
from __future__ import annotations

import json
import logging
from concurrent import futures
from typing import Any, Dict

import grpc

from .config import get_settings
from .tasks import hybrid_search_task, text_search_task, vector_search_task

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


def _search_text(data: Dict[str, Any]) -> Dict[str, Any]:
    task = text_search_task.delay(
        data.get("index_name"),
        data.get("query", ""),
        data.get("fields"),
        data.get("filters"),
        data.get("permission_filters"),
        data.get("size", 10),
        data.get("from", 0),
        data.get("highlight_fields"),
        data.get("_source"),
    )
    return {"task_id": task.id, "status": "submitted"}


def _search_vector(data: Dict[str, Any]) -> Dict[str, Any]:
    task = vector_search_task.delay(
        data.get("index_name"),
        data.get("query_vector", []),
        data.get("vector_field"),
        data.get("size", 10),
        data.get("num_candidates", 200),
        data.get("filters"),
        data.get("permission_filters"),
        data.get("_source"),
    )
    return {"task_id": task.id, "status": "submitted"}


def _search_hybrid(data: Dict[str, Any]) -> Dict[str, Any]:
    task = hybrid_search_task.delay(
        data.get("index_name"),
        data.get("query", ""),
        data.get("query_vector", []),
        data.get("fields"),
        data.get("vector_field"),
        data.get("text_weight", 1.0),
        data.get("vector_weight", 1.0),
        data.get("size", 10),
        data.get("from", 0),
        data.get("filters"),
        data.get("permission_filters"),
        data.get("_source"),
    )
    return {"task_id": task.id, "status": "submitted"}


def _health(_data: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok"}


def _build_generic_handler():
    return grpc.method_handlers_generic_handler(
        "es.search.SearchService",
        {
            "SearchText": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_search_text, req, ctx),
            ),
            "SearchVector": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_search_vector, req, ctx),
            ),
            "SearchHybrid": grpc.unary_unary_rpc_method_handler(
                lambda req, ctx: _unary(_search_hybrid, req, ctx),
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
