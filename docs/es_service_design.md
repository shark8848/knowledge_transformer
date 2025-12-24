# ES Service 详细设计文档

## 1. 服务定位
- 角色：提供 Elasticsearch 索引/别名管理与批量写入的轻量服务。
- 接口形态：FastAPI HTTP、Celery 异步任务、gRPC JSON bridge。
- 外部依赖：Elasticsearch（需安装 analysis-ik 与 analysis-pinyin 插件）、Redis 作为 Celery broker/result。
- 默认端口：HTTP 8085，gRPC 9105。Celery 队列：`es-schema-tasks`。

## 2. 代码结构
- FastAPI 应用与路由：`src/es_service/app.py`，`src/es_service/api/routes.py`
- 配置与环境：`src/es_service/config.py`（Pydantic Settings，前缀 `ES_SERVICE_`）
- 任务与客户端：`src/es_service/tasks.py`（Celery 任务），`src/es_service/clients.py`（ES HTTP 客户端，bulk 含 `Content-Type: application/x-ndjson`）
- gRPC 桥：`src/es_service/grpc_server.py`（通用 JSON handler）
- 映射模板：`config/kb_chunks_v1_mapping.json`
- 管理脚本：`start_es_service.sh`、`stop_es_service.sh`、`show_es_service.sh`

## 3. 配置与环境变量（核心）
前缀 `ES_SERVICE_`，嵌套用双下划线 `__`。
- 端口与基本：`API_PORT`、`GRPC_PORT`、`HOST`
- ES 连接：`ES__ENDPOINT`、`ES__USERNAME`、`ES__PASSWORD`、`ES__VERIFY_SSL`、`ES__REQUEST_TIMEOUT_SEC`
- 索引/别名：`ES__DEFAULT_INDEX`、`ES__READ_ALIAS`、`ES__WRITE_ALIAS`、`ES__BASE_INDEX`、`ES__DEFAULT_SHARDS`、`ES__DEFAULT_REPLICAS`、`ES__REFRESH_INTERVAL`
- 映射路径：`ES__MAPPING_PATH`（默认 `config/kb_chunks_v1_mapping.json`）
- Celery：`CELERY__BROKER_URL`、`CELERY__RESULT_BACKEND`、`CELERY__DEFAULT_QUEUE`、`CELERY__TASK_TIME_LIMIT_SEC`、`CELERY__PREFETCH_MULTIPLIER`

示例（自签证书环境）：
```
ES_SERVICE_ES__ENDPOINT=https://localhost:9200
ES_SERVICE_ES__USERNAME=elastic
ES_SERVICE_ES__PASSWORD=<password>
ES_SERVICE_ES__VERIFY_SSL=false
ES_SERVICE_API_PORT=8085
ES_SERVICE_GRPC_PORT=9105
```

## 4. HTTP 接口（FastAPI）
- `GET /health` → `{status, service, version}`
- `POST /schemas/render`：Body `{overrides?: {number_of_shards?, number_of_replicas?, refresh_interval?}}` → 返回渲染后的 mapping（忽略 None）
- `POST /indices/create`：Body `{index_name?, overrides?}` → 返回 Celery `task_id`
- `POST /indices/alias/switch`：`{new_index, old_index?, read_alias?, write_alias?}`
- `POST /ingest/bulk`：`{index_name?, refresh?, docs: []}`
- `POST /indices/rebuild`：`{source_alias?, target_version?, overrides?}`
- `POST /indices/rebuild/partial`：`{index_name?, query:{}, docs:[], refresh?}`
- `GET /tasks/{task_id}`：查询 Celery 任务状态

示例调用：
```
# 渲染 mapping
curl -k http://127.0.0.1:8085/schemas/render \
  -H "Content-Type: application/json" \
  -d '{"overrides":{"number_of_shards":1,"refresh_interval":"1s"}}'

# 创建索引
curl -k http://127.0.0.1:8085/indices/create \
  -H "Content-Type: application/json" \
  -d '{"index_name":"kb_chunks_v1","overrides":{"number_of_shards":3}}'

# 批量写入
curl -k http://127.0.0.1:8085/ingest/bulk \
  -H "Content-Type: application/json" \
  -d '{"index_name":"kb_chunks_v1","refresh":"wait_for","docs":[{"chunk_id":"1","content":"hello","embedding":[0.1,0.2]}]}'
```

## 5. Celery 任务
- `es_schema.create_index`
- `es_schema.alias_switch`
- `es_schema.bulk_ingest`
- `es_schema.rebuild_full`
- `es_schema.rebuild_partial`

## 6. gRPC JSON Bridge
- 服务名：`es.schema.IndexService`
- 方法：CreateIndex / AliasSwitch / BulkIngest / Rebuild / RebuildPartial / Health
- 请求/响应：JSON 字节。
- 示例：
```
grpcurl -plaintext -d '{"index_name":"kb_chunks_v1"}' \
  localhost:9105 es.schema.IndexService/CreateIndex

grpcurl -plaintext -d '{"index_name":"kb_chunks_v1","docs":[{"chunk_id":"1","content":"hi","embedding":[0.1,0.2]}]}' \
  localhost:9105 es.schema.IndexService/BulkIngest
```

## 7. 直接 Python 调用示例
```python
from es_service.config import get_settings
from es_service.clients import ESClient
s = get_settings()
es = ESClient(s)
resp = es.create_index("kb_chunks_v1_demo", {"settings": {}, "mappings": {"properties": {}}})
print(resp.status, resp.body)
docs = [{"chunk_id":"1","content":"hi","embedding":[0.1]*768}]
resp = es.bulk("kb_chunks_v1_demo", docs, refresh="wait_for")
print(resp.status, resp.body)
```

## 8. Celery 使用场景（穷举示例）

**快速写入现有索引/别名**
```python
from es_service.tasks import celery_app

task = celery_app.send_task(
  "es_schema.bulk_ingest",
  args=[
    "kb_chunks_v1",  # 可为写别名或具体索引，None 使用默认写别名
    [{"chunk_id": "1", "content": "hello", "embedding": [0.1] * 768}],
    "wait_for",      # refresh 策略，可省略
  ],
)
print(task.id)
```

**滚动升级（新索引 → 导入 → 切别名）**
```python
new_idx = "kb_chunks_v1_roll_2025"
celery_app.send_task("es_schema.create_index", args=[new_idx, {"number_of_shards": 3}])
celery_app.send_task("es_schema.bulk_ingest", args=[new_idx, [{"chunk_id": "1", "content": "hi", "embedding": [0.2]*768}], "wait_for"])
celery_app.send_task("es_schema.alias_switch", args=[new_idx, "kb_chunks", "kb_chunks_write", "kb_chunks_v1"])
```

**全量重建占位（rebuild_full）**
```python
task = celery_app.send_task(
  "es_schema.rebuild_full",
  args=["kb_chunks", "v2", {"number_of_shards": 3}],
)
print(task.id)
```

**局部重建/补丁（rebuild_partial）**
```python
task = celery_app.send_task(
  "es_schema.rebuild_partial",
  args=[
    "kb_chunks_v1",
    {"term": {"doc_id": "doc123"}},
    [{"chunk_id": "doc123-1", "content": "patch", "embedding": [0.3]*768}],
    "wait_for",
  ],
)
```

**任务状态查询（AsyncResult）**
```python
from celery import Celery
app = Celery(broker="redis://localhost:6379/0", backend="redis://localhost:6379/1")
res = app.AsyncResult(task.id)
print(res.state, res.result)
```

**实际业务样例：写入带丰富元数据的文档切片（支持后续检索/索引）**
```python
from es_service.tasks import celery_app

doc = {
  "primary_id": "zj_10001",
  "knowledge_id": "doc_90001",
  "file_id": "file_pdf_7788",
  "title": "员工报销制度（2025版）",
  "knowledge_type": "policy",
  "content": "第二条 报销范围包括：差旅费、住宿费、餐饮费……（该段落切片文本）",
  "embedding": [0.0] * 768,  # 替换为真实 768 维向量
  "content_image": "",
  "content_values": "第二条 报销范围包括：差旅费、住宿费、餐饮费",
  "knowledge_user_ids": "u001,u002",
  "knowledge_role_ids": "r_finance,r_admin",
  "chunk_id": "doc_90001_p003_c0007",
  "department_id": "dep_finance",
  "enterprise_id": "org_001",
  "tenant_id": "ep_001",
  "knowledge_base_id": "kb_01",
  "kb_tree_id_0": "kb_01",
  "kb_tree_id_1": "kb_01_02",
  "kb_tree_id_2": "kb_01_02_03",
  "kb_tree_id_3": "",
  "parent_path_id": "kb_01/kb_01_02/kb_01_02_03",
  "city_id": "",
  "parent_city_id": "",
  "document_status": "online",
  "lifecycle_status": "default",
  "created_user_id": "oa_12345",
  "tags": ["报销", "制度"],
  "keywords": ["差旅费", "住宿费", "发票"],
  "summary": "",
  "faq": [],
  "external_classify_id": "",
  "external_knowledge_id": "",
  "external_attach_id": "",
  "metadata": {"parser": "pdf-text-extract-v2", "page_total": "18"},
  "role_id": "0",
  "permitted_department_ids": [],
  "permitted_user_ids": [],
  "item_type": 0,
  "item_type_name": "paragraph",
  "vector_required": True,
  "source_chunk_id": "",
  "media_type": "document",
  "media_subtype": "pdf",
  "media_uri": "oss://bucket/kb/doc_90001.pdf",
  "converted _uri": "oss://bucket/kb/doc_90001.pdf",
  "markdown_file": "oss://bucket/kb/images_output/test_123/doc_90001.md",
  "middle_json": "oss://bucket/kb/images_output/test_123/doc_90001_middle.json",
  "media_meta": {
    "layout": {
      "format": "layout_xml_json_refs_v1",
      "raw": "<layout>[{\"page_idx\":1,\"index\":0},{\"page_idx\":1,\"index\":1},{\"page_idx\":2,\"index\":0}]</layout>",
      "source": "mineru",
      "source_base": {"page_idx": 1, "index": 0},
      "normalized_base": {"page_idx": 1, "index": 0},
      "normalized": {
        "refs": [
          {"page_idx": 1, "index": 0, "bbox": {"x1": 220, "y1": 930, "x2": 980, "y2": 1010}},
          {"page_idx": 1, "index": 1, "bbox": {"x1": 220, "y1": 930, "x2": 980, "y2": 1010}},
          {"page_idx": 2, "index": 0, "bbox": {"x1": 220, "y1": 860, "x2": 980, "y2": 920}},
        ]
      },
      "stats": {"ref_count": 3, "span_page_count": 2, "is_multi_page": True},
    }
  },
}

task = celery_app.send_task(
  "es_schema.bulk_ingest",
  args=[
    "kb_chunks_v1",  # 目标写别名或索引
    [doc],
    "wait_for",
  ],
)
print("bulk task id:", task.id)
```

**删除/清理场景（使用 rebuild_partial 的 delete+可选补丁）**
```python
from es_service.tasks import celery_app

# 仅删除匹配的文档（示例：按 doc_id）
del_task = celery_app.send_task(
  "es_schema.rebuild_partial",
  args=[
    "kb_chunks_v1",                # 目标索引或写别名
    {"term": {"doc_id": "doc_90001"}},  # 删除条件
    [],                              # 不写入新文档
    "wait_for",                    # 刷新策略，确保删除后可见
  ],
)
print("delete task id:", del_task.id)

# 删除后补回修订文档（可选）
patch_task = celery_app.send_task(
  "es_schema.rebuild_partial",
  args=[
    "kb_chunks_v1",
    {"term": {"doc_id": "doc_90001"}},
    [{"doc_id": "doc_90001", "chunk_id": "doc_90001_p003_c0007", "content": "修订后的文本", "embedding": [0.1]*768}],
    "wait_for",
  ],
)
print("patch task id:", patch_task.id)
```

**可靠性与性能提示**
- 控制并发/预取：`ES_SERVICE_CELERY__PREFETCH_MULTIPLIER`（默认 1）避免过多预取导致内存占用。
- 任务超时：`ES_SERVICE_CELERY__TASK_TIME_LIMIT_SEC`（默认 300）。
- 队列隔离：如需区分写入/重建，可改 `ES_SERVICE_CELERY__DEFAULT_QUEUE` 或在 send_task 指定 `queue`。
- Worker 命名：`ES_SERVICE_WORKER_NAME` 便于可观测。
- 错误重试：可在上层调用方捕获 `res.state` 及 `res.result`，根据业务补偿；当前任务未内置重试策略。

## 9. 运行与脚本
- 启动：`start_es_service.sh`（API + Celery + gRPC，日志 `logs/`，pid `.run/`）
- 停止：`stop_es_service.sh`
- 状态：`show_es_service.sh`（进程、/healthz、ES 健康、Celery ping）

## 10. 依赖与注意事项
- Elasticsearch 8.19.7 需安装插件：`analysis-ik`、`analysis-pinyin`，否则创建索引会报 unknown filter。
- 自签证书环境可设 `ES_SERVICE_ES__VERIFY_SSL=false`，或导入 CA 后开启校验。
- bulk 请求已显式使用 `Content-Type: application/x-ndjson`。
- Redis 作为 Celery broker/backend，示例：`redis://localhost:6379/0`、`redis://localhost:6379/1`。

## 11. 故障与排查
- 401：检查 ES 用户密码或 `ES_SERVICE_ES__USERNAME/PASSWORD` 是否正确。
- 406 bulk：确认客户端 Content-Type（本服务已修复）；确保 NDJSON 格式行尾有 `\n`。
- 创建索引报 unknown filter：安装 ik/pinyin 插件并重启 ES。
- 自签证书警告：设 `verify_ssl=false` 或导入 CA。
