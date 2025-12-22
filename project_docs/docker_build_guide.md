# Docker 构建指引（多镜像）

本指引基于 `rag_conversion_prompt.md` 目标，覆盖依赖组件（Redis/MinIO/MySQL/Elasticsearch）与业务模块（API、Worker、Flower、API Docs、Test Report）独立构建，输出多镜像。

## 目录
- 构建产物
- 预置依赖
- 快速构建
- 自定义构建目标
- 镜像说明
- 常见问题

## 构建产物
- 业务镜像：
  - `rag-converter/api:latest`（FastAPI 服务，包含 Python 依赖与 LibreOffice/Inkscape/FFmpeg）
  - `rag-converter/worker:latest`（Celery Worker，同依赖栈）
  - `rag-converter/flower:latest`（Celery Flower UI）
  - `rag-converter/api-docs:latest`（OpenAPI 文档服务）
  - `rag-converter/test-report:latest`（测试报告浏览服务）
  - `rag-converter/bundle:latest`（一体化镜像，包含全部工具，运行时自选入口）
- 依赖镜像（封装官方镜像以统一版本与标签）：
  - `rag-converter/redis:7`
  - `rag-converter/minio:2024-11-20`
  - `rag-converter/mysql:8.0`
  - `rag-converter/es:8.14.0`

## 预置依赖
- Docker 20.10+，已启用 BuildKit/Buildx（`docker buildx version` 可用）
- 可联网获取基础镜像
- 构建节点需具备：约 4 CPU / 6GB RAM（LibreOffice/FFmpeg 安装较重）

## 快速构建
```bash
# 在仓库根目录执行
./scripts/build_images.sh            # 构建全部镜像
```
脚本会调用 `docker buildx bake -f docker/docker-bake.hcl all`。

## 自定义构建目标
```bash
./scripts/build_images.sh app-api        # 仅构建 API 镜像
./scripts/build_images.sh app-worker     # 仅构建 Worker 镜像
./scripts/build_images.sh deps-redis     # 仅构建 Redis 封装镜像
```
可用目标定义见 [docker/docker-bake.hcl](docker/docker-bake.hcl)。

## 镜像说明
- 基础 Dockerfile：`docker/Dockerfile.app`
  - 安装系统依赖：LibreOffice、Inkscape、FFmpeg、字体等
  - 安装 Python 依赖：基于 `pyproject.toml` 执行 `pip install .`
  - 通过多目标导出 API/Worker/Flower/API Docs/Test Report 镜像
- 依赖 Dockerfile：`docker/Dockerfile.deps`
  - 直接引用官方基础镜像，确保版本固定，可统一标签
- 构建编排：`docker/docker-bake.hcl`
  - 定义了各目标的 `context`、`dockerfile`、`tags` 与缓存策略

## 常见问题
- **构建耗时长/镜像大**：LibreOffice/FFmpeg 体积较大，建议开启 BuildKit 缓存（脚本已默认启用 GHA cache 配置，可按需调整）。
- **网络受限**：需要访问 Debian/Ubuntu 与 PyPI 源，可通过 `pip`、`apt` 的代理或镜像源加速（可在构建时注入 `PIP_INDEX_URL`、`http_proxy`/`https_proxy`）。
- **依赖版本调整**：修改 `docker/docker-bake.hcl` 对应 `tags`，或直接在 Dockerfile.deps 中替换基础镜像标签。
- **新增业务镜像**：在 `docker/Dockerfile.app` 添加新的构建目标，然后在 `docker/docker-bake.hcl` 中补充 target 定义和 tags。

> 构建完成后，可用 `docker images | grep rag-converter` 查看全部产物。部署时可结合已有的 `docker-compose.yml` 或自定义编排文件引入这些镜像。
