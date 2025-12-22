# Slicer Recommendation Service Usage

独立的切片策略服务（`slicer_service`）提供探针画像和策略推荐两类能力，可单独部署。

## 1) 运行方式
- 一键脚本：`start_slicer.sh` / `stop_slicer.sh` / `show_slicer.sh`
  - API 默认 8100，Worker metrics/Prom 默认 9093，Flower 默认 5556
- Docker Compose: 已在 `docker-compose.yml` 中提供 `slicer-api`（端口 8100，/metrics 9093）和 `slicer-worker`、`slicer-flower`（5556）。
- 手工命令：
  - API: `uvicorn slicer_service.app:app --host 0.0.0.0 --port 8100`
  - Worker: `celery -A slicer_service.celery_app:celery_app worker --loglevel=info`
  - Flower: `celery -A slicer_service.celery_app:celery_app flower --port 5556`

## 2) 环境变量（前缀 `SLICE_`）
- `SLICE_celery__broker_url`：Celery Broker，默认 `redis://localhost:6379/0`
- `SLICE_celery__result_backend`：结果存储，默认 `redis://localhost:6379/1`
- `SLICE_api_auth__required`：是否启用鉴权，默认 `false`
- `SLICE_api_auth__appid` / `SLICE_api_auth__key`：开启鉴权后设置固定 appid/key
- `SLICE_monitoring__prometheus_port`：Prometheus 端口，默认 `9093`
- `SLICE_monitoring__enable_metrics`：是否启用 metrics，默认 `true`

## 3) REST 接口示例
- 探针画像：
```bash
curl -X POST http://localhost:8100/api/v1/probe/profile \
  -H 'Content-Type: application/json' \
  -d '{"samples":["# Title\\nParagraph text."]}'
```

- 策略推荐（含自定义分隔符）：
```bash
curl -X POST http://localhost:8100/api/v1/probe/recommend_strategy \
  -H 'Content-Type: application/json' \
  -d '{"samples":["a---b---c---d---e---f"],"custom":{"enable":true,"delimiters":["---"],"min_segments":2},"emit_candidates":true}'
```

## 4) Celery 任务调用示例
- `probe.extract_signals` payload：`{"samples": ["text ..."]}`
- `probe.recommend_strategy` payload：`{"samples": ["text ..."], "custom": {"enable": true, "delimiters": ["---"]}}`

## 5) 端口/健康检查/监控
- 健康检查: `GET http://localhost:8100/healthz`
- Metrics: `GET http://localhost:8100/metrics` （Prometheus 格式，默认 9093 暴露）
- Flower: `http://localhost:5556`

## 6) 典型返回（仅三类模式）
输出统一包含 `mode`/`mode_id`/`mode_desc`，仅三类：`direct_delimiter`(1)、`semantic_sentence`(2)、`hierarchical_heading`(3)。

```json
{
  "recommendation": {
    "strategy_id": "custom_delimiter_split",
    "mode": "direct_delimiter",
    "mode_id": 1,
    "mode_desc": "分隔符直切，命中即用",
    "params": {
      "target_length": 220,
      "overlap_ratio": 0.15,
      "delimiters": ["---"],
      "min_segment_len": 30,
      "max_segment_len": 800
    },
    "candidates": {"custom_delimiter_split": 1.0},
    "delimiter_hits": 6,
    "profile": {
      "heading_ratio": 0.0,
      "list_ratio": 0.0,
      "table_ratio": 0.0,
      "code_ratio": 0.0,
      "p90_para_len": 24,
      "p50_para_len": 24,
      "digit_symbol_ratio": 0.75,
      "samples": ["a---b---c---d---e---f"]
    },
    "notes": "分隔符命中触发",
    "segments": null
  }
}
```
