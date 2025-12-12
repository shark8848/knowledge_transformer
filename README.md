# RAG 文档规范化转换服务引擎

Knowledge Transformer 知识库文档规范化转换服务引擎，围绕“参数全配置化、接口安全、插件化架构、高并发与可观测性”四个核心设计目标展开，支持 REST API 与 Celery 异步任务双通道，覆盖 Office 与多媒体常见格式的批量转换场景。

## 快速开始

### 方式一：Docker 部署（推荐）

使用 Docker Compose 一键部署所有服务（包括 Redis、MinIO、API、Worker、Flower）：

```bash
# 1. 构建镜像
./docker-build.sh

# 2. 启动所有服务
./docker-start.sh

# 3. 查看服务状态
./docker-status.sh
```

访问地址：
- API 文档：http://localhost:8000/api/v1/docs
- Flower 监控：http://localhost:5555
            "output_path": null,
            "metadata": {"note": "Converted via LibreOffice soffice", "page_limit": 5}

详细说明请查看 [Docker 部署文档](docs/docker.md)

### 方式二：本地开发部署

1. **安装系统依赖**：确保主机已安装 `LibreOffice (soffice)`、`Inkscape`、`FFmpeg`，并提供可执行二进制到 `PATH`。
2. **创建虚拟环境并安装 Python 依赖**
    ```bash
    python3 -m venv .venv && source .venv/bin/activate
    pip install -U pip && pip install -e .[dev]
    ```
3. **准备配置与密钥**
    ```bash
    cp config/settings.example.yaml config/settings.yaml
    PYTHONPATH=src python scripts/manage_appkey.py generate
    ```
4. **启动服务与监控**（需要 Redis、MinIO 等依赖）：
    ```bash
    ./start_server.sh     # FastAPI + Celery Worker + Flower
    ./show_server.sh      # 查看 API/Worker/Flower/Redis/MinIO 状态
    # 也可使用 make run / make worker 进行手动调试
    ```

默认 `api_auth.required=true`，调用所有业务接口前需在 `secrets/appkeys.json` 中存在有效的 `appid/key` 组合，并通过 `X-Appid`、`X-Key` 或 URL 参数携带。可通过 `make_key.sh`（或 `make keys`）快速查看/管理密钥。

## 测试与报告

1. **运行完整测试并生成 HTML 报告**
    ```bash
    /home/knowledge_transformer/.venv/bin/python -m pytest \
      --html=test-report.html --self-contained-html
    ```
    以上命令会在仓库根目录输出 `test-report.html`，包含所有用例的通过/失败记录。
2. **启动测试报告服务器**
    ```bash
    TEST_REPORT_PATH=./test-report.html \
    TEST_REPORT_PORT=8088 \
    /home/knowledge_transformer/.venv/bin/python test_report_server.py
    ```
    - `TEST_REPORT_PATH`：可选，指定要发布的 HTML 报告路径，默认指向仓库根目录的 `test-report.html`。
    - `TEST_REPORT_PORT`：可选，默认为 `8088`。
    - 访问 `http://localhost:8088/` 可直接在线查看报告，`/download` 路径可下载原始 HTML 文件，`/healthz` 用于状态探测。

3. **启动 API 文档服务（Swagger/OpenAPI）**
        ```bash
        API_DOCS_PORT=8090 \
        API_DOCS_CONFIG=./config/settings.yaml \
        /home/knowledge_transformer/.venv/bin/python api_docs_server.py
        ```
        - 服务会直接从 FastAPI 应用生成最新的 OpenAPI Schema，并通过 Swagger UI / ReDoc 对外展示。
        - 页面路径：`http://localhost:8090/`（Swagger UI），`http://localhost:8090/redoc`（ReDoc），原始 Schema：`/openapi.json`。
        - Swagger UI 中点击 “Try it out / Execute” 时，会把请求发送到 `API_DOCS_TARGET_URL`（默认 `http://127.0.0.1:8000`），可根据部署拓扑覆盖为对外地址；`API_DOCS_ALWAYS_REFRESH=true` 可强制每次请求前重建 Schema，`API_DOCS_TITLE`、`API_DOCS_FAVICON` 可自定义页面样式。

`test_report_server.py` 与 `api_docs_server.py` 均基于 FastAPI/uvicorn，可单独运行，也会在执行 `start_server.sh` 时自动随主服务一同拉起，对应的状态可通过 `show_server.sh` 查看，`stop_server.sh` 会统一关闭。

4. **示例 API 测试脚本**
    - HTML→PDF（内联 base64）：
        ```bash
        ./scripts/test_pdf_conversion.py
        ```
    - 多场景转换套件（HTML base64 → PDF；DOCX base64 → PDF）：
        ```bash
        ./scripts/test_conversion_suite.py
        ```
        可通过 `DOCX_PATH` 覆盖 DOCX 样例路径；`API_URL`、`API_APPID`、`API_KEY` 覆盖服务地址与凭证。
    - 文档转换套件（含页数截断验证：doc/docx/pptx → pdf 全量 + `page_limit`=5）：
        ```bash
        /home/knowledge_transformer/.venv/bin/python scripts/test_doc_suite.py
        ```
        最近一次结果：39/39 成功（含页数裁剪用例）。
    - 并发混合转换压测（支持 `PAGE_LIMIT` 页数裁剪，覆盖 html/doc/docx/ppt/pptx、svg→png、wav→mp3、gif→mp4 等）：
        ```bash
        PAGE_LIMIT=5 ./scripts/test_concurrent_conversions.py  # 可用 CONCURRENCY、API_URL 等覆盖
        ```
        最近一次在 `PAGE_LIMIT=5` 下通过（并发示例 10）。
    - 所有脚本默认请求 `http://127.0.0.1:8000/api/v1/convert`，使用仓库内 appid/key。

## 技术栈

- **语言**：Python 3.11+
- **Web 框架**：FastAPI + Uvicorn
- **任务队列**：Celery + Redis（示例配置，可替换）
- **配置系统**：Pydantic Settings + YAML、环境变量、命令行覆盖
- **日志与监控**：结构化日志（standard logging + JSON formatter）、Prometheus 指标、内置健康检查 API
- **插件扩展**：基于抽象基类与动态入口注册的格式转换插件

## 顶层结构

```
├── README.md                     # 项目概述与运行指南
├── pyproject.toml                # 依赖与构建配置
├── Makefile                      # 开发与运维常用命令
├── config/
│   ├── settings.example.yaml     # 参数化配置示例
│   └── settings.yaml             # 默认运行配置（可自定义）
├── scripts/
│   ├── manage_appkey.py          # appid/key 生成与删除 CLI
│   └── manage_plugins.sh         # 插件模块注册与依赖管理 Shell 脚本
├── src/
│   └── rag_converter/
│       ├── app.py                # FastAPI 应用入口
│       ├── api/                  # 路由与请求/响应模型
│       ├── celery_app.py         # Celery 应用与任务定义
│       ├── config.py             # 配置加载与热更新钩子
│       ├── errors.py             # 错误码枚举与响应辅助
│       ├── logging.py            # 结构化日志与追踪 ID
│       ├── monitoring.py         # 指标与健康检查
│       └── plugins/              # 插件基类与内置格式适配
├── secrets/
│   └── appkeys.json              # API 授权密钥存储
├── docs/                         # 配置、API、错误码说明
└── tests/
    └── ...
```

## 关键能力

1. **参数全配置化**：所有资源限制、功能开关、监控、认证、输入/输出鉴权均可通过 YAML、环境变量或 CLI 注入，支持热重载策略。
2. **资源与安全限制**：按格式与全局的大小/批量上限，API 默认使用 `appid+key` 认证，可通过 CLI 管理密钥。
3. **错误码体系**：集中式错误码注册（多语言），自动映射 HTTP 状态与业务状态码。
4. **插件化架构**：转换逻辑与格式能力以插件形式装配，支持运行时发现与动态扩展。
5. **细粒度转换控制**：文档类（doc/docx/html/ppt/pptx）支持 `page_limit` 截断 PDF 页数，音视频类支持 `duration_seconds` 裁剪时长，API 校验后透传到插件执行。
6. **可观测性**：结构化日志、追踪 ID、Prometheus 指标以及健康/依赖监控端点。
7. **异步任务处理**：所有转换任务通过 Celery 异步执行，FastAPI 负责接收请求和返回 task_id，避免长时间阻塞连接。支持 webhook 回调、Result Backend 查询等多种结果获取方式。

## API 接口详细说明

所有业务接口默认挂载在 `/api/v1` 路径下，需要在请求头携带 `X-Appid` 和 `X-Key` 进行身份认证（可通过配置关闭）。

### 接口列表

| 接口路径 | 方法 | 功能描述 | 认证要求 |
|---------|------|----------|---------|
| `/api/v1/convert` | POST | 提交批量文档转换任务 | ✓ 需要 |
| `/api/v1/formats` | GET | 查询支持的格式映射列表 | ✓ 需要 |
| `/api/v1/monitor/health` | GET | 服务健康检查与依赖状态 | ✓ 需要 |
| `/healthz` | GET | 轻量级存活检测（容器探针） | ✗ 无需 |
| `http://<host>:9091/metrics` | GET | Prometheus 指标（API 进程） | ✗ 无需 |
| `http://<host>:9092/metrics` | GET | Prometheus 指标（Worker 进程） | ✗ 无需 |
| `http://<host>:5555` | GET | Celery Flower 监控 UI | ✗ 无需 |

### 1. POST /api/v1/convert - 提交转换任务

提交一个或多个文件的批量转换任务，系统将**异步处理**并可选通过 webhook 回调结果。

> **⚠️ 注意：当前仅支持异步模式**
> 
> 本接口返回 HTTP 202 Accepted，任务立即入队后返回 `task_id`。实际转换由 Celery Worker 后台执行，适合以下场景：
> - 大文件转换（视频、音频等可能需要数分钟）
> - 批量任务处理
> - 高并发请求（避免阻塞 API 线程）
> 
> **如需同步转换（阻塞等待结果）**，建议通过以下方式实现：
> 1. 客户端轮询：提交任务后通过 `task_id` 定期查询 Celery Result Backend
> 2. Webhook 回调：在请求中指定 `callback_url`，转换完成后接收推送
> 3. WebSocket 长连接：自行实现 WebSocket 端点订阅任务状态（需扩展开发）
> 
> 异步设计确保 API 服务高可用，避免长时间占用连接资源。

**请求头：**
```
X-Appid: your-app-id
X-Key: your-app-key
Content-Type: application/json
```

**请求体示例：**
```json
{
"task_name": "batch-office-conversion",
"priority": "high",
"mode": "async",
"callback_url": "https://your-service.com/webhook/conversion-complete",
"storage": {
    "endpoint": "http://minio:9000",
    "access_key": "your-ak",
    "secret_key": "your-sk",
    "bucket": "custom-bucket"
},
"files": [
    {
        "source_format": "doc",
        "target_format": "docx",
        "input_url": "https://storage.example.com/documents/report.doc",
        "object_key": "uploads/2025/report.doc",
        "filename": "report.doc",
        "size_mb": 2.5
    },
    {
        "source_format": "svg",
        "target_format": "png",
        "input_url": "https://storage.example.com/images/diagram.svg",
        "size_mb": 0.8,
        "page_limit": null,
        "duration_seconds": null
    },
    {
        "source_format": "wav",
        "target_format": "mp3",
        "object_key": "audio/interview.wav",
        "size_mb": 45.2,
        "duration_seconds": 30
    },
    {
        "source_format": "html",
        "target_format": "pdf",
        "base64_data": "PGh0bWw+PGJvZHk+PGgxPkJhc2U2NCBIVE1MPC9oMT48L2JvZHk+PC9odG1sPg==",
        "filename": "inline.html",
        "size_mb": 0.001,
        "page_limit": 1
    }
]
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `task_name` | string | ✓ | 任务名称，便于追踪 |
| `priority` | string | ✗ | 优先级：`low`/`normal`/`high`，默认 `normal` |
| `mode` | string | ✗ | 执行模式：`async`（默认，入队返回 202）或 `sync`（同步执行并直接返回结果，建议单文件小体积） |
| `callback_url` | string | ✗ | 转换完成后的 webhook 回调 URL |
| `storage` | object | ✗ | 对象存储覆盖信息；未提供时使用服务端缺省配置 |
| `files` | array | ✓ | 待转换文件列表 |
| `files[].source_format` | string | ✓ | 源格式，如 `doc`、`svg`、`wav` |
| `files[].target_format` | string | ✓ | 目标格式，如 `docx`、`png`、`mp3` |
| `files[].input_url` | string | ✗ | 文件下载 URL（与 `object_key`、`base64_data` 三选一） |
| `files[].object_key` | string | ✗ | 对象存储键名（与 `input_url`、`base64_data` 三选一） |
| `files[].base64_data` | string (base64) | ✗ | 内联内容（富文本/二进制）base64 字符串，便于直接传输小文件 |
| `files[].filename` | string | ✗ | 与 `base64_data` 搭配的文件名（未填则根据 `source_format` 推断扩展名） |
| `files[].size_mb` | number | ✓ | 文件大小（MB），用于预检验证 |
| `files[].page_limit` | number | ✗ | 文档类可选：限制转换到 PDF 的页数（从第 1 页开始），适用于 `doc/docx/html/ppt/pptx` |
| `files[].duration_seconds` | number | ✗ | 音/视频可选：裁剪转换时长（秒，t=0 起），适用于 `wav/flac/ogg/aac/avi/mov/mkv/webm/mpeg/flv/ts/m4v/3gp/gif` |

`page_limit` 与 `duration_seconds` 互斥：仅文档格式接受 `page_limit`，仅音视频/动图接受 `duration_seconds`。文档类会在生成 PDF 后裁剪前 N 页，音视频通过 FFmpeg `-t` 从 0 秒截取指定时长。

> 同步模式说明：`mode=sync` 仅支持单文件、小体积场景（建议 <20MB），不建议携带 `callback_url`。执行超时将直接返回错误，避免阻塞 API 线程。

**可选对象存储覆盖：**

```json
"storage": {
    "endpoint": "http://minio:9000",
    "access_key": "your-ak",
    "secret_key": "your-sk",
    "bucket": "custom-bucket"
}
```

不传 `storage` 字段时，服务端使用缺省配置（示例：`endpoint=http://localhost:9000`，`access_key=minioadmin`，`secret_key=minioadmin`，`bucket=qadata`）。

**响应示例（成功，异步入队）：**
```json
{
  "status": "accepted",
  "task_id": "a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f",
  "message": "Task accepted and scheduled for conversion"
}
```

**响应示例（成功，同步模式）：**
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
            "metadata": {"note": "Converted via LibreOffice soffice"}
        }
    ]
}
```

**响应示例（失败）：**
```json
{
  "status": "failure",
  "error_code": "ERR_FILE_TOO_LARGE",
  "error_status": 400,
  "message": "File size exceeds per-format limit"
}
```

**Webhook 回调示例（异步完成）：**
```json
{
    "task_id": "a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f",
    "status": "success",
    "results": [
        {
            "source": "doc",
            "target": "docx",
            "status": "success",
            "object_key": "converted/a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f/report.docx",
            "metadata": {"note": "Converted via LibreOffice soffice"}
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

不在可转换清单内时，错误响应会包含源文件定位信息（如 `input_url`/`object_key`/`filename`），便于快速排查：`"message": "Unsupported format doc->mp4 (source=https://...)"`。

**响应字段：**

| 字段 | 类型 | 说明 |
|-----|------|------|
| `status` | string | `accepted`（异步已入队） / `success`（同步模式直接完成） / `failure`（失败） |
| `task_id` | string | 任务唯一标识符，用于后续查询 |
| `message` | string | 描述信息 |
| `error_code` | string | 错误码（失败时），详见 `docs/error_codes.md` |
| `error_status` | number | HTTP 状态码（失败时） |

**获取转换后的文件：**

转换完成后，系统通过以下方式提供文件访问：

1. **对象存储（推荐方式）**
    - 转换后的文件自动上传到 MinIO/S3 对象存储，目标桶/凭证由配置 `minio.{endpoint,access_key,secret_key,bucket}` 决定
    - 存储路径格式：`converted/{task_id}/{filename}`
    - 示例：`converted/a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f/report.docx`
    - 如未显式提供对象存储地址与凭证，使用缺省配置：`endpoint=http://localhost:9000`，`access_key=minioadmin`，`secret_key=minioadmin`，`bucket=qadata`

2. **Webhook 回调**
   - 如果提交任务时指定了 `callback_url`，转换完成后会 POST 结果到该 URL
   - 回调报文示例：
   ```json
   {
     "task_id": "a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f",
     "results": [
       {
         "source": "doc",
         "target": "docx",
         "status": "success",
         "object_key": "converted/a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f/report.docx",
         "output_path": "/tmp/rag_converter/xyz123_report.docx",
         "metadata": {
           "note": "Converted via LibreOffice soffice"
         }
       },
       {
         "source": "svg",
         "target": "png",
         "status": "success",
         "object_key": "converted/a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f/diagram.png",
         "metadata": {
           "note": "Converted via Inkscape CLI"
         }
       }
     ]
   }
   ```

3. **Celery Result Backend 查询**
   - 使用 `task_id` 从 Redis result backend 查询任务结果
   - Python 示例：
   ```python
   from celery.result import AsyncResult
   from rag_converter.celery_app import celery_app
   
   result = AsyncResult(task_id, app=celery_app)
   if result.ready():
       task_result = result.get()
       for file_result in task_result['results']:
           if file_result['status'] == 'success':
               object_key = file_result['object_key']
               # 从 MinIO 下载文件
               print(f"Download from: {object_key}")
   ```

4. **直接从 MinIO 下载**
   - 使用 MinIO 客户端或 S3 API 下载文件
   - Python 示例（使用 minio 库）：
   ```python
   from minio import Minio
   
   client = Minio(
       "localhost:9000",
       access_key="minioadmin",
       secret_key="minioadmin",
       secure=False
   )
   
   # 下载转换后的文件
   object_key = "converted/a3f7e9d2-xxx/report.docx"
   client.fget_object("qadata", object_key, "local_report.docx")
   ```
   
   - 生成预签名下载 URL（临时访问链接）：
   ```python
   # 生成 1 小时有效的下载链接
   url = client.presigned_get_object("qadata", object_key, expires=3600)
   print(f"Download URL: {url}")
   ```

**文件存储配置：**

在 `config/settings.yaml` 中配置对象存储参数：
```yaml
minio:
  endpoint: "http://localhost:9000"
  access_key: "minioadmin"
  secret_key: "minioadmin"
  bucket: "qadata"
  timeout: 30
```

**实现类似同步的调用方式：**

虽然 API 本身是异步的，但客户端可以通过轮询实现同步等待效果：

```python
import time
import requests
from celery.result import AsyncResult
from rag_converter.celery_app import celery_app

# 1. 提交转换任务
response = requests.post(
    "http://localhost:8000/api/v1/convert",
    headers={"X-Appid": "your-appid", "X-Key": "your-key"},
    json={
        "task_name": "sync-like-conversion",
        "files": [{
            "source_format": "doc",
            "target_format": "docx",
            "object_key": "uploads/report.doc",
            "size_mb": 2.5
        }]
    }
)
task_id = response.json()["task_id"]

# 2. 轮询等待任务完成（同步效果）
def wait_for_task(task_id, timeout=300, poll_interval=2):
    """等待任务完成，返回结果"""
    result = AsyncResult(task_id, app=celery_app)
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if result.ready():
            if result.successful():
                return result.get()
            else:
                raise Exception(f"Task failed: {result.info}")
        time.sleep(poll_interval)
    
    raise TimeoutError(f"Task {task_id} timeout after {timeout}s")

# 使用
try:
    task_result = wait_for_task(task_id, timeout=300)
    print("Conversion complete!")
    for file_result in task_result['results']:
        print(f"✓ {file_result['object_key']}")
except TimeoutError:
    print("Task timeout, check Celery Worker status")
except Exception as e:
    print(f"Error: {e}")
```

**使用 Webhook 实现异步通知：**

```python
# 服务端实现 webhook 接收端点
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/conversion-complete")
async def receive_conversion_result(request: Request):
    payload = await request.json()
    task_id = payload["task_id"]
    results = payload["results"]
    
    # 处理转换结果
    for result in results:
        if result["status"] == "success":
            object_key = result["object_key"]
            # 下载文件或执行后续处理
            print(f"File ready: {object_key}")
    
    return {"status": "received"}

# 客户端提交任务时指定 callback_url
requests.post(
    "http://localhost:8000/api/v1/convert",
    headers={"X-Appid": "appid", "X-Key": "key"},
    json={
        "task_name": "webhook-example",
        "callback_url": "https://your-service.com/webhook/conversion-complete",
        "files": [...]
    }
)
```

---

### 2. GET /api/v1/formats - 查询支持格式

返回当前运行时已注册的所有格式转换能力。

**请求头：**
```
X-Appid: your-app-id
X-Key: your-app-key
```

**响应示例：**
```json
{
  "formats": [
        {"source": "doc", "target": "docx", "plugin": "doc-to-docx"},
        {"source": "doc", "target": "pdf", "plugin": "doc-to-pdf"},
        {"source": "docx", "target": "pdf", "plugin": "docx-to-pdf"},
        {"source": "ppt", "target": "pdf", "plugin": "ppt-to-pdf"},
        {"source": "pptx", "target": "pdf", "plugin": "pptx-to-pdf"},
        {"source": "html", "target": "pdf", "plugin": "html-to-pdf"},
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
        {"source": "mpeg", "target": "mp4", "plugin": "mpeg-to-mp4"},
        {"source": "flv", "target": "mp4", "plugin": "flv-to-mp4"},
        {"source": "ts", "target": "mp4", "plugin": "ts-to-mp4"},
        {"source": "m4v", "target": "mp4", "plugin": "m4v-to-mp4"},
        {"source": "3gp", "target": "mp4", "plugin": "3gp-to-mp4"}
  ]
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|-----|------|------|
| `formats` | array | 支持的格式转换列表 |
| `formats[].source` | string | 源格式 |
| `formats[].target` | string | 目标格式 |
| `formats[].plugin` | string | 插件标识符 |

---

**内联富文本/小文件示例（HTML → PDF，经 base64 传输）**

```json
{
    "task_name": "html-to-pdf-inline",
    "priority": "normal",
    "files": [
        {
            "base64_data": "PGgxPkhlbGxvPC9oMT4=",
            "source_format": "html",
            "target_format": "pdf",
            "filename": "inline.html",
            "size_mb": 0.001
        }
    ]
}
```

### 3. GET /api/v1/monitor/health - 健康检查

返回服务运行状态和关键依赖的连通性信息。

**请求头：**
```
X-Appid: your-app-id
X-Key: your-app-key
```

**响应示例：**
```json
{
  "status": "ok",
  "timestamp": "2025-12-04T08:15:30.123456Z",
  "dependencies": {
    "redis": "connected",
    "minio": "connected",
    "celery_workers": "2 active"
  }
}
```

**响应字段：**

| 字段 | 类型 | 说明 |
|-----|------|------|
| `status` | string | 服务状态：`ok`、`degraded`、`down` |
| `timestamp` | string | 检查时间戳（ISO 8601） |
| `dependencies` | object | 各依赖服务的状态信息 |

---

### 4. GET /healthz - 存活探针

简单的存活检测接口，用于容器编排（Kubernetes）的 liveness probe。

**响应示例：**
```json
{
  "status": "ok"
}
```

---

### 5. Prometheus 指标端点

系统在两个端口暴露 Prometheus 格式的监控指标：

- **API 进程指标**：`http://<host>:9091/metrics`
- **Worker 进程指标**：`http://<host>:9092/metrics`

**关键指标：**

| 指标名称 | 类型 | 标签 | 说明 |
|---------|------|------|------|
| `conversion_tasks_accepted_total` | Counter | `priority` | API 接收的任务总数 |
| `conversion_tasks_completed_total` | Counter | `status` | Worker 完成的任务数（成功/失败） |
| `conversion_queue_depth` | Gauge | - | 当前队列中待处理任务数 |
| `conversion_active_celery_workers` | Gauge | - | 活跃的 Celery Worker 数量 |

**示例输出片段：**
```
# HELP conversion_tasks_accepted_total Total conversion tasks accepted
# TYPE conversion_tasks_accepted_total counter
conversion_tasks_accepted_total{priority="high"} 127
conversion_tasks_accepted_total{priority="normal"} 854
conversion_tasks_accepted_total{priority="low"} 43

# HELP conversion_queue_depth Current conversion queue depth
# TYPE conversion_queue_depth gauge
conversion_queue_depth 12
```

---

### 6. Celery Flower 监控界面

访问 `http://<host>:5555` 可打开 Flower Web UI，实时查看：
- 任务执行历史与状态
- Worker 节点列表与负载
- 队列深度与延迟分布
- 任务重试与失败详情

默认端口 `5555` 可通过环境变量 `FLOWER_PORT` 自定义。

---

### 7. Celery 任务详细说明

系统注册的 Celery 任务及其参数说明：

#### 任务名称：`conversion.handle_batch`

批量文档转换任务，由 API 接口提交后异步执行。

**任务路径：** `rag_converter.celery_app:handle_conversion_task`

**参数结构：**

```python
{
    "task_id": str,              # 任务唯一标识符
    "files": [                   # 待转换文件列表
        {
            "source_format": str,      # 源格式，如 "doc"、"svg"、"wav"
            "target_format": str,      # 目标格式，如 "docx"、"png"、"mp3"
            "input_url": str | None,   # 文件下载 URL（可选）
            "object_key": str | None,  # MinIO 对象键名（可选）
            "size_mb": float           # 文件大小（MB）
        }
    ],
    "priority": str,             # 优先级：low/normal/high
    "callback_url": str | None,  # 完成后回调 URL（可选）
    "requested_by": str | None   # 请求来源标识（可选）
}
```

**返回结构：**

```python
{
    "task_id": str,              # 任务标识符
    "results": [                 # 每个文件的转换结果
        {
            "source": str,             # 源格式
            "target": str,             # 目标格式
            "status": str,             # "success" 或 "failed"
            "object_key": str | None,  # 转换后的存储路径
            "output_path": str | None, # 本地临时文件路径
            "metadata": dict,          # 转换元数据
            "reason": str | None       # 失败原因（失败时）
        }
    ]
}
```

**示例报文：**

请求（API 已完成校验后写入队列的 payload）：
```json
{
    "task_id": "f8c6a2fd-9d76-4bf0-9f2f-5e9f6a6e2c11",
    "priority": "normal",
    "callback_url": null,
    "files": [
        {
            "source_format": "docx",
            "target_format": "pdf",
            "input_url": "https://example.com/report.docx",
            "object_key": null,
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

返回（成功 + 失败混合示例）：
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

**直接调用示例：**

```python
from rag_converter.celery_app import handle_conversion_task

# 方式1：通过 delay() 异步调用
task = handle_conversion_task.delay({
    "task_id": "custom-task-id",
    "files": [{
        "source_format": "doc",
        "target_format": "docx",
        "object_key": "uploads/report.doc",
        "size_mb": 2.5
    }],
    "priority": "high"
})
print(f"Task ID: {task.id}")

# 方式2：通过 apply_async() 指定队列和参数
task = handle_conversion_task.apply_async(
    args=[{
        "task_id": "priority-task",
        "files": [...],
        "priority": "high"
    }],
    queue="conversion",
    priority=9
)

# 获取任务结果
from celery.result import AsyncResult
result = AsyncResult(task.id)
if result.ready():
    output = result.get()
    print(output)
```

**任务配置：**

- **队列名称：** `conversion`（默认，可在 `config/settings.yaml` 修改）
- **超时时间：** 300 秒（5 分钟，可配置 `task_time_limit_sec`）
- **重试策略：** 不自动重试（失败即标记为 failed）
- **结果后端：** Redis（存储在 `result_backend` 配置的地址）

**任务执行流程：**

1. API 接收请求，验证参数和格式支持
2. 生成 `task_id`，通过 `delay()` 提交任务到 Redis 队列
3. Celery Worker 从队列获取任务
4. 对每个文件：
   - 从 MinIO/URL 下载输入文件
   - 调用对应插件执行转换
   - 上传转换结果到 MinIO
   - 记录转换状态和元数据
5. 所有文件处理完成后返回结果
6. 如果配置了 `callback_url`，发送 POST 回调

**监控与调试：**

```bash
# 查看队列中的任务
celery -A rag_converter.celery_app:celery_app inspect active

# 查看注册的任务
celery -A rag_converter.celery_app:celery_app inspect registered

# 查看 Worker 状态
celery -A rag_converter.celery_app:celery_app inspect stats

# 清空队列(危险操作)
celery -A rag_converter.celery_app:celery_app purge
```

---

## 跨容器调用示例

### 场景：Pipeline 容器 A 调用服务引擎容器 B

在微服务架构中，通常 Pipeline 处理流程运行在独立容器 A，而文档转换引擎部署在容器 B。以下示例展示如何通过 Docker 网络实现跨容器调用。

#### 架构图

```
┌─────────────────────────┐      HTTP API      ┌──────────────────────────┐
│  Pipeline Container A   │ ──────────────────> │  Converter Container B   │
│                         │                     │                          │
│  - 数据预处理           │                     │  - FastAPI (port 8000)   │
│  - 任务编排             │                     │  - Celery Worker         │
│  - 结果聚合             │                     │  - Redis                 │
│                         │ <────────────────── │  - MinIO                 │
└─────────────────────────┘   Webhook 回调     └──────────────────────────┘
       │                                                    │
       │                                                    │
       └────────────────> 共享 Docker 网络 <───────────────┘
```

---

### 方式一：Docker Compose 网络共享

#### 1. 服务引擎 docker-compose.yml (Container B)

```yaml
# 文件位置：/path/to/converter/docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    networks:
      - converter-network

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    networks:
      - converter-network

  converter-api:
    image: rag-converter:latest
    container_name: converter-engine
    ports:
      - "8000:8000"
      - "9091:9091"
    environment:
      RAG_REDIS_URL: redis://redis:6379/0
      RAG_MINIO_ENDPOINT: http://minio:9000
    networks:
      - converter-network
    depends_on:
      - redis
      - minio

  converter-worker:
    image: rag-converter:latest
    command: celery -A rag_converter.celery_app:celery_app worker -l INFO
    environment:
      RAG_REDIS_URL: redis://redis:6379/0
      RAG_MINIO_ENDPOINT: http://minio:9000
    networks:
      - converter-network
    depends_on:
      - redis
      - minio

networks:
  converter-network:
    name: converter-network
    driver: bridge
```

#### 2. Pipeline docker-compose.yml (Container A)

```yaml
# 文件位置：/path/to/pipeline/docker-compose.yml
version: '3.8'

services:
  pipeline-service:
    image: my-pipeline:latest
    container_name: pipeline-processor
    ports:
      - "9000:9000"
    environment:
      CONVERTER_API_URL: http://converter-engine:8000
      CONVERTER_APPID: ${CONVERTER_APPID}
      CONVERTER_KEY: ${CONVERTER_KEY}
      CALLBACK_URL: http://pipeline-processor:9000/webhook/conversion
    networks:
      - converter-network  # 加入转换引擎的网络
    depends_on:
      - postgres
      - rabbitmq

  postgres:
    image: postgres:15
    networks:
      - converter-network

  rabbitmq:
    image: rabbitmq:3-management
    networks:
      - converter-network

networks:
  converter-network:
    external: true  # 使用已存在的转换引擎网络
```

#### 3. Pipeline 调用代码 (Celery 编排模式)

**Pipeline 服务项目结构：**

```
/path/to/pipeline/                   # Pipeline 项目根目录
├── pipeline_service/                # Python 包目录
│   ├── __init__.py                  # 包初始化（导出关键组件）
│   ├── celery_config.py             # Celery 应用配置
│   ├── converter_client.py          # 转换引擎客户端
│   ├── tasks.py                     # Pipeline 自定义任务
│   ├── main.py                      # FastAPI 应用入口
│   └── webhook_handler.py           # Webhook 回调处理（可选）
├── requirements.txt                 # Python 依赖
├── docker-compose.yml               # Docker Compose 配置
├── Dockerfile                       # 容器镜像构建文件
└── .env                             # 环境变量配置
```

**关键文件说明：**

```python
# 文件：pipeline_service/__init__.py
"""Pipeline Service Package"""

# 导出主要组件，方便外部导入
from .celery_config import pipeline_celery
from .converter_client import CeleryConverterClient
from .tasks import quality_check_task, post_process_task, aggregate_results_task

__all__ = [
    'pipeline_celery',
    'CeleryConverterClient',
    'quality_check_task',
    'post_process_task',
    'aggregate_results_task',
]
```

```txt
# 文件：requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
celery>=5.3.0
redis>=5.0.0
minio>=7.2.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
requests>=2.31.0
```

**方式A：直接调用转换引擎的 Celery 任务**

```python
# 文件：pipeline_service/celery_config.py
from celery import Celery
import os

# 配置 Pipeline 的 Celery 应用，连接到转换引擎的 Redis
pipeline_celery = Celery(
    'pipeline_service',
    broker='redis://redis:6379/0',      # 共享 Redis Broker
    backend='redis://redis:6379/1'      # Pipeline 专用 Result Backend
)

pipeline_celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
```

```python
# 文件：pipeline_service/converter_client.py
import os
import uuid
from typing import List, Dict
from celery import chain, group, chord
from celery.result import AsyncResult

# 导入同目录下的 celery_config 模块
# 如果作为包运行：from pipeline_service.celery_config import pipeline_celery
# 如果直接运行：from celery_config import pipeline_celery
try:
    from .celery_config import pipeline_celery  # 包模式
except ImportError:
    from celery_config import pipeline_celery   # 直接运行模式

class CeleryConverterClient:
    """通过 Celery 编排直接调用转换引擎任务，构造与 API 校验一致的 payload"""
    
    def __init__(self):
        # 引用转换引擎容器中注册的任务
        self.conversion_task = pipeline_celery.signature(
            'conversion.handle_batch',  # 转换引擎注册的任务名
            app=pipeline_celery
        )

    def _build_payload(
        self,
        files: List[Dict],
        *,
        priority: str = "normal",
        callback_url: str | None = None,
        storage: Dict | None = None,
        requested_by: str = "pipeline-service"
    ) -> Dict:
        return {
            "task_id": str(uuid.uuid4()),
            "files": files,
            "priority": priority,
            "callback_url": callback_url,
            "storage": storage,
            "requested_by": requested_by,
        }
    
    def submit_conversion_chain(
        self,
        files: List[Dict],
        priority: str = "normal",
        *,
        callback_url: str | None = None,
        storage: Dict | None = None,
    ) -> str:
        """使用 Celery Chain 串行编排：转换 -> 质量检查 -> 后处理"""

        conversion_payload = self._build_payload(
            files,
            priority=priority,
            callback_url=callback_url,
            storage=storage,
        )
        
        workflow = chain(
            self.conversion_task.clone(args=[conversion_payload]),
            pipeline_celery.signature('pipeline.quality_check'),
            pipeline_celery.signature('pipeline.post_process')
        )
        
        result = workflow.apply_async(priority=self._priority_to_int(priority))
        return result.id
    
    def submit_conversion_group(
        self,
        file_groups: List[List[Dict]],
        priority: str = "normal",
        *,
        callback_url: str | None = None,
        storage: Dict | None = None,
    ) -> List[str]:
        """使用 Celery Group 并行编排多个转换任务"""

        tasks = []
        for files in file_groups:
            payload = self._build_payload(
                files,
                priority=priority,
                callback_url=callback_url,
                storage=storage,
            )
            tasks.append(self.conversion_task.clone(args=[payload]))
        
        job = group(tasks)
        result = job.apply_async(priority=self._priority_to_int(priority))
        return [r.id for r in result.results]
    
    def submit_conversion_chord(
        self,
        file_batches: List[List[Dict]],
        priority: str = "high",
        *,
        callback_url: str | None = None,
        storage: Dict | None = None,
    ) -> str:
        """使用 Celery Chord：并行转换 + 聚合处理"""

        parallel_tasks = []
        for files in file_batches:
            payload = self._build_payload(
                files,
                priority=priority,
                callback_url=callback_url,
                storage=storage,
            )
            parallel_tasks.append(self.conversion_task.clone(args=[payload]))
        
        workflow = chord(
            group(parallel_tasks),
            pipeline_celery.signature('pipeline.aggregate_results')
        )
        result = workflow.apply_async(priority=self._priority_to_int(priority))
        return result.id
    
    def get_result(self, task_id: str, timeout: int = 300) -> Dict:
        """获取任务结果（阻塞等待）"""
        result = AsyncResult(task_id, app=pipeline_celery)
        return result.get(timeout=timeout)
    
    def check_status(self, task_id: str) -> Dict:
        """检查任务状态（非阻塞）"""
        result = AsyncResult(task_id, app=pipeline_celery)
        return {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None
        }
    
    def _priority_to_int(self, priority: str) -> int:
        """转换优先级字符串为数值"""
        priority_map = {"low": 3, "normal": 5, "high": 9}
        return priority_map.get(priority, 5)


# 使用示例1：Chain 串行编排（含 page_limit/duration/storage/callback）
def example_chain_workflow():
    client = CeleryConverterClient()
    
    files = [
        {
            "source_format": "doc",
            "target_format": "docx",
            "object_key": "uploads/report.doc",
            "filename": "report.doc",
            "size_mb": 2.5,
            "page_limit": 3
        },
        {
            "source_format": "wav",
            "target_format": "mp3",
            "object_key": "uploads/interview.wav",
            "size_mb": 45.0,
            "duration_seconds": 20
        }
    ]
    
    storage_override = {
        "endpoint": "http://minio:9000",
        "access_key": "override-ak",
        "secret_key": "override-sk",
        "bucket": "custom-bucket"
    }
    
    task_id = client.submit_conversion_chain(
        files,
        priority="high",
        callback_url="http://pipeline-processor:9000/webhook/conversion",
        storage=storage_override,
    )
    print(f"Chain workflow submitted: {task_id}")
    result = client.get_result(task_id, timeout=600)
    print(f"Workflow completed: {result}")


# 使用示例2：Group 并行编排（多批次 + 元数据）
def example_group_workflow():
    client = CeleryConverterClient()
    file_groups = [
        [{"source_format": "doc", "target_format": "docx", "object_key": "batch1/file1.doc", "filename": "file1.doc", "size_mb": 2.0, "page_limit": 2}],
        [{"source_format": "svg", "target_format": "png", "input_url": "https://example.com/file2.svg", "size_mb": 1.5}],
        [{"source_format": "wav", "target_format": "mp3", "object_key": "batch3/audio.wav", "size_mb": 50.0, "duration_seconds": 15}]
    ]
    task_ids = client.submit_conversion_group(
        file_groups,
        priority="normal",
        callback_url="http://pipeline-processor:9000/webhook/conversion"
    )
    print(f"Group tasks submitted: {task_ids}")
    for task_id in task_ids:
        status = client.check_status(task_id)
        print(f"Task {task_id}: {status}")


# 使用示例3：Chord 并行+聚合（混合 page_limit/duration）
def example_chord_workflow():
    client = CeleryConverterClient()
    file_batches = [
        [{"source_format": "doc", "target_format": "docx", "object_key": "project/doc1.doc", "size_mb": 2.0, "page_limit": 2}],
        [{"source_format": "pptx", "target_format": "pdf", "object_key": "project/slides.pptx", "size_mb": 10.0, "page_limit": 5}],
        [{"source_format": "gif", "target_format": "mp4", "object_key": "project/anim.gif", "size_mb": 5.0, "duration_seconds": 5}]
    ]
    chord_id = client.submit_conversion_chord(
        file_batches,
        priority="high",
        storage={"bucket": "converted-overrides"}
    )
    print(f"Chord workflow submitted: {chord_id}")
    aggregated_result = client.get_result(chord_id, timeout=600)
    print(f"Aggregated result: {aggregated_result}")
```

**方式B：定义 Pipeline 自己的 Celery 任务**

```python
# 文件：pipeline_service/tasks.py
try:
    from .celery_config import pipeline_celery
except ImportError:
    from celery_config import pipeline_celery

from celery import chain
from typing import Dict, List

@pipeline_celery.task(name='pipeline.quality_check')
def quality_check_task(conversion_results: Dict) -> Dict:
    """
    质量检查任务（Chain 中的第二步）
    
    Args:
        conversion_results: 上一步转换任务的输出
    """
    print(f"Quality checking results: {conversion_results['task_id']}")
    
    checked_results = []
    for result in conversion_results.get('results', []):
        if result['status'] == 'success':
            # 执行质量检查逻辑
            quality_score = _check_file_quality(result['object_key'])
            result['quality_score'] = quality_score
            result['quality_passed'] = quality_score > 0.8
        checked_results.append(result)
    
    return {
        "task_id": conversion_results['task_id'],
        "results": checked_results,
        "stage": "quality_checked"
    }

@pipeline_celery.task(name='pipeline.post_process')
def post_process_task(checked_results: Dict) -> Dict:
    """
    后处理任务（Chain 中的第三步）
    
    Args:
        checked_results: 上一步质量检查的输出
    """
    print(f"Post processing results: {checked_results['task_id']}")
    
    processed_results = []
    for result in checked_results.get('results', []):
        if result.get('quality_passed', True):
            # 执行后处理：文本提取、向量化等
            extracted_text = _extract_text(result['object_key'])
            vectors = _vectorize_text(extracted_text)
            
            result['text_extracted'] = True
            result['vector_count'] = len(vectors)
        processed_results.append(result)
    
    return {
        "task_id": checked_results['task_id'],
        "results": processed_results,
        "stage": "completed"
    }

@pipeline_celery.task(name='pipeline.aggregate_results')
def aggregate_results_task(batch_results: List[Dict]) -> Dict:
    """
    聚合任务（Chord 的回调）
    
    Args:
        batch_results: 所有并行任务的结果列表
    """
    print(f"Aggregating {len(batch_results)} batch results")
    
    total_files = 0
    success_count = 0
    failed_count = 0
    
    for batch in batch_results:
        for result in batch.get('results', []):
            total_files += 1
            if result['status'] == 'success':
                success_count += 1
            else:
                failed_count += 1
    
    # 生成汇总报告
    summary = {
        "total_batches": len(batch_results),
        "total_files": total_files,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": success_count / total_files if total_files > 0 else 0
    }
    
    # 可以触发通知、更新数据库等
    _send_completion_notification(summary)
    
    return summary

def _check_file_quality(object_key: str) -> float:
    """检查文件质量（示例）"""
    # 实现质量检查逻辑
    return 0.95

def _extract_text(object_key: str) -> str:
    """提取文本内容（示例）"""
    # 实现文本提取逻辑
    return "Extracted text content..."

def _vectorize_text(text: str) -> List[float]:
    """向量化文本（示例）"""
    # 实现向量化逻辑
    return [0.1, 0.2, 0.3]

def _send_completion_notification(summary: Dict):
    """发送完成通知（示例）"""
    print(f"Pipeline completed: {summary}")
```

#### 4. Webhook 回调接收端点

```python
# 文件：pipeline_service/webhook_handler.py
from fastapi import FastAPI, Request, BackgroundTasks
from typing import Dict

app = FastAPI()

# 存储任务状态（生产环境应使用 Redis/数据库）
task_results = {}

@app.post("/webhook/conversion")
async def receive_conversion_result(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    接收来自转换引擎容器的 webhook 回调
    """
    payload = await request.json()
    task_id = payload["task_id"]
    results = payload["results"]
    
    # 保存结果
    task_results[task_id] = payload
    
    # 异步处理后续流程
    background_tasks.add_task(process_converted_files, task_id, results)
    
    return {"status": "received", "task_id": task_id}

async def process_converted_files(task_id: str, results: list):
    """处理转换后的文件（异步）"""
    from minio import Minio
    
    # 连接到转换引擎的 MinIO（通过 Docker 网络）
    minio_client = Minio(
        "minio:9000",  # 使用 Docker 网络中的服务名
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )
    
    for result in results:
        if result["status"] == "success":
            object_key = result["object_key"]
            
            # 下载转换后的文件
            local_path = f"/tmp/pipeline/{task_id}/{object_key.split('/')[-1]}"
            minio_client.fget_object("qadata", object_key, local_path)
            
            # 执行 Pipeline 后续处理
            print(f"Processing converted file: {local_path}")
            # 例如：文本提取、向量化、索引构建等
            
    print(f"Task {task_id} processing completed")
```

---

### 方式二：独立网络 + 端口映射

如果无法共享 Docker 网络，可通过宿主机端口映射实现跨容器调用。

#### 1. 服务引擎容器启动（暴露端口）

```bash
# Container B: 转换引擎
docker-compose -f /path/to/converter/docker-compose.yml up -d
# API 端口映射到宿主机 8000
```

#### 2. Pipeline 调用配置

```python
# 通过宿主机 IP + 端口访问
class ConverterClient:
    def __init__(self):
        # 使用宿主机 IP（或 Docker 桥接网络网关）
        self.api_url = os.getenv(
            "CONVERTER_API_URL",
            "http://172.17.0.1:8000"  # Docker 默认网关
        )
        # 或使用宿主机实际 IP
        # self.api_url = "http://192.168.1.100:8000"
```

---

### 方式三：Kubernetes 跨 Pod 调用

如果部署在 K8s 环境：

```yaml
# converter-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: converter-service
spec:
  selector:
    app: rag-converter
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
```

```python
# Pipeline Pod 中调用
class ConverterClient:
    def __init__(self):
        # 使用 K8s Service DNS 名称
        self.api_url = "http://converter-service.default.svc.cluster.local:8000"
```

---

### 配置要点

#### 环境变量配置（Pipeline 容器 - Celery 模式）

```bash
# .env 文件
# Celery Broker/Backend（共享转换引擎的 Redis）
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# MinIO 连接（共享对象存储）
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=qadata

# Pipeline 服务配置
PIPELINE_SERVICE_PORT=9000
LOG_LEVEL=INFO
```

**关键配置说明：**

| 配置项 | 说明 |
|-------|------|
| `CELERY_BROKER_URL` | **必须**与转换引擎容器使用相同的 Redis，确保任务能被转换引擎的 Worker 消费 |
| `CELERY_RESULT_BACKEND` | 可使用独立的 Redis DB，避免与转换引擎的结果混淆 |
| `MINIO_ENDPOINT` | 通过 Docker 网络访问转换引擎的 MinIO 服务 |

#### 网络调试命令

```bash
# 在 Pipeline 容器内测试网络连通性
docker exec -it pipeline-processor bash

# 测试 DNS 解析
nslookup converter-engine

# 测试 HTTP 连接
curl http://converter-engine:8000/healthz

# 测试认证
curl -H "X-Appid: your-appid" \
     -H "X-Key: your-key" \
     http://converter-engine:8000/api/v1/formats
```

---

### 完整示例：Pipeline 主流程（Celery 编排）

```python
# 文件：pipeline_service/main.py
try:
    from .converter_client import CeleryConverterClient
    from .celery_config import pipeline_celery
except ImportError:
    from converter_client import CeleryConverterClient
    from celery_config import pipeline_celery

from typing import List
import logging

logger = logging.getLogger(__name__)

class DocumentPipeline:
    """文档处理流水线（Celery 编排模式）"""
    
    def __init__(self):
        self.converter = CeleryConverterClient()
        
    def run_chain_workflow(self, document_paths: List[str]) -> str:
        """
        执行串行工作流（Chain）
        
        流程：预处理 -> 格式转换 -> 质量检查 -> 后处理 -> 索引
        """
        logger.info(f"Starting chain workflow for {len(document_paths)} documents")
        
        # 步骤1：预处理（去重、分类等）
        processed_docs = self._preprocess(document_paths)
        
        # 步骤2：构建转换文件列表
        conversion_files = []
        for doc in processed_docs:
            conversion_files.append({
                "source_format": doc["format"],
                "target_format": self._get_target_format(doc["format"]),
                "object_key": doc["storage_key"],
                "size_mb": doc["size_mb"]
            })
        
        # 步骤3：提交 Celery Chain 工作流
        # 转换 -> 质量检查 -> 后处理（自动串行执行）
        task_id = self.converter.submit_conversion_chain(
            files=conversion_files,
            priority="high"
        )
        
        logger.info(f"Chain workflow submitted: {task_id}")
        return task_id
    
    def run_parallel_workflow(self, document_batches: List[List[str]]) -> List[str]:
        """
        执行并行工作流（Group）
        
        场景：多个项目/批次同时处理
        """
        logger.info(f"Starting parallel workflow for {len(document_batches)} batches")
        
        file_groups = []
        for batch in document_batches:
            processed_docs = self._preprocess(batch)
            batch_files = [
                {
                    "source_format": doc["format"],
                    "target_format": self._get_target_format(doc["format"]),
                    "object_key": doc["storage_key"],
                    "size_mb": doc["size_mb"]
                }
                for doc in processed_docs
            ]
            file_groups.append(batch_files)
        
        # 提交 Celery Group 并行任务
        task_ids = self.converter.submit_conversion_group(
            file_groups=file_groups,
            priority="normal"
        )
        
        logger.info(f"Parallel workflow submitted: {task_ids}")
        return task_ids
    
    def run_chord_workflow(self, document_batches: List[List[str]]) -> str:
        """
        执行并行+聚合工作流（Chord）
        
        流程：多批次并行转换 -> 等待全部完成 -> 统一聚合处理
        """
        logger.info(f"Starting chord workflow for {len(document_batches)} batches")
        
        file_batches = []
        for batch in document_batches:
            processed_docs = self._preprocess(batch)
            batch_files = [
                {
                    "source_format": doc["format"],
                    "target_format": self._get_target_format(doc["format"]),
                    "object_key": doc["storage_key"],
                    "size_mb": doc["size_mb"]
                }
                for doc in processed_docs
            ]
            file_batches.append(batch_files)
        
        # 提交 Celery Chord：并行 + 聚合
        chord_id = self.converter.submit_conversion_chord(
            file_batches=file_batches,
            priority="high"
        )
        
        logger.info(f"Chord workflow submitted: {chord_id}")
        return chord_id
    
    def get_workflow_result(self, task_id: str, timeout: int = 600):
        """获取工作流结果（阻塞等待）"""
        return self.converter.get_result(task_id, timeout=timeout)
    
    def check_workflow_status(self, task_id: str):
        """检查工作流状态（非阻塞）"""
        return self.converter.check_status(task_id)
    
    def _preprocess(self, paths: List[str]) -> List[dict]:
        """预处理逻辑"""
        # 实现文档分类、去重、上传到 MinIO 等
        return [
            {
                "format": self._detect_format(p),
                "storage_key": f"uploads/{p}",
                "size_mb": 2.0
            }
            for p in paths
        ]
    
    def _detect_format(self, path: str) -> str:
        """检测文件格式"""
        ext = path.split('.')[-1].lower()
        return ext
    
    def _get_target_format(self, source_format: str) -> str:
        """确定目标格式"""
        format_map = {
            "doc": "docx",
            "svg": "png",
            "wav": "mp3",
            "avi": "mp4",
            "gif": "mp4",
            "webp": "png"
        }
        return format_map.get(source_format, source_format)


# FastAPI 应用入口
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI(title="Document Pipeline Service (Celery Orchestration)")
pipeline = DocumentPipeline()

class ChainRequest(BaseModel):
    document_paths: List[str]

class ParallelRequest(BaseModel):
    document_batches: List[List[str]]

class ChordRequest(BaseModel):
    document_batches: List[List[str]]

@app.post("/pipeline/chain")
async def submit_chain_workflow(request: ChainRequest):
    """
    提交串行工作流
    
    示例请求：
    {
        "document_paths": ["report.doc", "diagram.svg", "audio.wav"]
    }
    """
    task_id = pipeline.run_chain_workflow(request.document_paths)
    return {
        "workflow_type": "chain",
        "task_id": task_id,
        "status": "submitted"
    }

@app.post("/pipeline/parallel")
async def submit_parallel_workflow(request: ParallelRequest):
    """
    提交并行工作流
    
    示例请求：
    {
        "document_batches": [
            ["project1/doc1.doc", "project1/img1.svg"],
            ["project2/doc2.doc", "project2/audio.wav"],
            ["project3/video.avi"]
        ]
    }
    """
    task_ids = pipeline.run_parallel_workflow(request.document_batches)
    return {
        "workflow_type": "parallel",
        "task_ids": task_ids,
        "batch_count": len(task_ids),
        "status": "submitted"
    }

@app.post("/pipeline/chord")
async def submit_chord_workflow(request: ChordRequest):
    """
    提交并行+聚合工作流
    
    示例请求：
    {
        "document_batches": [
            ["batch1/doc1.doc"],
            ["batch2/doc2.doc"],
            ["batch3/img.svg"]
        ]
    }
    """
    chord_id = pipeline.run_chord_workflow(request.document_batches)
    return {
        "workflow_type": "chord",
        "chord_id": chord_id,
        "status": "submitted"
    }

@app.get("/pipeline/status/{task_id}")
async def get_pipeline_status(task_id: str):
    """查询工作流状态（非阻塞）"""
    status = pipeline.check_workflow_status(task_id)
    return status

@app.get("/pipeline/result/{task_id}")
async def get_pipeline_result(task_id: str, timeout: int = 600):
    """获取工作流结果（阻塞等待）"""
    try:
        result = pipeline.get_workflow_result(task_id, timeout=timeout)
        return {
            "task_id": task_id,
            "status": "completed",
            "result": result
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "status": "error",
### Pipeline 服务部署准备

**1. 创建 Pipeline 项目目录结构：**

```bash
# 创建项目目录
mkdir -p /path/to/pipeline/pipeline_service
cd /path/to/pipeline

# 创建必要文件
touch pipeline_service/__init__.py
touch pipeline_service/celery_config.py
touch pipeline_service/converter_client.py
touch pipeline_service/tasks.py
touch pipeline_service/main.py
touch requirements.txt
touch docker-compose.yml
touch Dockerfile
touch .env
```

**2. 编写 Dockerfile：**

```dockerfile
# 文件：Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY pipeline_service/ ./pipeline_service/

# 暴露端口
EXPOSE 9000

# 启动命令（通过 docker-compose 覆盖）
CMD ["uvicorn", "pipeline_service.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

**3. 配置环境变量：**

```bash
# 文件：.env
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=qadata
PIPELINE_SERVICE_PORT=9000
LOG_LEVEL=INFO
```

**4. 编写 docker-compose.yml：**

```yaml
# 文件：docker-compose.yml
version: '3.8'

services:
  pipeline-api:
    build: .
    container_name: pipeline-processor
    ports:
      - "9000:9000"
    environment:
      CELERY_BROKER_URL: ${CELERY_BROKER_URL}
      CELERY_RESULT_BACKEND: ${CELERY_RESULT_BACKEND}
      MINIO_ENDPOINT: ${MINIO_ENDPOINT}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
    networks:
      - converter-network
    command: uvicorn pipeline_service.main:app --host 0.0.0.0 --port 9000
    depends_on:
      - pipeline-worker

  pipeline-worker:
    build: .
    container_name: pipeline-worker
    environment:
      CELERY_BROKER_URL: ${CELERY_BROKER_URL}
      CELERY_RESULT_BACKEND: ${CELERY_RESULT_BACKEND}
      MINIO_ENDPOINT: ${MINIO_ENDPOINT}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
    networks:
      - converter-network
    command: celery -A pipeline_service.celery_config:pipeline_celery worker -l INFO -Q conversion,pipeline
    restart: unless-stopped

  pipeline-flower:
    build: .
    container_name: pipeline-flower
    ports:
      - "5556:5556"
    environment:
      CELERY_BROKER_URL: ${CELERY_BROKER_URL}
      CELERY_RESULT_BACKEND: ${CELERY_RESULT_BACKEND}
    networks:
      - converter-network
    command: celery -A pipeline_service.celery_config:pipeline_celery flower --port=5556
    restart: unless-stopped

networks:
  converter-network:
    external: true  # 使用转换引擎的网络
```

---

### 部署启动顺序（Celery 编排模式）

```bash
# 1. 启动转换引擎容器（Container B）
cd /path/to/converter
docker-compose up -d

# 2. 验证转换引擎 Celery Worker 就绪
docker-compose logs -f converter-worker
# 应看到：[tasks] * conversion.handle_batch

# 3. 启动 Pipeline 容器（Container A）
cd /path/to/pipeline
docker-compose up -d

# 4. 启动 Pipeline 的 Celery Worker（如有自定义任务）
docker-compose exec pipeline-service celery -A pipeline_service.celery_config:pipeline_celery worker -l INFO

# 5. 验证 Celery 连接
docker exec pipeline-processor python -c "
from pipeline_service.celery_config import pipeline_celery
inspector = pipeline_celery.control.inspect()
print('Active workers:', inspector.active())
print('Registered tasks:', inspector.registered())
"

# 6. 提交测试任务（Chain 工作流）
curl -X POST http://localhost:9000/pipeline/chain \
  -H "Content-Type: application/json" \
  -d '{
    "document_paths": ["report.doc", "diagram.svg"]
  }'

# 7. 提交测试任务（Parallel 工作流）
curl -X POST http://localhost:9000/pipeline/parallel \
  -H "Content-Type: application/json" \
  -d '{
    "document_batches": [
      ["batch1/doc1.doc"],
      ["batch2/doc2.doc"],
      ["batch3/img.svg"]
    ]
  }'

# 8. 提交测试任务（Chord 工作流）
curl -X POST http://localhost:9000/pipeline/chord \
  -H "Content-Type: application/json" \
  -d '{
    "document_batches": [
      ["project/doc1.doc", "project/img1.svg"],
      ["project/doc2.doc"]
    ]
  }'

# 9. 查询任务状态
TASK_ID="<返回的task_id>"
curl http://localhost:9000/pipeline/status/$TASK_ID

# 10. 获取任务结果（阻塞等待）
curl http://localhost:9000/pipeline/result/$TASK_ID

# 11. 监控 Celery 任务（通过 Flower）
# 转换引擎 Flower: http://localhost:5555
# Pipeline Flower (如果启动): http://localhost:5556
```

---

### Celery 编排模式优势

相比 HTTP API 调用模式，Celery 编排具有以下优势：

| 特性 | HTTP API 模式 | Celery 编排模式 |
|-----|-------------|----------------|
| **性能** | 需要 HTTP 序列化/反序列化 | 直接通过 Redis 传递消息，性能更高 |
| **可靠性** | 依赖 API 服务可用性 | 基于消息队列，自动重试和容错 |
| **编排能力** | 需要自己实现工作流逻辑 | 原生支持 Chain/Group/Chord 等编排原语 |
| **资源利用** | 每次调用占用 HTTP 连接 | 异步消息传递，资源占用更少 |
| **监控** | 需要自己实现追踪 | Celery 内置任务追踪和 Flower 监控 |
| **回调** | 需要暴露 Webhook 端点 | 通过 Celery Chain 自动串联 |
| **复杂编排** | 实现复杂，容易出错 | 使用 Canvas 原语，代码简洁清晰 |

**使用建议：**

- **轻量调用**：单次转换任务，使用 HTTP API 更简单
- **复杂工作流**：多步骤、并行、聚合场景，使用 Celery 编排
- **高并发**：大批量任务处理，Celery 模式性能更优
- **跨语言**：非 Python 客户端，使用 HTTP API
- **同技术栈**：Pipeline 和转换引擎都是 Python + Celery，优先 Celery 编排. 启动 Pipeline 容器（Container A）
cd /path/to/pipeline
docker-compose up -d

# 4. 验证跨容器连通性
docker exec pipeline-processor curl http://converter-engine:8000/healthz

# 5. 提交测试任务
curl -X POST http://localhost:9000/pipeline/submit \
  -H "Content-Type: application/json" \
  -d '{"document_paths": ["doc1.doc", "doc2.doc"]}'
```

---

### 错误码说明

所有 API 错误返回统一结构，包含 `error_code` 字段。常见错误码：

| 错误码 | HTTP 状态 | 说明 |
|-------|----------|------|
| `ERR_FILE_TOO_LARGE` | 400 | 单文件超出大小限制 |
| `ERR_BATCH_LIMIT_EXCEEDED` | 400 | 批量任务超出文件数或总大小限制 |
| `ERR_FORMAT_UNSUPPORTED` | 400 | 不支持的格式转换 |
| `ERR_AUTH_FAILED` | 401 | 认证失败（appid/key 无效） |
| `ERR_TASK_FAILED` | 500 | 任务调度失败 |

完整错误码列表和多语言描述详见 `docs/error_codes.md`。

## 配置与扩展

- 所有参数可通过 `config/settings.yaml`、环境变量（前缀 `RAG_`）或命令行覆盖。详细字段说明见 `docs/configuration.md`。
- 插件目录位于 `src/rag_converter/plugins`，继承 `ConversionPlugin` 并在 `REGISTRY` 注册即可热扩展格式支持。当前内置能力：
    - 文档/图片：`doc→docx`（LibreOffice）、`svg→png`（Inkscape）、`webp→png`（FFmpeg）
    - 动画/视频：`gif→mp4`、`avi→mp4`、`mov→mp4`、`mkv→mp4`、`webm→mp4`、`mpeg→mp4`（均通过 FFmpeg）
    - 音频：`wav/flac/ogg/aac→mp3`（FFmpeg）
    - 插件注册与依赖：通过 `scripts/manage_plugins.sh` 维护模块及依赖，例如：

      ```bash
      ./scripts/manage_plugins.sh list
      ./scripts/manage_plugins.sh register custom_pkg.plugins.pdf_to_md
      ./scripts/manage_plugins.sh deps set custom_pkg.plugins.pdf_to_md pypdf2 pillow
      ./scripts/manage_plugins.sh deps install custom_pkg.plugins.pdf_to_md
      ./scripts/manage_plugins.sh unregister custom_pkg.plugins.legacy_doc
      ```
- Celery worker 通过 `rag_converter.celery_app:celery_app` 启动，可针对不同格式定制队列、超时与资源限制。`start_server.sh` 会同时拉起 Flower 以便可视化监控任务与队列。

更多开发/部署细节，请参考 `docs/api.md` 与 `docs/configuration.md`。
