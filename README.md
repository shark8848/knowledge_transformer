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
- MinIO 控制台：http://localhost:9001 (minioadmin/minioadmin)

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
5. **可观测性**：结构化日志、追踪 ID、Prometheus 指标以及健康/依赖监控端点。
6. **异步任务处理**：所有转换任务通过 Celery 异步执行，FastAPI 负责接收请求和返回 task_id，避免长时间阻塞连接。支持 webhook 回调、Result Backend 查询等多种结果获取方式。

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
  "callback_url": "https://your-service.com/webhook/conversion-complete",
  "files": [
    {
      "source_format": "doc",
      "target_format": "docx",
      "input_url": "https://storage.example.com/documents/report.doc",
      "object_key": "uploads/2025/report.doc",
      "size_mb": 2.5
    },
    {
      "source_format": "svg",
      "target_format": "png",
      "input_url": "https://storage.example.com/images/diagram.svg",
      "size_mb": 0.8
    },
    {
      "source_format": "wav",
      "target_format": "mp3",
      "object_key": "audio/interview.wav",
      "size_mb": 45.2
    }
  ]
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `task_name` | string | ✓ | 任务名称，便于追踪 |
| `priority` | string | ✗ | 优先级：`low`/`normal`/`high`，默认 `normal` |
| `callback_url` | string | ✗ | 转换完成后的 webhook 回调 URL |
| `files` | array | ✓ | 待转换文件列表 |
| `files[].source_format` | string | ✓ | 源格式，如 `doc`、`svg`、`wav` |
| `files[].target_format` | string | ✓ | 目标格式，如 `docx`、`png`、`mp3` |
| `files[].input_url` | string | ✗ | 文件下载 URL（与 `object_key` 二选一） |
| `files[].object_key` | string | ✗ | 对象存储键名（与 `input_url` 二选一） |
| `files[].size_mb` | number | ✓ | 文件大小（MB），用于预检验证 |

**响应示例（成功）：**
```json
{
  "status": "accepted",
  "task_id": "a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f",
  "message": "Task accepted and scheduled for conversion"
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

**响应字段：**

| 字段 | 类型 | 说明 |
|-----|------|------|
| `status` | string | `accepted`（已接受）或 `failure`（失败） |
| `task_id` | string | 任务唯一标识符，用于后续查询 |
| `message` | string | 描述信息 |
| `error_code` | string | 错误码（失败时），详见 `docs/error_codes.md` |
| `error_status` | number | HTTP 状态码（失败时） |

**获取转换后的文件：**

转换完成后，系统通过以下方式提供文件访问：

1. **对象存储（推荐方式）**
   - 转换后的文件自动上传到 MinIO/S3 对象存储
   - 存储路径格式：`converted/{task_id}/{filename}`
   - 示例：`converted/a3f7e9d2-4c5b-4e8a-9f2d-1a6b8c3e5d7f/report.docx`

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

**响应字段：**

| 字段 | 类型 | 说明 |
|-----|------|------|
| `formats` | array | 支持的格式转换列表 |
| `formats[].source` | string | 源格式 |
| `formats[].target` | string | 目标格式 |
| `formats[].plugin` | string | 插件标识符 |

---

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
