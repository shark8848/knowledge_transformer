# Docker 部署指南

本项目提供完整的 Docker 容器化部署方案，包括 FastAPI、Celery Worker、Redis、MinIO 和 Flower 监控。

## 快速开始

### 1. 构建镜像

```bash
./docker-build.sh
```

此脚本会：
- 检查 Docker 和 Docker Compose 是否安装
- 创建默认配置文件（如不存在）
- 生成 API 密钥（存储在 `secrets/appkeys.json`）
- 构建所有 Docker 镜像

### 2. 启动服务

```bash
./docker-start.sh
```

启动所有容器服务，包括：
- **Redis** (端口 6379) - Celery 消息队列
- **MinIO** (端口 9000/9001) - 对象存储
- **API** (端口 8000/9091) - FastAPI 应用 + Prometheus 指标
- **Worker** (端口 9092) - Celery 后台任务 + Prometheus 指标
- **Flower** (端口 5555) - Celery 监控界面

### 3. 检查服务状态

```bash
./docker-status.sh
```

### 4. 停止服务

```bash
./docker-stop.sh
```

## 访问地址

| 服务 | 地址 | 说明 |
|-----|------|------|
| API 接口 | http://localhost:8000 | REST API 服务 |
| API 文档 | http://localhost:8000/api/v1/docs | Swagger UI |
| 健康检查 | http://localhost:8000/healthz | 存活探针 |
| Prometheus (API) | http://localhost:9091/metrics | API 进程指标 |
| Prometheus (Worker) | http://localhost:9092/metrics | Worker 进程指标 |
| Flower UI | http://localhost:5555 | Celery 任务监控 |
| MinIO Console | http://localhost:9001 | 对象存储管理界面 |

**MinIO 默认凭据：** `minioadmin` / `minioadmin`

## 文件结构

```
.
├── Dockerfile              # 应用镜像定义
├── docker-compose.yml      # 服务编排配置
├── docker-build.sh         # 构建脚本
├── docker-start.sh         # 启动脚本
├── docker-stop.sh          # 停止脚本
├── docker-status.sh        # 状态检查脚本
└── .dockerignore           # Docker 构建排除文件
```

## 配置说明

### 环境变量

在 `docker-compose.yml` 中可以通过环境变量覆盖配置：

```yaml
environment:
  - RAG_celery__broker_url=redis://redis:6379/0
  - RAG_celery__result_backend=redis://redis:6379/1
  - RAG_minio__endpoint=http://minio:9000
  - RAG_minio__access_key=minioadmin
  - RAG_minio__secret_key=minioadmin
```

### 卷挂载

持久化数据卷：
- `redis-data` - Redis 数据
- `minio-data` - MinIO 对象存储
- `worker-temp` - Worker 临时文件

主机挂载：
- `./config` - 配置文件
- `./secrets` - API 密钥
- `./logs` - 日志文件

## 常用命令

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f flower
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart api
docker-compose restart worker
```

### 进入容器

```bash
# 进入 API 容器
docker exec -it rag-api bash

# 进入 Worker 容器
docker exec -it rag-worker bash
```

### 扩展 Worker

```bash
# 增加 Worker 实例数量
docker-compose up -d --scale worker=4
```

## 生产环境建议

### 1. 安全配置

- 修改 MinIO 默认密码
- 使用 HTTPS（Nginx 反向代理）
- 配置防火墙规则
- 限制端口暴露范围

### 2. 资源限制

在 `docker-compose.yml` 中添加资源限制：

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 4G
    reservations:
      cpus: '1'
      memory: 2G
```

### 3. 日志管理

配置日志驱动和轮转：

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "10"
```

### 4. 监控集成

- 配置 Prometheus 抓取指标
- 集成 Grafana 仪表盘
- 设置告警规则

### 5. 备份策略

定期备份：
- Redis 数据 (`redis-data` 卷)
- MinIO 对象存储 (`minio-data` 卷)
- 配置文件和密钥

## 故障排查

### API 无法启动

```bash
# 查看 API 日志
docker-compose logs api

# 检查配置文件
docker exec rag-api cat /app/config/settings.yaml
```

### Worker 无法连接 Redis

```bash
# 测试 Redis 连接
docker exec rag-worker redis-cli -h redis ping

# 检查网络连通性
docker network inspect rag-network
```

### MinIO 存储问题

```bash
# 查看 MinIO 日志
docker-compose logs minio

# 检查存储桶
docker exec rag-api mc ls minio/qadata
```

## 更新部署

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建镜像
./docker-build.sh

# 3. 停止旧服务
./docker-stop.sh

# 4. 启动新服务
./docker-start.sh
```

## 清理环境

```bash
# 停止并删除容器
docker-compose down

# 删除卷（⚠️ 会删除所有数据）
docker-compose down -v

# 删除镜像
docker rmi $(docker images -q 'knowledge_transformer*')
```
