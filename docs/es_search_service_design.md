# ES Search Service 详细设计文档

## 1. 服务定位
- 角色：面向知识库切片的检索服务，提供关键字全文检索、向量检索、混合检索，支持可配置权重与过滤。
- 模式：与 es_index_service 一致，包含 FastAPI HTTP、Celery 异步任务、gRPC JSON bridge。
- 外部依赖：Elasticsearch（同一集群，向量字段 `embedding`）、Redis 作为 Celery broker/result。

## 2. 代码结构
- FastAPI 应用与路由：`src/es_search_service/app.py`，`src/es_search_service/api/routes.py`
- 配置：`src/es_search_service/config.py`（前缀 `ES_SEARCH_SERVICE_`）
- 客户端与任务：`src/es_search_service/clients.py`，`src/es_search_service/tasks.py`
- gRPC 桥：`src/es_search_service/grpc_server.py`（服务 `es.search.SearchService`）

## 3. 配置与环境变量
前缀 `ES_SEARCH_SERVICE_`，嵌套用 `__`。
- 基本：`HOST`、`PORT`（默认 8086）、`GRPC_PORT`（默认 9106）、`BASE_URL`
- ES 连接：`ES__ENDPOINT`、`ES__USERNAME`、`ES__PASSWORD`、`ES__VERIFY_SSL`、`ES__REQUEST_TIMEOUT_SEC`
- 索引/字段：`ES__READ_ALIAS`、`ES__DEFAULT_INDEX`、`ES__VECTOR_FIELD`（默认 `embedding`）、`ES__TEXT_FIELDS`（默认 `title^2,content^3,summary,keywords^1.5,content_values`）、`ES__DEFAULT_NUM_CANDIDATES`（默认 200）
- Celery：`CELERY__BROKER_URL`、`CELERY__RESULT_BACKEND`、`CELERY__DEFAULT_QUEUE`（默认 `es-search-tasks`）、`CELERY__TASK_TIME_LIMIT_SEC`、`CELERY__PREFETCH_MULTIPLIER`

## 4. HTTP 接口（FastAPI）
- `GET /health` → `{status, service, version}`
- `POST /search/text` → Celery task id（文本 BM25，multi_match，支持 filters、permission_filters、highlight、_source）
- `POST /search/vector` → Celery task id（KNN，支持 filters、permission_filters、_source）
- `POST /search/hybrid` → Celery task id（script_score 结合 BM25 与向量，相对权重可调，支持 filters、permission_filters、_source）
- `GET /tasks/{task_id}` → 查询 Celery 任务状态/结果

### 请求体示例
**文本检索**
```json
{
  "query": "报销制度",
  "index_name": "kb_chunks_v1",
  "fields": ["title^2", "content^3", "summary"],
  "permission_filters": [
    {"term": {"tenant_id": "ep_001"}},
    {"terms": {"permitted_user_ids": ["u001", "u002"]}}
  ],
  "filters": [
    {"term": {"tenant_id": "ep_001"}},
    {"terms": {"knowledge_type": ["policy", "guide"]}}
  ],
  "from": 0,
  "size": 10,
  "highlight_fields": ["content", "title"],
  "_source": ["chunk_id", "title", "content", "knowledge_type", "score"]
}
```

**向量检索**
```json
{
  "query_vector": [0.01, 0.02, 0.03],
  "index_name": "kb_chunks_v1",
  "num_candidates": 500,
  "size": 20,
  "permission_filters": [
    {"term": {"tenant_id": "ep_001"}},
    {"terms": {"permitted_user_ids": ["u001", "u002"]}}
  ],
  "filters": [
    {"term": {"tenant_id": "ep_001"}},
    {"range": {"doc_version": {"gte": 2}}}
  ],
  "_source": ["chunk_id", "title", "content", "score"]
}
```

**混合检索（权重可配）**
```json
{
  "query": "员工差旅报销",
  "query_vector": [0.01, 0.02, 0.03],
  "index_name": "kb_chunks_v1",
  "text_weight": 1.2,
  "vector_weight": 1.0,
  "fields": ["content^3", "title^2", "summary"],
  "permission_filters": [
    {"term": {"tenant_id": "ep_001"}},
    {"terms": {"permitted_user_ids": ["u001", "u002"]}}
  ],
  "filters": [
    {"term": {"tenant_id": "ep_001"}},
    {"term": {"document_status": "online"}},
    {"bool": {"must_not": [{"term": {"is_deleted": true}}]}}
  ],
  "size": 15,
  "_source": ["chunk_id", "title", "content", "score", "tenant_id"]
}
```

返回：`{"task_id": "<uuid>", "status": "submitted"}`，通过 `/tasks/{task_id}` 获取结果。

## 5. Celery 任务
- `es_search.text_search(index_name, query, fields?, filters?, size?, from?, highlight_fields?, _source?)`
- `es_search.vector_search(index_name, query_vector, vector_field?, size?, num_candidates?, filters?, _source?)`
- `es_search.hybrid_search(index_name, query, query_vector, fields?, vector_field?, text_weight?, vector_weight?, size?, from?, filters?, _source?)`

## 6. gRPC JSON Bridge
- 服务名：`es.search.SearchService`
- 方法：SearchText / SearchVector / SearchHybrid / Health
- 请求/响应：JSON 字节，字段同 HTTP。

## 7. 过滤与权重说明
- filters 直接透传到 Elasticsearch 的 bool.filter，可组合 `term/terms/range/exists/bool`。
- 文本检索使用 multi_match(best_fields)；可通过 `fields` 调整字段权重（如 `content^3`）。
- 向量检索使用 KNN：`k=size`，`num_candidates` 默认 200；支持 filter（bool.filter）。
- 混合检索采用 script_score：`score = cosineSimilarity(params.vector, doc[vector_field]) * vector_weight + _score * text_weight`，可通过 text_weight/vector_weight 调整占比。
- 权限过滤（permission_filters）优先注入到 bool.filter，先于相关性计算执行，典型字段：`tenant_id`、`permitted_user_ids`、`permitted_department_ids`、`knowledge_role_ids`。

## 8. 运行
- 启动 HTTP：`uvicorn es_search_service.app:app --host 0.0.0.0 --port 8086`
- 启动 Celery worker：`celery -A es_search_service.tasks.celery_app worker -Q es-search-tasks -l info`
- 启动 gRPC：`python -m es_search_service.grpc_server`

## 9. 注意事项
- 向量字段默认为 `embedding` (dense_vector 768)。
- 过滤字段需存在于 mapping（参考 `config/kb_chunks_v1_mapping.json`）。
- 若需与写服务共用集群，请确保安装 ik/pinyin 插件并使用相同证书配置。
- 默认关闭 SSL 校验，可通过 `ES_SEARCH_SERVICE_ES__VERIFY_SSL=true` 并配置证书开启。
