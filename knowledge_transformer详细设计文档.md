# knowledge_transformer 详细设计文档

## 文档规范化转换服务引擎

### 1. 设计原则

1. **参数全配置化**：资源限制、鉴权、监控等能力都可通过 YAML / 环境变量动态调节，并支持热重载。
2. **资源与安全限制**：按格式与全局定义文件大小/批量上限，API 层使用 appid/key 鉴权，支持 CLI 管理。
3. **错误码体系**：集中式错误码映射 HTTP 状态与业务状态，支持多语言描述，方便排障与对接（详见文末《附录：错误码总览》）。
4. **插件化架构**：转换逻辑以插件形式装配，可运行时发现新插件并快速扩展支持的格式。
5. **细粒度转换控制**：文档格式支持 `page_limit` 截断 PDF 页数；音视频支持 `duration_seconds` 裁剪时长，API 校验后透传到插件执行。
6. **可观测性**：结构化日志、Tracing ID、Prometheus 指标、Flower 监控以及健康检查接口，提升可运维性。
7. **异步高并发处理**：所有任务通过 Celery 执行，提供 Webhook、Result Backend、对象存储下载、预签名 URL 等多种结果获取方式，显著降低 API 阻塞。

### 2. 实现描述
文档规范化转换服务引擎核心功能为实现覆盖 Office、矢量图、音视频等多种常见格式的转换服务。提供 REST API 与 Celery 异步任务双通道能力。FastAPI 接收文档转换请求并立即返回 `task_id`，Celery 异步调度任务，Worker 通过插件体系（LibreOffice / Inkscape / FFmpeg 等）执行转换。结果统一存储在对象存储服务器中，消费端可通过 Result Backend 轮询、Webhook 回调或直接访问对象存储获取文件。Celery Pipeline 可以直接调用 Celery 任务，利用 Chain/Group/Chord 等编排方式实现串行、并行及聚合流程。

### 3. 处理流程
- **内部处理流程**

    ```mermaid
    sequenceDiagram
        participant API as API 层
        participant Q as Redis 队列/Result Backend
        participant W as Celery Worker
        participant P as 转换插件
        participant S as 对象存储
        participant CB as 回调客户端
        API->>API: 校验输入并生成 task_id
        API->>Q: 封装 conversion.handle_batch
        Q-->>W: 下发任务
        W->>S: 下载源文件或外部 URL
        W->>P: 调用插件执行转换
        P-->>W: 返回转换产物

        W->>S: 上传至 converted/task_id/ 目录
        W->>API: 记录 results[]
        alt callback_url 已配置
            API->>CB: 触发 Webhook 通知
        else 未配置
            API-->>API: 等待客户端自行查询
        end
    ```
  
  1. 接口校验输入，生成 `task_id`。
  2. 将任务封装为 `conversion.handle_batch` 并推送到 Redis 队列。
  3. Worker 拉取任务，下载源文件（对象存储 / 外部 URL）。
  4. 调用相应插件执行转换，并上传到对象存储 `converted/{task_id}/` 路径。
  5. 记录 `results[]` 并根据是否设置 `callback_url` 执行回调。

- **外部交互时序**

    ```mermaid
    sequenceDiagram
      participant C as 客户端
      participant API as API 层
      participant R as Redis 队列/Result Backend
      participant W as Celery Worker
      participant M as 对象存储
      participant Mon as Flower/Prometheus
      C->>API: POST /api/v1/convert
      API-->>C: 202 Accepted + task_id
      API->>R: 推送 conversion.handle_batch
      R->>W: 下发任务
      W->>M: 下载源文件/上传结果
      W-->>R: 更新结果与状态
      alt callback_url 设置
        W->>C: Webhook 通知
      else 轮询/直连
        C->>R: 查询状态
        C->>M: 下载成品
      end
      Mon-->>API: 暴露指标
      Mon-->>W: 任务监控
    ```

  1. 客户端（或 Pipeline Celery 任务）向 `/api/v1/convert` 提交批量文件，附带回调、优先级等元数据；API 完成校验后立即写入 Redis 队列。
  2. API 以 HTTP 202 返回 `task_id` 与查询提示，客户端可用该 ID 轮询 Result Backend 或等待回调。
  3. Celery Worker 执行完成后，根据配置触发 Webhook、更新 Result Backend，并将成品上传对象存储；客户端随后可通过 Webhook、Result Backend 或直接访问对象存储下载成品。
  4. Flower 与 Prometheus 持续收集 API/Worker 状态、队列深度与指标，支持运维侧查看单任务轨迹或设置告警阈值。

### 4. 核心算法
- **调度算法**：基于 Celery 的多队列与优先级调度。
  - **原理**：不同格式或业务线可绑定到独立队列，队列内通过 `priority` 标签和 `prefetch_multiplier` 控制 worker 抢占顺序，配合 `task_time_limit`、`soft_time_limit` 与 `acks_late` 机制，确保长耗时任务不会阻塞短任务，且失败可按需重试。
  - **核心逻辑**：API 层根据 `files[]` 的目标插件、批量大小和 SLA 计算 priority，统一封装为 `conversion.handle_batch`。Worker 启动时声明可消费的队列列表，并在拉取任务前根据 `max_tasks_per_child`、并发数设置可承载的批次数。执行过程中，若检测到单批超过 `batch_size` 或运行超时，任务立即失败并写入结果，剩余文件回退到队列重试，从而避免单个任务占用全部资源。

  **伪代码：**
  ```pseudo
  function submit_request(files, metadata):
    priority = calc_priority(files, metadata.sla)
    batch = split_files(files, metadata.batch_size)
    for chunk in batch:
      payload = build_payload(chunk, priority, metadata)
      push_to_queue(select_queue(chunk.plugin), payload)

  worker_loop():
    settings = load_runtime_limits()
    while worker_alive():
      task = fetch_from_queue(settings.prefetch)
      if not task:
        continue
      with deadline(settings.task_time_limit):
        try:
          for file in task.files:
            artifact = run_plugin(file)
            upload_to_storage(task.task_id, artifact)
          ack(task)
        except TimeoutError:
          mark_failed(task, "timeout")
          requeue_remaining(task)
        except Exception as exc:
          mark_failed(task, str(exc))
          maybe_retry(task)
  ```
- **解析算法**：
  - 文档：利用 LibreOffice headless `soffice` 完成 Office→PDF/HTML/文本等格式转换。API 层先为每个任务创建独立临时目录，将对象存储或 URL 下载的源文件写入本地，再根据 `source_format` 选择对应 filter（如 `--convert-to pdf:writer_pdf_Export`）。执行流程：① 建立隔离 `tmpdir`；② 调用 `soffice` 并传入 `--headless --norestore --nodefault` 等参数，避免互相干扰；③ 监听退出码与 stderr，若失败则根据错误码映射业务状态；④ 成功后校验产物完整性，将文件上传对象存储，并清理 `tmpdir`。


  - 图像/矢量：Inkscape CLI 作为统一渲染器，先将 SVG/EPS/PDF 等矢量格式解析成中间对象，再按业务预设输出 PNG/JPEG/WebP。转换流程包含三步：① 基于 `--export-area-drawing` 自动裁剪透明留白；② 根据目标分辨率与 `dpi` 参数动态缩放，确保像素密度一致；③ 如需水印、轮廓描边或背景填充，通过 Inkscape `--actions` 注入自定义命令。批量图标场景下启用无头模式并发执行，完成后统一上传对象存储。
    - **输出流程示例**：
      1. 解析输入：加载源文件，若为 PDF/EPS 先转换为 Inkscape 支持的内部 SVG。
      2. 预处理：执行裁剪、缩放、背景填充与滤镜动作，生成临时工作文件。
      3. 渲染导出：根据 `target_format` 选择 PNG/JPEG/WebP，设置 DPI/压缩质量后输出到 `/tmp/rag_converter/<task>`。
      4. 元数据记录：统计分辨率、文件大小、色彩空间等信息，写入 `results[]`。
      5. 上传与清理：上传对象存储 `converted/{task_id}/`，完成后删除临时文件。

    ```mermaid
    flowchart LR
      A[解析输入<br/>SVG/EPS/PDF] --> B[预处理<br/>裁剪/缩放/背景]
      B --> C[渲染导出<br/>PNG/JPEG/WebP]
      C --> D[记录元数据<br/>分辨率/体积]
      D --> E[上传对象存储<br/>converted/task_id/]
      E --> F[清理临时目录]
    ```
  - 音视频：FFmpeg 提供模板化参数集，按 `source_format`/`target_profile` 选择不同 Preset（帧率、比特率、采样率、编码器），可透传 `duration_seconds` 以 `-t` 截断输出时长。调用链路先拼装基础指令，再叠加业务侧自定义滤镜（如裁剪、降噪、字幕）或压缩策略（CRF、ABR、两遍编码）。任务执行时会根据文件长度动态估算超时时间，并在失败后回退到保守参数或转码降级方案。
    - **场景样例**：
      1. `webm→mp4`：高码率直播回放转 MP4，使用 x264 Baseline + CRF 23，附带音轨统一到 AAC 128kbps。
      2. `wav→mp3`：语音识别前的批量降采样，固定 16kHz/单声道，并在滤镜中追加噪声抑制。
      3. `mov→mp4`：移动端拍摄素材导出，按分辨率选择 H.265 或 H.264，两遍编码以控制目标文件大小。
      4. `gif→mp4/png`：动图转视频与首帧截图，先以调色板 + scale 滤镜去抖动，再并行输出 MP4 与 PNG。

### 5. 通用lib设计
- `rag_converter.plugins`：定义插件抽象基类与注册表，支持热插拔。
  - `ConversionInput/ConversionResult` 数据类：封装 `source_format`、`target_format`、`input_path`/`input_url`/`object_key` 及扩展 `metadata`，输出侧对应 `output_path`、`object_key`、`metadata`。
  - 核心工具函数：

    | 工具/方法 | 输入参数 | 输出/说明 |
    |-----------|----------|-----------|
    | `ConversionPlugin.convert(payload)` | `payload: ConversionInput`（单次转换上下文） | 返回 `ConversionResult`，描述生成文件的路径/对象键及附加元数据；由具体插件实现。 |
    | `ConversionPlugin.describe()` | 无 | 字典：`slug/source/target`，供 `/api/v1/formats` 暴露能力。 |
    | `PluginRegistry.register(plugin_cls)` | `plugin_cls: Type[ConversionPlugin]` | 将插件注册到 `(source,target)` 键表；若重复注册抛出 `ValueError`。 |
    | `PluginRegistry.get(source, target)` | `source:str`, `target:str` | 按格式返回插件实例，未找到抛出 `KeyError`。 |
    | `PluginRegistry.list()` | 无 | 生成器，依次返回所有插件实例，可用于枚举可用格式。 |
    | `load_plugins(module_names=None)` | `module_names: Iterable[str]`（可选，自定义插件模块列表） | 依次 `import_module`，触发模块侧的注册副作用；默认载入内置插件。 |
    | `read_plugin_module_file(path)` | `path: str|Path` 指向 YAML 配置文件 | 返回字符串列表，代表要动态加载的插件模块路径；文件不存在则返回空列表。 |
    | `write_plugin_module_file(path, modules)` | `path: str|Path`，`modules: Iterable[str]` | 将唯一模块集合写入 YAML（`{"modules": [...]}`），用于 CLI/运维同步配置。 |
- `scripts/manage_plugins.sh`：统一插件注册、依赖维护与安装脚本。
- `rag_converter.monitoring`：暴露 API/Worker 两套 Prometheus 指标。
  | 函数 | 输入参数 | 输出/说明 |
  |------|----------|-----------|
  | `ensure_metrics_server(port)` | `port:int` Prometheus 暴露端口 | 启动一次性指标 HTTP Server，并记录日志。 |
  | `record_task_accepted(priority)` | `priority:str` | 将 `conversion_tasks_accepted_total` 指标 +1。 |
  | `record_task_completed(status)` | `status:str` | 将 `conversion_tasks_completed_total` 指标 +1，并区分成功/失败。 |
  | `collect_dependency_status(settings, celery_app)` | `settings:Settings`，`celery_app:Celery` | 返回字典 `{redis,minio,celery}`，同时更新 `QUEUE_DEPTH`、`CELERY_WORKERS`。 |
  | `_check_redis(settings)` | `settings:Settings` | 内部调用，探测 Redis 并更新 `QUEUE_DEPTH`（返回 "ok"/错误）。 |
  | `_check_minio(settings)` | `settings:Settings` | 内部调用，探测对象存储连通性（返回 "ok"/错误码）。 |
  | `_check_celery_workers(celery_app)` | `celery_app:Celery` | 内部调用，统计活跃 Worker 数并返回状态。 |
- `rag_converter.logging`：集中式日志封装，提供结构化 JSON、Trace/TaskID 注入、模块化采样策略，并内置标准格式（访问日志、任务日志、插件调试日志）。与 FastAPI/Celery 中间件集成，支持将关键事件输出到 stdout 或外部日志代理（如 Loki、ELK）。
  | 函数 | 输入参数 | 输出/说明 |
  |------|----------|-----------|
  | `configure_logging(settings)` | `settings:LoggingSettings`（含 level、log_dir、滚动策略） | 创建日志目录，配置标准 logging + structlog，启用控制台和文件 Handler。 |
- `pipeline_service` 示例：包含 Celery 客户端与 Pipeline 自身任务，可在模块内或其他项目复用。
  | 函数/方法 | 输入参数 | 输出/说明 |
  |------------|----------|-----------|
  | `CeleryConverterClient.submit_conversion_chain(files, priority)` | `files:List[Dict]`，`priority:str` | 创建 `conversion.handle_batch` + `pipeline.quality_check` + `pipeline.post_process` 的 Chain，返回 Celery `task_id`。 |
  | `submit_conversion_group(file_groups, priority)` | `file_groups:List[List[Dict]]` | 并行提交多个转换任务 Group，返回各自 `task_id`。 |
  | `submit_conversion_chord(file_batches, priority)` | `file_batches:List[List[Dict]]` | 创建并行转换 + 聚合回调的 Chord，返回聚合任务 `task_id`。 |
  | `get_result(task_id, timeout)` | `task_id:str`, `timeout:int` | 阻塞等待指定任务完成并返回结果字典。 |
  | `check_status(task_id)` | `task_id:str` | 非阻塞查询任务状态，返回 `status/ready/successful`。 |
  | `quality_check_task(conversion_results)` | `conversion_results:Dict` | Celery 任务，遍历转换结果计算 `quality_score`，输出 `stage=quality_checked`。 |
  | `post_process_task(checked_results)` | `checked_results:Dict` | Celery 任务，对通过质量检查的文件提取文本/向量，输出 `stage=completed`。 |
  | `aggregate_results_task(batch_results)` | `batch_results:List[Dict]` | Chord 回调，汇总批次成功率并触发通知，返回统计摘要。 |

### 6. 接口与关键工具（输入/输出）

| 接口/工具 | 输入 | 输出 |
|-----------|------|------|
| `POST /api/v1/convert` | Headers: `X-Appid`, `X-Key`；Body: `task_name`, `priority`, `mode`（`async` 默认 / `sync` 同步执行）、`callback_url`、`storage{endpoint,access_key,secret_key,bucket}`（可选），`files[]`（`source_format`, `target_format`, `input_url`/`object_key`/`base64_data`，可选 `filename`，`size_mb`，可选 `page_limit` 或 `duration_seconds` 二选一） | `status`, `task_id`, `message`, `results`(sync) |
| `GET /api/v1/formats` | Headers: `X-Appid`, `X-Key` | `formats[]`（`source`, `target`, `plugin`） |
| `GET /api/v1/monitor/health` | Headers: `X-Appid`, `X-Key` | `status`, `timestamp`, `dependencies{redis,object_storage,celery_workers}` |
| `GET /healthz` | 无 | `{"status":"ok"}` |
| Celery 任务 `conversion.handle_batch` | `payload = {task_id, files[], priority, callback_url, storage?, requested_by}` | `{ "task_id":..., "results":[{source,target,status,object_key,output_path,metadata,reason}] }` |
| Pipeline `submit_conversion_chain` | `files[]`, `priority` | `AsyncResult.id`（转换→质量检查→后处理） |
| Pipeline `submit_conversion_group` | `file_groups[][]`, `priority` | `task_ids[]`（并行批次） |
| Pipeline `submit_conversion_chord` | `file_batches[][]`, `priority` | `chord_id`（并行+聚合） |


`page_limit` 仅适用于 `doc/docx/html/ppt/pptx`，生成 PDF 后保留前 N 页；`duration_seconds` 仅适用于音视频/动图（`wav/flac/ogg/aac/avi/mov/mkv/webm/mpeg/flv/ts/m4v/3gp/gif`），两者互斥。`mode` 默认 `async` 返回 202 入队；`sync` 单文件同步执行直接返回结果（建议小体积），超时直接失败。不支持的格式或非法参数会在错误信息中携带源文件定位（`input_url`/`object_key`/`filename`），便于排查。

**API 请求/响应示例（含同步模式与错误源定位）：**

请求：
```json
{
  "task_name": "doc-and-audio",
  "mode": "sync",
  "priority": "normal",
  "files": [
    {
      "source_format": "docx",
      "target_format": "pdf",
      "input_url": "https://example.com/report.docx",
      "size_mb": 3.2,
      "page_limit": 5
    }
  ]
}
```

响应（同步成功）：
```json
{
  "status": "success",
  "task_id": "4b52c3e6-5c2a-4f9b-9d3c-17e7f6e3e111",
  "message": "Task completed synchronously",
  "results": [
    {
      "source": "docx",
      "target": "pdf",
      "status": "success",
      "object_key": "converted/4b52c3e6-5c2a-4f9b-9d3c-17e7f6e3e111/report.pdf",
      "metadata": {"page_limit": 5}
    }
  ]
}
```

响应（不支持的格式，附带源文件定位）：
```json
{
  "status": "failure",
  "error_code": "ERR_FORMAT_UNSUPPORTED",
  "error_status": 400,
  "message": "Unsupported format doc->mp4 (source=https://example.com/report.doc)"
}
```

**Celery 任务报文示例（API 校验后入队的有效负载）：**

请求：
```json
{
  "task_id": "f8c6a2fd-9d76-4bf0-9f2f-5e9f6a6e2c11",
  "priority": "normal",
  "files": [
    {
      "source_format": "docx",
      "target_format": "pdf",
      "input_url": "https://example.com/report.docx",
      "size_mb": 3.2,
      "page_limit": 5
    },
    {
      "source_format": "wav",
      "target_format": "mp3",
      "object_key": "audio/interview.wav",
      "size_mb": 48.5,
      "duration_seconds": 30
    }
  ]
}
```

返回（成功 + 失败混合）：
```json
{
  "task_id": "f8c6a2fd-9d76-4bf0-9f2f-5e9f6a6e2c11",
  "results": [
    {
      "source": "docx",
      "target": "pdf",
      "status": "success",
      "object_key": "converted/f8c6a2fd-9d76-4bf0-9f2f-5e9f6a6e2c11/report.pdf",
      "metadata": {"page_limit": 5}
    },
    {
      "source": "wav",
      "target": "mp3",
      "status": "failed",
      "reason": "Input preparation failed (source=audio/interview.wav): FileNotFoundError('...')"
    }
  ]
}
```

### 7. 容错设计
- **内部容错**：
  - 任务级异常捕获（`status=failed` + `reason`）。
  - `task_time_limit=300s`，避免单任务阻塞。
  - 插件临时目录隔离并执行清理。
  - 对象存储上传失败自动重试一次。
- **外部容错**：
  - 统一错误码 + 客户端重试策略。
  - Webhook 失败由调用方重发。
  - Result Backend/对象存储可支撑故障恢复。
  - Pipeline Celery 自带重试/降级机制（只聚合成功结果、回退为轮询等）。

### 8. 约束
- 当前仅支持异步模式；需自行实现同步等待（轮询或 Celery Chain）。
- 默认开启 `appid/key` 认证。
- 依赖 Redis、对象存储、LibreOffice、Inkscape、FFmpeg 等基础组件。
- 文件大小与批量数量受 `config/settings.yaml` 限制。

### 9. 可处理类型

| 源格式 | 目标格式 | 插件/工具栈 | 典型场景 |
|--------|-----------|--------------|-----------|
| `doc`, `docx`, `ppt`, `pptx`, `html` | `docx`, `pdf`, `html` | LibreOffice `soffice` 插件 | 办公文档标准化、合同归档、文本抽取，支持 `page_limit` 裁剪 PDF 页数。 |
| `svg`, `eps`, `pdf` | `png`, `jpeg`, `webp` | Inkscape CLI | 产品图/流程图渲染、批量图标输出。 |
| `gif`, `webp` | `png`, `mp4` | GIF/WebP 插件 + FFmpeg | 动图转静帧、营销素材转视频，可作为视频源接受 `duration_seconds`。 |
| `wav`, `flac`, `ogg`, `aac` | `mp3` | FFmpeg Audio 插件 | 语音识别预处理、播客压缩，支持 `duration_seconds` 裁剪。 |
| `avi`, `mov`, `mkv`, `webm`, `mpeg`, `flv`, `ts`, `m4v`, `3gp` | `mp4` | FFmpeg Video 插件 | 跨平台视频播放、长视频归档，支持 `duration_seconds` 裁剪。 |
| 自定义格式 | 自定义输出 | 第三方/自研插件 | 按需扩展，例如 CAD→PDF、AI→SVG 等。 |

### 10. 数据存储
- **缓存与落盘**：
  - Worker 临时目录 `/tmp/rag_converter/<task>`，任务结束清理。
  - 对象存储 `converted/{task_id}/...` 长期存储，遵循 bucket 生命周期或人工清理；若未提供自定义对象存储地址/凭证则使用缺省 `endpoint=http://localhost:9000`、`access_key=minioadmin`、`secret_key=minioadmin`、`bucket=qadata`。
  - Redis Result Backend 配置过期时间，控制历史任务保留周期。
  - API 请求可在 payload 中透传 `storage.endpoint/access_key/secret_key/bucket` 覆盖单次任务的对象存储目标。
- **环境约束**：Docker/K8s/裸机均可，需保证 CPU、内存与磁盘资源。

### 11. 配置设计
- `config/settings.yaml`：核心配置文件，覆盖 Redis/对象存储、认证、任务限制、监控等。

  | 配置段 | 关键字段 | 说明 |
  |--------|----------|------|
  | `file_limits` | `default_max_size_mb`, `per_format_max_size_mb`, `max_files_per_task` | 控制单文件/总批次大小与数量上限。 |
  | `logging` | `level`, `log_dir`, `max_log_file_size_mb`, `backup_count` | 日志级别、目录与滚动策略。 |
  | `monitoring` | `prometheus_port`, `metrics_interval_sec`, `health_api` 等 | 指标端口、采样周期、健康检查路径。 |
  | `minio` | `endpoint`, `access_key`, `secret_key`, `bucket`, `timeout` | 对象存储连接配置；未覆盖时默认 `http://localhost:9000` / `minioadmin` / `minioadmin` / `qadata`。 |
  | `convert_formats` | `source`, `target`, `plugin` | 受支持的格式映射及默认插件。 |
  | `api_auth` | `required`, `app_secrets_path`, `header_appid` | API 鉴权开关与凭证路径。 |
  | `celery` | `broker_url`, `result_backend`, `task_time_limit_sec`, `prefetch_multiplier` | 任务调度与执行限制。 |
  | `rate_limit` | `enabled`, `interval_sec`, `max_requests` | API 限流配置。 |
  | 其他 | `service_name`, `plugin_modules_file` 等 | 服务元数据与插件配置文件路径。 |
- 环境变量（前缀 `RAG_`）：可覆盖 YAML；示例：`RAG_REDIS_URL`、`RAG_MINIO_ENDPOINT`、`RAG_API_AUTH_REQUIRED`。
  | 环境变量 | 影响字段 | 说明 |
  |-----------|----------|------|
  | `RAG_REDIS_URL` | `celery.broker_url/result_backend` | 覆盖 Celery Broker/Result Backend。 |
  | `RAG_MINIO_ENDPOINT` | `minio.endpoint` | 切换对象存储地址（如 Docker 网络内服务名）。 |
  | `RAG_API_AUTH_REQUIRED` | `api_auth.required` | 控制是否启用 API 鉴权。 |
  | `RAG_FILE_LIMIT_MAX_SIZE` | `file_limits.default_max_size_mb` | 调整默认文件大小限制。 |
  | `RAG_PROM_PORT` | `monitoring.prometheus_port` | 重定义 Prometheus 端口。 |
  | 其他 `RAG_*` | 任意配置键（驼峰→下划线） | 通过 `pydantic-settings` 自动映射，便于 K8s/Compose 注入。 |
- CLI/脚本：`manage_plugins.sh`、`make_key.sh` 等辅助配置管理。
  | 脚本 | 主要功能 | 输入/输出 |
  |------|----------|-----------|
  | `manage_plugins.sh` | 列出/安装/移除插件模块与依赖；同步 `config/plugins.yaml` | 命令行参数（如 `list/install/remove`）；输出操作日志与更新后的配置。 |
  | `make_key.sh` | 生成 API `appid/key`，写入 `secrets/appkeys.json` | 可选 `--appid` 指定 ID；输出新密钥并追加到文件。 |
  | `docker-start.sh`/`stop.sh` | 一键启动/停止 Docker Compose 组件 | 读取 `.env`，调用 `docker compose up/down`；输出各容器状态。 |
  | `show_server.sh` | 汇总 API/Worker/对象存储/Redis 状态 | 无输入；调用健康检查并打印表格。 |

### 12. 初始化参数设计
- `start_server.sh`：加载配置后启动 FastAPI、Celery Worker 与 Flower。

  | 组件 | 启动命令 | 关键环境变量/参数 | 输出 |
  |------|-----------|-------------------|------|
  | FastAPI | `uvicorn rag_converter.app:app --host 0.0.0.0 --port ${API_PORT}` | `RAG_CONFIG_FILE`, `API_PORT` | 启动 REST API（默认 8000），日志写入 `logs/api.log`。 |
  | Celery Worker | `celery -A rag_converter.celery_app.celery_app worker -l ${CELERY_LOG_LEVEL}` | `CELERY_LOG_LEVEL`, `RAG_CONFIG_FILE` | 消费转换任务，日志 `logs/celery.log`。 |
  | Flower | `celery -A rag_converter.celery_app.celery_app flower --port ${FLOWER_PORT}` | `FLOWER_PORT`, `RAG_CONFIG_FILE` | 提供 Celery UI 监控，日志 `logs/flower.log`。 |

- Celery Worker 与 Pipeline Celery：通过 `.env` 中的 `CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND`、`MINIO_*` 等参数初始化；队列名称、优先级、超时均可配置。

  | 模块 | 关键变量 | 作用 |
  |------|-----------|------|
  | 转换引擎 Worker | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_DEFAULT_QUEUE`, `CELERYD_PREFETCH_MULTIPLIER`, `TASK_TIME_LIMIT`, `MINIO_*` | 指定 Broker/Backend，限制预取/超时，并提供对象存储凭据。 |
  | Pipeline Celery | `BROKER_URL`, `RESULT_BACKEND`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `PIPELINE_QUEUE` | 连接共享 Redis，访问转换结果与对象存储，配置工作流队列。 |

### 13. 外部工具

| 组件 | 最低版本/要求 | 用途 |
|------|---------------|------|
| FastAPI | ≥ 0.104 | 提供 REST API 接口层。 |
| Celery | ≥ 5.3 | 异步任务调度执行。 |
| Redis | ≥ 7 | 作为 Celery Broker/Result Backend。 |
| 对象存储 | S3 兼容（如 MinIO） | 存放输入/输出文件。 |
| LibreOffice | 最新 LTS | 文档格式转换。 |
| Inkscape | ≥ 1.3 | 矢量图批量渲染。 |
| FFmpeg | ≥ 5.0 | 音视频转码/滤镜。 |
| Flower | ≥ 1.2 | Celery 监控 UI。 |
| Prometheus | ≥ 2.46 | 指标采集与告警。 |

- Python 依赖见 `pyproject.toml`；Pipeline 示例的 `requirements.txt` 已在 README 中说明。

### 14. 单元测试设计
- **测试工具**：pytest + HTTPX，Celery test worker，对象存储 mock 或本地实例。
- **测试集**：覆盖所有格式、极大/极小文件、非法参数、权限失败、Webhook 失败、部分任务失败以及 Pipeline Chain/Group/Chord 场景。
- **场景文件列表示例**：

  | 文件名 | 源格式 → 目标格式 | 大小 (MB) | 用途 |
  |--------|-------------------|-----------|------|
  | `doc_sample_small.doc` | `doc → docx` | 0.05 | 最小文件验证（极小文件处理 + Pipeline Chain）。 |
  | `doc_sample_pdf.doc` | `doc → pdf` | 0.05 | 文档直转 PDF，验证 soffice 输出及 `page_limit=5` 截断。 |
  | `docx_sample.docx` | `docx → pdf` | 0.1 | DOCX 转 PDF（含 `page_limit` 截断与内联 base64 上传）。 |
  | `html_inline_base64.json` | `html(base64) → pdf` | 0.01 | 富文本内联（base64_data）到 PDF 的链路验证。 |
  | `ppt_marketing.ppt` | `ppt → pdf` | 48 | 常规文档转换，验证多页结构与 `page_limit`。 |
  | `pptx_demo.pptx` | `pptx → pdf` | 20 | PPTX 转 PDF，覆盖页数截断与 LibreOffice 过滤。 |
  | `svg_logo.svg` | `svg → png` | 0.8 | 图像/矢量流程 + Pipeline Group。 |
  | `gif_banner.gif` | `gif → mp4` | 25 | 动图转视频，检查对象存储上传与回调。 |
  | `webp_large.webp` | `webp → png` | 15 | 静态图较大文件，用于对象存储异常注入。 |
  | `wav_podcast.wav` | `wav → mp3` | 180 | 大音频文件（接近限制），测试超时与分片策略。 |
  | `flac_archive.flac` | `flac → mp3` | 220 | 超限文件，触发 `FILE_TOO_LARGE` 场景。 |
  | `mov_trailer.mov` | `mov → mp4` | 480 | 视频大型文件（接近 500MB），检验性能与 Pipeline Chord。 |
  | `mkv_fail.mkv` | `mkv → mp4` | 300 | 插件模拟失败，测试部分任务失败回滚。 |
  | `invalid_format.bin` | `bin → docx` | 1 | 非法参数/不支持格式，期望 HTTP 400 + 错误码。 |
  | `auth_test.docx` | `docx → pdf` | 2 | API key 失效场景，确保返回 401。 |
  | `webhook_payload.json` | - | - | Webhook 失败（模拟 500/timeout）场景。 |
- **测试用例（Mock 场景）**：

  | 编号 | 分类 | 场景 | Mock 组件 | 输入示例 | 期待输出/断言 |
  |------|------|------|-----------|-----------|----------------|
  | UT-01 | API 层 | API 入参合法性 | Mock Redis + Celery，HTTPX client | `files=2`, `priority=high` | HTTP 202，`task_id` 非空，Celery `delay` 调用 1 次。 |
  | UT-02 | API 层 | 文件大小超限 | Mock `file_limits` 配置 | `size_mb=600` | HTTP 400，错误码 `FILE_TOO_LARGE`，Celery 未被调用。 |
  | UT-03 | Worker | 对象存储下载失败 | Mock MinIO SDK 抛 `S3Error` | `object_key=foo.doc` | `results[0].status=failed`，`reason` 含 `S3Error`，日志 Warning。 |
  | UT-04 | Worker | 插件执行成功 | Mock 插件 `convert` 返回 `/tmp/out.docx` | `doc->docx` | `results[0].status=success`，上传对象存储 1 次，返回 `converted/task/file.docx`。 |
  | UT-05 | Worker | 插件超时 | Mock Celery 超时 | `task_time_limit=300s` | 任务 failed，`reason=timeout`，触发 `maybe_retry`。 |
  | UT-06 | 安全 | API Key 管理 | Mock `make_key.sh` + `secrets/appkeys.json` | 创建 `appid=test-client`、删除旧 key | 创建时生成新 key 写入 JSON；删除后旧 key 调用返回 401，新 key 正常。 |
  | UT-07 | 回调 | Webhook 成功/失败 | Mock `requests.post` | `callback_url=https://example.com` | 成功 200，失败 500 + 重试计数，记录 `callback_status`。 |
  | UT-08 | Pipeline | Chain 工作流 | Mock `conversion/quality_check/post_process` | 3 步串行 | 最终 `stage=completed`，`quality_score=0.95`，`vector_count>0`。 |
  | UT-09 | Pipeline | Group + Result Backend | Mock `AsyncResult` | 三个任务 | `len(task_ids)=3`，分别返回 `SUCCESS/FAILURE` 状态。 |
  | UT-10 | 监控 | 依赖检查 | Mock Redis/MinIO/Celery Ping | Redis down | 返回 `{"redis":"error:RedisError"...}`，`QUEUE_DEPTH`=NaN。 |
  | UT-11 | 基础设施 | Logging 配置 | Mock `structlog.configure` | `level=DEBUG`, `log_dir=./logs` | 生成 `logs/service.log`，console+file handler 正常。 |
  | UT-12 | Worker | base64 内联输入 | Mock/真实 MinIO | `base64_data + filename`，`html→pdf` | 任务成功，生成 PDF，`object_key`/本地工件存在，状态 `success`。 |
  | UT-13 | Worker | 对象存储覆盖 | Mock MinIO 客户端 | `storage.endpoint/access_key/secret_key/bucket` 覆盖 + `object_key` 下载 | `_get_minio_client` 使用非缓存配置，下载/上传均指向覆盖的 bucket/endpoint。 |
  | UT-14 | 压测 | 并发混合转换 | 真实 API + ThreadPool | svg→png、wav→mp3、gif→mp4 各 10 条并发 | 30/30 成功；p50≈0.024s，p95≈0.292s，max≈0.295s（并发 10）。 |
  | UT-14 | Worker | DOCX→PDF 插件 | Mock `soffice` 命令 | `docx(base64) → pdf` | 生成 `.pdf` 输出文件，metadata 含 `LibreOffice soffice`，对象存储上传成功。 |
- **优化/边界/异常覆盖**：
  - **性能优化**：在 UT-01/UT-07 基础上增加高并发模拟（pytest-xdist + Celery test worker），观察 `queue_depth` 与 `prefetch_multiplier` 对吞吐的影响。
  - **边界值**：针对 `file_limits`（最小 1KB、最大 500MB）、批次数（1 与上限 10）以及优先级（low/high）设置独立用例，确保阈值附近行为符合预期。
  - **异常路径**：扩展 UT-03/UT-05/UT-06，注入网络抖动、对象存储 5xx、Webhook 超时等异常，验证重试次数、错误码映射与日志完整性。
- **测试评测**：
  - 断言 HTTP/错误码。
  - 验证 Redis 任务状态与对象存储对象存在。
  - 监控 Prometheus 指标变化，执行性能/压力测试。
- **报告样例**：以表格记录测试编号、输入文件/参数、期望结果、实际结果、耗时、系统指标等，便于审计与追踪。
  | 测试编号 | 输入文件/参数 | 期望结果 | 实际结果 | 耗时 (s) | 系统指标 |
  |----------|----------------|-----------|-----------|-----------|-----------|
  | TC-0001 | `doc_sample_small.doc`, `priority=high` | HTTP 202，`task_id` 返回，转换成功 | 同期望 | 2.4 | CPU 35%，内存 +50MB。
  | TC-0002 | `flac_archive.flac (220MB)` | HTTP 400，错误码 `FILE_TOO_LARGE` | 同期望 | 0.8 | 无 Celery 调用，Redis 连接 1 次。
  | TC-0003 | `wav_podcast.wav`, Webhook=200 | `results[].status=success`，Webhook `success` | Webhook 200，回调记录成功 | 65 | Worker CPU 70%，队列深度保持 <5。
  | TC-0004 | `mkv_fail.mkv` + 插件超时 | 任务部分失败，`reason=timeout`，触发重试 | 首次失败，重试后成功 | 310 | Celery 任务数 +2，Prometheus `conversion_tasks_completed_total{status="failed"}` +1。
  | TC-0005 | Pipeline Chain（三文件） | `stage=completed`，`quality_score>0.9` | `stage=completed`，`quality_score=0.95` | 120 | Redis result 节点读写 3 次，Flower 显示 3 步串行完成。
  | TC-0006 | API Key 创建/删除 | 新 key 生效，旧 key 返回 401 | 新 key 鉴权通过，旧 key 401 | 1.2 | `secrets/appkeys.json` 更新一次，API error 日志 +1。 |

  ### 附录：错误码总览

  | 错误码 | HTTP 状态 | 业务码 | 描述 | 典型触发场景 | 触发模块/函数 | 触发条件 | 备注 |
  |--------|-----------|--------|------|---------------|----------------|-----------|------|
  | `ERR_AUTH_MISSING` | 401 | 4010 | 认证信息缺失 | 请求未携带 `X-Appid`/`X-Key`。 | `security.authenticate_request` | Header/Query 缺少任意 `appid`/`key` | 记录安全告警并拒绝请求。 |
  | `ERR_AUTH_INVALID` | 401 | 4011 | 认证失败，appid 或 key 错误 | 使用无效 key 或记录已删除的 key。 | `security.authenticate_request` | `AppKeyValidator` 校验失败 | `AppKeyValidator` 热加载 `secrets/appkeys.json`。 |
  | `ERR_FILE_TOO_LARGE` | 400 | 4201 | 文件大小超限 | 超过 `per_format_max_size_mb`（如 `flac_archive.flac`）。 | `api.routes._validate_request` | 单文件超过 `Settings.file_limits.per_format_max_size_mb` | 限制值由配置热更新。 |
  | `ERR_BATCH_LIMIT_EXCEEDED` | 400 | 4202 | 批量数量/体积超限 | 超出 `max_files_per_task` 或 `max_total_upload_size_mb`。 | `api.routes._validate_request` | 文件数量或总大小超限 | 多批次循环同样生效。 |
  | `ERR_FORMAT_UNSUPPORTED` | 400 | 4203 | 格式暂不支持 | 未注册插件（如 `invalid_format.bin`）。 | `api.routes._validate_request` | 源/目标格式对不在插件或配置中 | 记录 payload 以便排查。 |
  | `ERR_TASK_FAILED` | 500 | 5001 | 任务执行失败 | 插件崩溃、队列/对象存储异常、内部错误。 | `api.routes.submit_conversion` | `handle_conversion_task.delay` 抛出异常（队列不可用等） | FastAPI 记录异常栈并触发监控。 |

