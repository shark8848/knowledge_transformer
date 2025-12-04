# 配置指南

该引擎的所有能力均通过 `config/settings.yaml`、环境变量或命令行参数注入，底层基于 `pydantic-settings` 支持热加载与分层覆盖。

## 配置加载顺序

1. **环境变量 `RAG_CONFIG_FILE`**：指向自定义 YAML，优先级最高。
2. **默认文件 `config/settings.yaml`**。
3. **内建默认值**：若文件缺失，仍可启动但仅包含最小能力。

环境变量前缀统一为 `RAG_`，支持嵌套字段，如：

```bash
export RAG_file_limits__default_max_size_mb=200
export RAG_api_auth__required=false
```

## 关键配置段

### file_limits

| 字段 | 说明 |
| --- | --- |
| `default_max_size_mb` | 默认单文件大小上限 |
| `per_format_max_size_mb` | 按格式覆盖的最大值 |
| `max_total_upload_size_mb` | 单任务累计体积限制 |
| `max_files_per_task` | 单任务文件数量限制 |

### api_auth

- `required`：是否启用 `appid/key` 校验。
- `app_secrets_path`：密钥 JSON 文件路径，`scripts/manage_appkey.py` 会自动维护。
- `header_appid`/`header_key`：自定义请求头。

### celery

| 字段 | 说明 |
| --- | --- |
| `broker_url` | Celery Broker（示例为 Redis） |
| `result_backend` | 结果存储，默认 Redis |
| `default_queue` | 任务队列名称 |
| `task_time_limit_sec` | 单任务超时 |
| `prefetch_multiplier` | Worker 预取策略 |

### monitoring

提供可观测 API 的路径和 Prometheus 端口。HTTP 指标端点默认位于 `http://<host>:prometheus_port/metrics`（API 进程），Celery worker 启动时会自动启用 `prometheus_port + 1`，若需自定义可在部署脚本中覆盖相关环境变量（例如 `RAG_monitoring__prometheus_port`）。

## 插件声明

`convert_formats` 列表用于文档化和前端展示，真实能力由 `src/rag_converter/plugins` 注册的插件决定；若注册插件为空，则回退到配置中的声明。默认示例包括：

- 文档/图片：`doc→docx`（LibreOffice）、`svg→png`（Inkscape）、`webp→png`（FFmpeg）
- 视频：`gif/avi/mov/mkv/webm/mpeg→mp4`（FFmpeg）
- 音频：`wav/flac/ogg/aac→mp3`（FFmpeg）

可根据业务场景继续扩展。

### 插件模块配置与 CLI

- `plugin_modules_file`：指向一个 YAML 文件（默认 `config/plugins.yaml`），存放需要自动导入的模块列表。
- `plugin_modules`：若希望通过环境变量或 Helm 覆盖，可直接提供模块数组，优先级高于文件。

系统在启动 FastAPI 与 Celery 时会依序读取 `plugin_modules` → `plugin_modules_file` → 内建默认模块，以确保所有插件模块均被导入并自动调用 `REGISTRY.register` 完成注册。

可使用 Shell 脚本便捷管理该文件：

```bash
./scripts/manage_plugins.sh list
./scripts/manage_plugins.sh register mypkg.plugins.xlsx_to_pdf
./scripts/manage_plugins.sh reset
```

脚本会在必要时创建文件，并在注册时校验模块可导入，保证部署一致性。

### 插件依赖管理

系统支持在 `config/plugins-deps.yaml` 中声明插件所需的外部依赖（系统工具或 Python 包），并通过脚本统一安装：

```bash
# 查看所有插件依赖
./scripts/manage_plugins.sh deps list

# 为插件设置依赖（系统工具名或 pip 包）
./scripts/manage_plugins.sh deps set custom.plugins.pdf_converter pypdf2 pillow

# 安装特定插件的依赖
./scripts/manage_plugins.sh deps install custom.plugins.pdf_converter

# 安装所有插件的依赖
./scripts/manage_plugins.sh deps install

# 移除插件依赖声明
./scripts/manage_plugins.sh deps remove custom.plugins.pdf_converter
```

内置插件已预先配置好依赖（LibreOffice、Inkscape、FFmpeg），部署时需确保这些工具已安装到系统 `PATH` 中。

## CLI 管理密钥

```bash
PYTHONPATH=src python scripts/manage_appkey.py generate --appid demo
PYTHONPATH=src python scripts/manage_appkey.py delete demo
PYTHONPATH=src python scripts/manage_appkey.py list
```

脚本会自动读取 `settings.api_auth.app_secrets_path` 并维护 JSON。生产环境建议结合 Vault/Secrets Manager 同步管理。

## 外部依赖

- **Redis**：作为 Celery broker/result backend，在健康检测与 Prometheus 队列深度指标中使用。
- **MinIO/S3 兼容存储**：用于下载输入、上传输出；相关凭据在 `minio` 段配置。
- **LibreOffice / Inkscape / FFmpeg**：分别支撑 `doc→docx`、`svg→png`、`gif→mp4` 插件，需要系统层面安装二进制可执行文件。
