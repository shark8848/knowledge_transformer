from __future__ import annotations

from types import SimpleNamespace

import pytest

import es_index_service.tasks as tasks


class FakeResp:
    def __init__(self, ok: bool = True, status: int = 200, body: dict | None = None):
        self.ok = ok
        self.status = status
        self.body = body or {"took": 1, "items": []}


class FakeES:
    def __init__(self):
        self.calls: list[tuple[str, list[dict], str | None]] = []

    def bulk(self, target: str, docs: list[dict], refresh: str | None = None) -> FakeResp:
        self.calls.append((target, docs, refresh))
        return FakeResp()


def test_transform_doc_index_maps_fields_and_vector():
    raw = {
        "zj_id": "p1",
        "docid": "k1",
        "attachId": "f1",
        "doctitle": "title",
        "klg_type": "type",
        "item_value": "content",
        "item_value_vector": "1,2,3",
        "item_value_img": "img",
        "item_values": "vals",
        "itemvaluess": "vals_s",
        "klg_user_ids": ["u1"],
        "klg_role_ids": ["r1"],
        "group_id": "g1",
        "depar_id": "d1",
        "org_id": "o1",
        "ep_id": "e1",
        "ct_id": "kb",
        "ct_id0": "t0",
        "ct_id1": "t1",
        "ct_id2": "t2",
        "ct_id3": "t3",
        "parent_path_id": "pp",
        "city_id": "c1",
        "up_city_id": "pc1",
        "doc_status": "active",
        "life_status": "live",
        "crt_userid": "uploader",
        "tags": ["t"],
        "keywords": ["k"],
        "summary": "s",
        "faq": ["q"],
        "rel_classify_id": "rc",
        "rel_klg_id": "rk",
        "rel_attach_id": "ra",
        "attributes": {"k": "v"},
        "metaData": {"m": "v"},
        "role": "0",
        "deptPermission": ["d2"],
        "userPermission": ["u2"],
        "item_type": 1,
    }

    transformed = tasks._transform_doc_index(raw)

    assert transformed["primary_id"] == "p1"
    assert transformed["knowledge_id"] == "k1"
    assert transformed["file_id"] == "f1"
    assert transformed["title"] == "title"
    assert transformed["knowledge_type"] == "type"
    assert transformed["content"] == "content"
    assert transformed["content_image"] == "img"
    assert transformed["content_values"] == "vals"
    assert transformed["content_values_s"] == "vals_s"
    assert transformed["knowledge_user_ids"] == ["u1"]
    assert transformed["knowledge_role_ids"] == ["r1"]
    assert transformed["chunk_id"] == "g1"
    assert transformed["department_id"] == "d1"
    assert transformed["enterprise_id"] == "o1"
    assert transformed["tenant_id"] == "e1"
    assert transformed["knowledge_base_id"] == "kb"
    assert transformed["kb_tree_id_0"] == "t0"
    assert transformed["kb_tree_id_1"] == "t1"
    assert transformed["kb_tree_id_2"] == "t2"
    assert transformed["kb_tree_id_3"] == "t3"
    assert transformed["parent_path_id"] == "pp"
    assert transformed["city_id"] == "c1"
    assert transformed["parent_city_id"] == "pc1"
    assert transformed["document_status"] == "active"
    assert transformed["lifecycle_status"] == "live"
    assert transformed["created_user_id"] == "uploader"
    assert transformed["tags"] == ["t"]
    assert transformed["keywords"] == ["k"]
    assert transformed["summary"] == "s"
    assert transformed["faq"] == ["q"]
    assert transformed["external_classify_id"] == "rc"
    assert transformed["external_knowledge_id"] == "rk"
    assert transformed["external_attach_id"] == "ra"
    assert transformed["attributes"] == {"k": "v"}
    assert transformed["metadata"] == {"m": "v"}
    assert transformed["visibility_scope"] == "0"
    assert transformed["permitted_department_ids"] == ["d2"]
    assert transformed["permitted_user_ids"] == ["u2"]
    assert transformed["item_type"] == 1
    assert transformed["embedding"] == [1.0, 2.0, 3.0]


def test_ingest_docindex_task_maps_and_calls_bulk(monkeypatch):
    fake_es = FakeES()
    monkeypatch.setattr(tasks, "ES", fake_es)
    monkeypatch.setattr(tasks, "SETTINGS", SimpleNamespace(es=SimpleNamespace(write_alias="kb_write", default_index="kb_def")))

    payload = [
        {"zj_id": "p1", "docid": "k1", "item_value": "c", "item_value_vector": [0.1, 0.2]},
        {"zj_id": "p2", "docid": "k2", "item_value": "c2"},
    ]

    result = tasks.ingest_docindex_task(payload, index_name=None, refresh="wait_for")

    assert result["status"] == 200
    assert result["ingested"] == 2
    assert fake_es.calls[0][0] == "kb_write"
    assert fake_es.calls[0][2] == "wait_for"
    docs = fake_es.calls[0][1]
    assert docs[0]["primary_id"] == "p1"
    assert docs[0]["knowledge_id"] == "k1"
    assert docs[0]["content"] == "c"
    assert docs[0]["embedding"] == [0.1, 0.2]
    assert docs[1]["primary_id"] == "p2"


def test_ingest_docindex_task_returns_empty_when_no_docs(monkeypatch):
    fake_es = FakeES()
    monkeypatch.setattr(tasks, "ES", fake_es)
    monkeypatch.setattr(tasks, "SETTINGS", SimpleNamespace(es=SimpleNamespace(write_alias="kb_write", default_index="kb_def")))

    result = tasks.ingest_docindex_task([], index_name=None, refresh=None)

    assert result["status"] == 200
    assert result["body"]["took"] == 0
    assert result.get("ingested", 0) == 0
    assert fake_es.calls == []
