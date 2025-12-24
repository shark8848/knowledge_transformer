# 1. Pipeline API 说明

本文档面向外部使用者，描述 `pipeline_service` 提供的 HTTP API 以及端到端「转换 → 探针 → 策略推荐」的编排逻辑。实现位置：`src/pipeline_service/app.py`、`src/pipeline_service/tasks.py`。

# 2. 总览
- 主要端点
  - `POST /api/v1/pipeline/upload`：上传文件到 MinIO，返回 `bucket` 与 `object_key`。
  - `POST /api/v1/pipeline/recommend`：提交文件列表，执行转换（必要时）→ 探针抽样 → 策略推荐，可同步返回结果或仅返回 `task_id`。
- 编排链路
  - **PDF 直通**：所有文件满足 `source_format=pdf`（或 `application/pdf`）、`target_format=pdf` 且提供 `object_key` 时，跳过转换，直接执行 `pipeline.extract_and_probe`。
  - **常规链路**：`conversion.handle_batch` → `pipeline.extract_and_probe`。
  - 探针阶段会提取 PDF 或 Markdown 的抽样文本并调用 `probe.extract_signals` 与 `probe.recommend_strategy` 两个 Celery 任务。
- 队列与职责
  - 转换：`conversion_queue`
  - 探针/推荐：`probe_queue`
  - 编排（extract/probe）：`pipeline_queue`

# 3. 认证与请求格式
- 认证：沿用网关/上游配置，当前 pipeline API 默认不强制 AppId/Key（视部署而定）。
- 数据格式：请求体为 JSON；`/upload` 使用 `multipart/form-data`。

# 4. 数据模型

## 4.1 FilePayload
| 父参数 | 子参数 | 类型 | 必填 | 取值范围 | 说明 |
| --- | --- | --- | --- | --- | --- |
| files[i] | source_format | string | ✓ | 常见办公/多媒体格式 | 源格式，如 `pdf`/`docx`/`html` |
| files[i] | target_format | string | ✗ | `pdf`/`md` 等 | 目标格式，默认 `pdf`；会经 `prefer_markdown_target` 做合理化处理 |
| files[i] | input_url | string | ✗ | http/https URL | 源文件 HTTP(s) 地址（与 object_key/base64_data 三选一） |
| files[i] | object_key | string | ✗ | 任意字符串 | MinIO 对象键（与 input_url/base64_data 三选一） |
| files[i] | base64_data | string | ✗ | base64 文本 | 内联 base64 内容（与 input_url/object_key 三选一） |
| files[i] | filename | string | ✗ | 任意 | 搭配 base64_data 的文件名 |
| files[i] | size_mb | number | ✗ | >0 | 文件大小（MB），便于校验 |
| files[i] | page_limit | number | ✗ | >=0 | 文档裁剪页数；`0` 表示全文，未传则按 `sample_pages` 抽样 |
| files[i] | duration_seconds | number | ✗ | >=0 | 音视频裁剪时长（秒） |

## 4.2 PipelineRequest
| 父参数 | 子参数 | 类型 | 必填 | 取值范围 | 说明 |
| --- | --- | --- | --- | --- | --- |
| - | files | FilePayload[] | ✓ | 长度>=1 | 待处理文件列表 |
| - | priority | string | ✗ | `low`/`normal`/`high` | 任务优先级标记，默认 `normal`（当前编排未使用） |
| - | callback_url | string | ✗ | URL | 预留字段，当前未在 pipeline 内使用 |
| - | storage | object | ✗ | - | 预留字段，当前未覆盖 MinIO 设置 |
| - | async_mode | bool | ✗ | `true`/`false` | `false` 同步等待；`true` 仅返回 `task_id` |

## 4.3 PipelineResponse
| 父参数 | 子参数 | 类型 | 取值范围 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | - | string | UUID | Celery 任务 ID |
| status | - | string | `accepted`/`success` | `accepted`（异步）或 `success`（同步完成） |
| result | - | object? | - | 同步模式返回的结果；异步为 null |
| result | conversion | object | - | conversion.handle_batch 的返回（含 results 列表），见 4.3.1 |
| result | profile | object | - | probe.extract_signals 的画像输出，见 4.3.2 |
| result | recommendation | object | - | probe.recommend_strategy 的推荐输出，见 4.3.3 |

### 4.3.1 result.conversion
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| task_id | string | conversion.handle_batch 的任务 ID |
| results | array | 转换结果列表，元素结构同转换服务输出 |

### 4.3.2 result.profile
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| heading_ratio/list_ratio/table_ratio/code_ratio/... | number | 画像特征，数值已四舍五入 |
| p90_para_len/p50_para_len | number | 段落长度分位数 |
| digit_symbol_ratio | number | 数字/符号占比（如有） |
| samples | string[] | 抽样文本片段 |

### 4.3.3 result.recommendation
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| strategy_id | string | 推荐的策略 ID |
| params | object | 策略参数（target_length/overlap_ratio 等） |
| candidates | object? | 候选策略得分（可选） |
| delimiter_hits | number | 分隔符命中数量 |
| profile | object | 回传画像（与 4.3.2 一致，已四舍五入） |
| notes | string | 备注/路由提示 |

同步模式下 `result`（`pipeline.extract_and_probe` 输出）：
```json
{
  "conversion": {
    "task_id": "...",           // 来自 conversion.handle_batch
    "results": [
      {
        "source": "docx",
        "target": "pdf",
        "status": "success",
        "object_key": "converted/.../report.pdf",
        "download_url": "http://localhost:9000/qadata/converted/.../report.pdf",
        "output_path": null,
        "metadata": {"note": "passthrough pdf"}
      }
    ]
  },
  "profile": {
    "heading_ratio": 0.12,
    "list_ratio": 0.04,
    "table_ratio": 0.0,
    "code_ratio": 0.0,
    "p90_para_len": 180,
    "p50_para_len": 120,
    "digit_symbol_ratio": 0.05,
    "samples": ["...抽样文本..."]
  },
  "recommendation": {
    "strategy_id": "heading_block_length_split",
    "params": {"target_length": 180, "overlap_ratio": 0.15},
    "candidates": {"heading_block_length_split": 1.2, "sentence_split_sliding": 0.4},
    "delimiter_hits": 0,
    "profile": {"heading_ratio": 0.12, ...},
    "notes": "推荐的策略仅供参考"
  }
}
```

# 5. 端点列表
- `POST /api/v1/pipeline/upload`：上传文件到 MinIO。
- `POST /api/v1/pipeline/recommend`：执行转换 → 探针 → 策略推荐（同步/异步）。

# 6. API 详解

## 6.1 POST /api/v1/pipeline/upload
- 功能：将上传文件写入 MinIO，返回 `bucket`、`object_key`。
- 请求：`multipart/form-data`，字段 `file`。
- 响应示例：
```json
{"bucket": "qadata", "object_key": "uploads/<uuid>_demo.pdf"}
```

- 请求参数

| 父参数 | 子参数 | 类型 | 必填 | 取值范围 | 说明 |
| --- | --- | --- | --- | --- | --- |
| - | file | binary | ✓ | 任意文件 | 待上传文件，文件名将用于生成 `object_key` 后缀 |

- 响应字段

| 字段 | 类型 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| bucket | string | 存储桶名 | 目标存储桶名称 |
| object_key | string | 对象键 | 上传后的对象键，可直接用于后续转换/推荐请求 |

## 6.2 POST /api/v1/pipeline/recommend
- 功能：执行转换 → 探针 → 策略推荐；支持同步/异步。
- 入参：`PipelineRequest`。
- 编排逻辑：
  - PDF 直通：全部 `pdf` 且已有 `object_key` → 直接 `pipeline.extract_and_probe`。
  - 常规：`conversion.handle_batch` → `pipeline.extract_and_probe`。
- 同步：`async_mode=false`，等待最长 `conversion_timeout_sec + probe_timeout_sec`。
- 异步：`async_mode=true`，立即返回 `task_id`。
- 请求示例（同步）：
```json
{
  "files": [
    {
      "source_format": "docx",
      "target_format": "pdf",
      "input_url": "https://example.com/report.docx",
      "page_limit": 5
    }
  ],
  "async_mode": false
}
```
- 响应示例（同步 success）：
```json
{
  "task_id": "c1c2f...",
  "status": "success",
  "result": { "conversion": {"results": [...]}, "profile": {...}, "recommendation": {...} }
}
```
- 响应示例（异步 accepted）：
```json
{"task_id": "c1c2f...", "status": "accepted", "result": null}
```

- 请求参数

| 父参数 | 子参数 | 类型 | 必填 | 取值范围 | 说明 |
| --- | --- | --- | --- | --- | --- |
| files | - | FilePayload[] | ✓ | 长度>=1 | 文件列表，至少一项，详见 4.1 |
| priority | - | string | ✗ | `low`/`normal`/`high` | 任务优先级标记，默认 `normal`（当前未使用） |
| callback_url | - | string | ✗ | URL | 预留字段，当前未在 pipeline 内使用 |
| storage | - | object | ✗ | - | 预留字段，当前未覆盖 MinIO 设置 |
| async_mode | - | bool | ✗ | `true`/`false` | `false` 同步等待返回结果；`true` 仅返回 `task_id` |

- 响应字段

| 父参数 | 子参数 | 类型 | 取值范围 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | - | string | UUID | Celery 任务 ID |
| status | - | string | accepted/success | `accepted`（异步）或 `success`（同步） |
| result | - | object? | - | 同步模式的完整结果；异步为 null |
| result | conversion | object | - | conversion.handle_batch 的返回（含 results 列表），见 4.3.1 |
| result | profile | object | - | probe.extract_signals 的画像输出，见 4.3.2 |
| result | recommendation | object | - | probe.recommend_strategy 的推荐输出，见 4.3.3 |

# 7. 行为与边界
- 抽样：PDF 默认按页抽样（比例 + 上限 10 页），Markdown 按段落前 N 段；受 `sample_pages`、`sample_char_limit` 配置影响。
- 分隔符策略：`probe.recommend_strategy` 支持自定义分隔符，当前 API 未暴露；如需透传需扩展请求模型并调整 app 层。
- 直通条件：仅当源/目标均为 PDF 且提供 `object_key` 时生效；否则执行转换。
- 失败行为：转换失败或探针无样本会导致同步 500 或异步任务失败。

# 8. 相关代码
- FastAPI 入口与路由：`src/pipeline_service/app.py`
- Celery 编排与探针任务：`src/pipeline_service/tasks.py`
- 探针/推荐实现：`src/slicer_service/recommendation.py`（通过 Celery 任务 `probe.*` 调用）

# 9. 变更建议
- 推荐对外仅暴露 `/api/v1/pipeline/recommend`，内部统一委派 `pipeline.run_document_pipeline`，避免双逻辑漂移。
- 如需暴露分隔符自定义、存储覆盖等高级能力，需扩展 `PipelineRequest` 并透传到下游任务。
