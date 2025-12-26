"""HTTP client for ES search operations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from .config import ServiceSettings


@dataclass
class ESResponse:
    status: int
    body: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class ESClient:
    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        self.base = settings.es.endpoint.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESResponse:
        url = f"{self.base}/{path.lstrip('/')}"
        auth = None
        if self.settings.es.username and self.settings.es.password:
            auth = HTTPBasicAuth(self.settings.es.username, self.settings.es.password)
        response = requests.request(
            method,
            url,
            json=json_body,
            params=params,
            auth=auth,
            timeout=self.settings.es.request_timeout_sec,
            verify=self.settings.es.verify_ssl,
            headers=headers or {},
        )
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return ESResponse(status=response.status_code, body=body)

    def _build_filters(
        self,
        filters: Optional[Iterable[Dict[str, Any]]],
        permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        # permission_filters 被优先加入，确保访问控制在评分前生效
        combined: List[Dict[str, Any]] = []
        for f in (permission_filters or []):
            if f:
                combined.append(f)
        for f in (filters or []):
            if f:
                combined.append(f)
        return combined

    def text_search(
        self,
        index: str,
        query_text: str,
        *,
        fields: Optional[List[str]] = None,
        filters: Optional[Iterable[Dict[str, Any]]] = None,
        permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
        size: int = 10,
        from_: int = 0,
        highlight_fields: Optional[List[str]] = None,
        source: Optional[List[str]] = None,
    ) -> ESResponse:
        search_fields = fields or self.settings.es.text_fields
        bool_query: Dict[str, Any] = {
            "must": [
                {
                    "multi_match": {
                        "query": query_text,
                        "fields": search_fields,
                        "type": "best_fields",
                    }
                }
            ],
        }
        filter_clauses = self._build_filters(filters, permission_filters)
        if filter_clauses:
            bool_query["filter"] = filter_clauses

        body: Dict[str, Any] = {
            "from": from_,
            "size": size,
            "query": {"bool": bool_query},
        }
        if highlight_fields:
            body["highlight"] = {"fields": {name: {} for name in highlight_fields}}
        if source is not None:
            body["_source"] = source
        return self._request("POST", f"{index}/_search", json_body=body)

    def vector_search(
        self,
        index: str,
        query_vector: List[float],
        *,
        vector_field: Optional[str] = None,
        size: int = 10,
        num_candidates: Optional[int] = None,
        filters: Optional[Iterable[Dict[str, Any]]] = None,
        permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
        source: Optional[List[str]] = None,
    ) -> ESResponse:
        field_name = vector_field or self.settings.es.vector_field
        effective_candidates = num_candidates or self.settings.es.default_num_candidates
        knn: Dict[str, Any] = {
            "field": field_name,
            "query_vector": query_vector,
            "k": size,
            "num_candidates": effective_candidates,
        }
        filter_clauses = self._build_filters(filters, permission_filters)
        if filter_clauses:
            knn["filter"] = {"bool": {"filter": filter_clauses}}
        body: Dict[str, Any] = {"size": size, "knn": knn}
        if source is not None:
            body["_source"] = source
        return self._request("POST", f"{index}/_search", json_body=body)

    def hybrid_search(
        self,
        index: str,
        query_text: str,
        query_vector: List[float],
        *,
        fields: Optional[List[str]] = None,
        vector_field: Optional[str] = None,
        text_weight: float = 1.0,
        vector_weight: float = 1.0,
        size: int = 10,
        from_: int = 0,
        filters: Optional[Iterable[Dict[str, Any]]] = None,
        permission_filters: Optional[Iterable[Dict[str, Any]]] = None,
        source: Optional[List[str]] = None,
    ) -> ESResponse:
        search_fields = fields or self.settings.es.text_fields
        field_name = vector_field or self.settings.es.vector_field
        filter_clauses = self._build_filters(filters, permission_filters)
        bool_query: Dict[str, Any] = {
            "must": [
                {
                    "multi_match": {
                        "query": query_text,
                        "fields": search_fields,
                        "type": "best_fields",
                    }
                }
            ]
        }
        if filter_clauses:
            bool_query["filter"] = filter_clauses

        body: Dict[str, Any] = {
            "from": from_,
            "size": size,
            "query": {
                "script_score": {
                    "query": {"bool": bool_query},
                    "script": {
                        # Use field name directly with cosineSimilarity; avoids docvalue casting issues.
                        "source": "cosineSimilarity(params.vector, params.field) * params.vector_weight + _score * params.text_weight",
                        "params": {
                            "vector": query_vector,
                            "field": field_name,
                            "vector_weight": vector_weight,
                            "text_weight": text_weight,
                        },
                    },
                }
            },
        }
        if source is not None:
            body["_source"] = source
        return self._request("POST", f"{index}/_search", json_body=body)

    def cluster_health(self) -> ESResponse:
        return self._request("GET", "_cluster/health")
