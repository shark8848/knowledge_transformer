# 错误码与说明

服务返回结构：

```json
{
  "status": "failure",
  "error_code": "ERR_AUTH_INVALID",
  "error_status": 4011,
  "message": "Authentication failed: invalid appid or key",
  "zh_message": "认证失败，appid或key错误",
  "task_id": null
}
```

| 错误码 | HTTP 状态 | 业务码 | 中文描述 | 英文描述 | 典型触发场景 |
| --- | --- | --- | --- | --- | --- |
| `ERR_AUTH_MISSING` | 401 | 4010 | 认证信息缺失 | Missing authentication information | 未携带 `appid/key` 或者为空 |
| `ERR_AUTH_INVALID` | 401 | 4011 | 认证失败，appid或key错误 | Authentication failed: invalid appid or key | appid 不存在或 key 错误 |
| `ERR_FILE_TOO_LARGE` | 400 | 4201 | 单个文件大小超出限制 | File exceeds per-format size limit | 文件体积超过 `per_format_max_size_mb` |
| `ERR_BATCH_LIMIT_EXCEEDED` | 400 | 4202 | 批量任务超出数量或体积限制 | Batch exceeds allowed number or total size | 文件数量或总大小超过阈值 |
| `ERR_FORMAT_UNSUPPORTED` | 400 | 4203 | 文件格式暂不支持 | Unsupported source format | 无可用插件或配置未声明 |
| `ERR_TASK_FAILED` | 500 | 5001 | 任务执行失败 | Conversion task failed | Celery 入队失败或插件异常 |

所有错误码在 `src/rag_converter/errors.py` 统一注册，并可扩展以满足企业自定义规范，推荐在新增业务能力时同步更新此文档。
