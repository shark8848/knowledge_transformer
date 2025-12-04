# RAG知识库文档规范化转换服务引擎 Copilot Agent 提示词

## 背景与目标

### 背景
随着知识库技术的蓬勃发展，企业和项目需要收集、整理和处理来自多渠道、格式多样的文档、表格和多媒体内容。这些内容在规范化、结构化后，便于知识检索、深度理解和自动化利用。传统的文档转换方案难以应对高并发、批量、弹性和企业级的需求。
本项目旨在打造一个现代化、企业级的RAG（检索增强生成）知识库文档规范化转换服务引擎，实现高并发、自动化、弹性、标准化、可维护和安全的文档批量处理与流水线集成。

### 目标
- 构建高并发、多格式、弹性扩展的文档/多媒体规范化转换服务，覆盖常见Office和媒体格式。
- 支持REST API和Celery任务两种供给方式，方便集成于流水线/异步处理场景。
- 参数全配置化：包括功能、资源、输出、监控、限制、接口权限等，支持配置文件、环境变量、命令行注入，且可热加载或平滑滚动。
- 每种文件格式支持单独文件大小上限（全局+按格式）、最大批量数与体积安全限制，保证系统稳定和安全。
- API访问具安全设计，默认需要appid和key授权，可配置为免认证。支持通过命令行生成和移除app授权信息。
- 插件化和高可扩展架构，适应动态格式扩展、分布式部署、多人协作。
- 日志全链路结构化，自动切割与清理策略可配置。内置监控API、依赖服务连通性健康检测。
- 完善的错误码与异常提示，便于快速定位和集成。

---

## 系统设计原则

### 1. 参数全配置化
- 所有功能、行为、转换格式、输入输出、资源限制、日志、监控、队列、存储、任务绑定、依赖服务、API身份认证等参数必须全部配置化，覆盖配置文件、环境变量和命令行参数。
- 全部限制（如文件大小、任务数量、认证开关等）均可“全局默认+按格式/业务单独配置”，支持热加载重载。
- 提供示例配置文件、配置文档与命令行入口指令，便于维护和迁移。

### 2. 明确的资源与安全限制
- 每种文件格式可独立配置单文件大小最大值（per_format_max_size_mb），支持最大批量数量和总批量体积限制（max_files_per_task, max_total_upload_size_mb）。
- 超限拦截并按标准错误码规范返回。
- API 安全接入：默认每个API请求需携带正确的 appid 和 key。是否开启认证可配置，禁止时相关校验/日志自动屏蔽。
- 支持通过命令行工具生成和删除appid、key，便于授权管理和密钥安全。

### 3. 完整错误码体系
- 涉及认证失败、参数校验、格式支持、文件/任务超限、连接失败、第三方错误、系统异常等，错误码唯一、结构化、含多语言和详细说明，可配置并自动同步到接口文档与前后端。
- 所有异常流程，返回明确错误码和信息。

### 4. 插件化与可扩展架构
- 转换能力解耦为独立模块/插件，格式支持、处理逻辑动态扩展。
- Celery、API、监控等子模块解耦，便于单测、独立部署和升级。
- 支持多输入/输出，存储后端可扩展。

---

## 主要功能概要

### 1. 多格式支持
- 插件化/热加载的格式转换能力，常见如：
    - doc → docx
    - ppt → pptx
    - xls → xlsx
    - wps → docx
    - gif → mp4
    - svg → png
- 支持运行时查询和动态扩展。

### 2. 高并发与异步处理
- 支持配置化的并发与队列、Celery分布式和API双协议，批量上传自动校验各限制。

### 3. 多方式安全输入输出
- 输入：本地、对象存储（S3/MinIO…），参数和认证全部配置化。
- 输出：对象流或S3存储，目标和认证可完全配置。
- API均需带appid+key请求头或参数，后端核查，支持白名单或免认证场景配置。

### 4. Celery任务与Pipeline友好
- 各格式单独队列、并发、超时参数；API与任务通讯协议、参数结构一致。

### 5. 结构化日志与可观测监控
- 支持INFO/WARN/ERROR/DEBUG，全链路追踪ID，日志切割/清理参数化。
- 所有日志事件、异常、认证校验均详细记录。
- 监控API端点、Prometheus支持、全部指标项/端口可配置。

---

## API认证与授权指引

### 1. 接口访问安全设计
- 默认所有API接口 **必须** 携带 `appid` 和 `key`（可做请求头如`X-Appid`, `X-Key`或者url参数）。
- 是否要求认证及认证模式可通过配置参数 `api_auth.required` 控制，缺省为`true`（强认证）。

```yaml
api_auth:
  required: true           # 缺省开启，有重要数据建议一直开启
  app_secrets_path: "./secrets/appkeys.json"
```

- API请求范例：

```
POST /api/v1/convert
Headers: X-Appid: 123456   X-Key: abcdefg
```

### 2. appid和key管理
- 提供命令行工具用于生成和删除appid/key，自动写入配置和密钥文件，可脱机安全管理。

```shell
python manage_appkey.py generate  # 自动生成appid/key并存储
python manage_appkey.py delete <appid>
```

- 后端安全存储，密钥文件路径可通过`app_secrets_path`参数配置。

### 3. 认证失败时返回标准错误码

```yaml
error_codes:
  ERR_AUTH_MISSING:
    zh: "认证信息缺失"
    en: "Missing authentication information"
    status: 4010
  ERR_AUTH_INVALID:
    zh: "认证失败，appid或key错误"
    en: "Authentication failed: invalid appid or key"
    status: 4011
```

---

## 配置及错误码结构示例

### 核心配置片段

```yaml
file_limits:
  default_max_size_mb: 100
  per_format_max_size_mb:
    doc: 50
    ppt: 60
    gif: 30
    svg: 10
  max_total_upload_size_mb: 500
  max_files_per_task: 10

logging:
  level: "INFO"
  log_dir: "./logs"
  rotation: "size"
  max_log_file_size_mb: 100
  backup_count: 7
  retention_days: 30

monitoring:
  health_api: "/api/v1/monitor/health"
  traffic_api: "/api/v1/monitor/traffic"
  queue_api: "/api/v1/monitor/queue"
  dependencies_api: "/api/v1/monitor/dependencies"
  prometheus_port: 9091
  metrics_interval_sec: 15

minio:
  endpoint: "http://minio:9000"
  access_key: "your_access_key"
  secret_key: "your_secret_key"
  bucket: "qadata"
  timeout: 30

convert_formats:
  - source: "doc"
    target: "docx"
  - source: "ppt"
    target: "pptx"
  - source: "xls"
    target: "xlsx"
  - source: "wps"
    target: "docx"
  - source: "gif"
    target: "mp4"
  - source: "svg"
    target: "png"

api_auth:
  required: true
  app_secrets_path: "./secrets/appkeys.json"
```

---

## API响应及错误码示例

```json
{
  "status": "failure",
  "error_code": "ERR_AUTH_INVALID",
  "error_status": 4011,
  "message": "Authentication failed: invalid appid or key",
  "zh_message": "认证失败，appid或key错误",
  "output_url": null,
  "output_object": null,
  "task_id": null
}
```

---

## Copilot Agent 协作开发提示词

你是高级AI工程助手，目标是协助开发满足上述系统设计原则和功能目标的RAG知识库文档规范化转换服务，包括：

- **参数全配置化**（全部功能、行为、认证、资源、输入输出均可配置）
- **接口安全机制**：API默认要求appid和key，认证可开关，密钥支持命令行生成与删除
- **每种格式文件单独大小上限、批量/任务严格限制**
- **插件化格式转换、Celery与API双通道、高并发、结构解耦**
- **全面错误码、细致日志、自动切割清理、完整监控API与采集覆盖**
- **示例配置和文档清晰、自动化部署与可维护性强**

请完全按此进行工程实现、文档与配置输出，优先考虑安全、可扩展性、易集成、现代工程最佳实践。
