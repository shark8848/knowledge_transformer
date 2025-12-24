"""HTTP client helpers for Elasticsearch operations."""
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
        data_body: Any | None = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESResponse:
        url = f"{self.base}/{path.lstrip('/')}"
        auth = None
        if self.settings.es.username and self.settings.es.password:
            auth = HTTPBasicAuth(self.settings.es.username, self.settings.es.password)

        req_headers = headers or {}
        response = requests.request(
            method,
            url,
            json=json_body,
            data=data_body,
            params=params,
            auth=auth,
            timeout=self.settings.es.request_timeout_sec,
            verify=self.settings.es.verify_ssl,
            headers=req_headers,
        )
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return ESResponse(status=response.status_code, body=body)

    def create_index(self, index_name: str, body: Dict[str, Any]) -> ESResponse:
        return self._request("PUT", f"{index_name}", json_body=body)

    def alias_switch(
        self,
        *,
        read_alias: str,
        write_alias: str,
        new_index: str,
        old_index: str | None = None,
    ) -> ESResponse:
        actions: List[Dict[str, Any]] = []
        if old_index:
            actions.append({"remove": {"index": old_index, "alias": read_alias}})
            actions.append({"remove": {"index": old_index, "alias": write_alias}})
        actions.append({"add": {"index": new_index, "alias": read_alias}})
        actions.append({"add": {"index": new_index, "alias": write_alias}})
        return self._request("POST", "_aliases", json_body={"actions": actions})

    def bulk(self, index_name: str, docs: Iterable[Dict[str, Any]], refresh: str | None = None) -> ESResponse:
        lines: List[str] = []
        for doc in docs:
            doc_id = doc.get("chunk_id")
            action: Dict[str, Any] = {"index": {"_index": index_name}}
            if doc_id:
                action["index"]["_id"] = doc_id
            lines.append(json.dumps(action, ensure_ascii=False))
            lines.append(json.dumps(doc, ensure_ascii=False))
        payload = "\n".join(lines) + "\n"
        params = {"refresh": refresh} if refresh is not None else None
        return self._request(
            "POST",
            "_bulk",
            data_body=payload.encode("utf-8"),
            params=params,
            headers={"Content-Type": "application/x-ndjson"},
        )

    def cluster_health(self) -> ESResponse:
        return self._request("GET", "_cluster/health")

    def delete_by_query(self, index: str, query: Dict[str, Any]) -> ESResponse:
        return self._request("POST", f"{index}/_delete_by_query", json_body=query)
