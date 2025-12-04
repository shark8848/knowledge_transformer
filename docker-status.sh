#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📊 RAG Conversion Engine - Service Status"
echo "=========================================="
echo ""

# 检查 docker-compose 命令
COMPOSE_CMD=""
if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "❌ Error: Docker Compose not found"
    exit 1
fi

# 显示容器状态
echo "🐳 Container Status:"
$COMPOSE_CMD ps
echo ""

# 检查各服务健康状态
echo "🏥 Health Checks:"
echo ""

# API 健康检查
if curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "✅ API Service:       Running (http://localhost:8000)"
else
    echo "❌ API Service:       Not responding"
fi

# Redis 检查
if docker exec rag-redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis:             Connected"
else
    echo "❌ Redis:             Not responding"
fi

# MinIO 检查
if curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo "✅ MinIO:             Running (http://localhost:9001)"
else
    echo "❌ MinIO:             Not responding"
fi

# Flower 检查
if curl -sf http://localhost:5555 > /dev/null 2>&1; then
    echo "✅ Flower UI:         Running (http://localhost:5555)"
else
    echo "❌ Flower UI:         Not responding"
fi

echo ""
echo "📈 Metrics Endpoints:"
if curl -sf http://localhost:9091/metrics > /dev/null 2>&1; then
    echo "✅ API Metrics:       http://localhost:9091/metrics"
else
    echo "❌ API Metrics:       Not available"
fi

if curl -sf http://localhost:9092/metrics > /dev/null 2>&1; then
    echo "✅ Worker Metrics:    http://localhost:9092/metrics"
else
    echo "❌ Worker Metrics:    Not available"
fi

echo ""
echo "📝 Quick Commands:"
echo "  - View all logs:    $COMPOSE_CMD logs -f"
echo "  - API logs:         $COMPOSE_CMD logs -f api"
echo "  - Worker logs:      $COMPOSE_CMD logs -f worker"
echo "  - Restart all:      $COMPOSE_CMD restart"
echo "  - Stop all:         ./docker-stop.sh"
