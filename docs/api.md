# API 说明

所有业务接口默认挂载在 `base_url`（默认 `/api/v1`）下，并要求在请求头携带 `X-Appid`、`X-Key`。若在 `config/settings.yaml` 中将 `api_auth.required` 设置为 `false`，则无需认证。

## POST /api/v1/convert

提交批量转换任务。

```json
{
  "task_name": "demo-batch",
  "priority": "normal",
  "callback_url": "https://example.com/hook",
  "files": [
    {
      "source_format": "doc",
      "target_format": "docx",
      "input_url": "https://storage/doc1.doc",
      "size_mb": 12.5
    }
  ]
}
```

**响应**

```json
{
  "status": "accepted",
  "task_id": "b8a6b5df-...",
  "message": "Task accepted and scheduled for conversion"
}
```

## GET /api/v1/formats

返回运行时可用的格式映射（实时读取插件注册信息）。

```json
{
  "formats": [
    {"source": "doc", "target": "docx", "plugin": "doc-to-docx"},
    {"source": "svg", "target": "png", "plugin": "svg-to-png"},
    {"source": "gif", "target": "mp4", "plugin": "gif-to-mp4"},
    {"source": "webp", "target": "png", "plugin": "webp-to-png"},
    {"source": "wav", "target": "mp3", "plugin": "wav-to-mp3"},
    {"source": "flac", "target": "mp3", "plugin": "flac-to-mp3"},
    {"source": "ogg", "target": "mp3", "plugin": "ogg-to-mp3"},
    {"source": "aac", "target": "mp3", "plugin": "aac-to-mp3"},
    {"source": "avi", "target": "mp4", "plugin": "avi-to-mp4"},
    {"source": "mov", "target": "mp4", "plugin": "mov-to-mp4"},
    {"source": "mkv", "target": "mp4", "plugin": "mkv-to-mp4"},
    {"source": "webm", "target": "mp4", "plugin": "webm-to-mp4"},
    {"source": "mpeg", "target": "mp4", "plugin": "mpeg-to-mp4"}
  ]
}
```

## GET /api/v1/monitor/health

输出服务状态、关键依赖连通性（示例实现为占位，可扩展 MinIO、Redis、对象存储等检测）。

```json
{
  "status": "ok",
  "timestamp": "2025-12-04T03:21:00Z",
  "dependencies": {
    "redis": "unknown",
    "minio": "unknown"
  }
}
```

## GET /healthz

裸服务存活检测，主要用于容器探针。

## Prometheus 指标

运行 FastAPI 进程后，默认会在 `http://<host>:9091/metrics` 暴露指标；Celery worker 会额外在 `9092` 启动指标端口。暴露的核心字段包括：

- `conversion_tasks_accepted_total{priority}`：API 接收到的转换任务数量。
- `conversion_tasks_completed_total{status}`：任务在 Worker 侧完成/失败次数。
- `conversion_queue_depth`：Redis/Celery 队列深度。
- `conversion_active_celery_workers`：当前在线的 Worker 数目。

---

- 所有请求/响应字段定义位于 `src/rag_converter/api/schemas.py`，便于多语言 SDK 自动生成。
- 若需要扩展新的监控接口，可在 `src/rag_converter/api/routes.py` 中添加路由并复用 `settings.monitoring` 下的路径配置。
