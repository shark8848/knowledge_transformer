#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting RAG Conversion Engine services..."

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

# 启动服务
$COMPOSE_CMD up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# 检查服务状态
echo ""
echo "📊 Service Status:"
$COMPOSE_CMD ps

echo ""
echo "✅ Services started successfully!"
echo ""
echo "🌐 Access Points:"
echo "  - API:              http://localhost:8000"
echo "  - API Docs:         http://localhost:8000/api/v1/docs"
echo "  - Health Check:     http://localhost:8000/healthz"
echo "  - Prometheus (API): http://localhost:9091/metrics"
echo "  - Prometheus (Wkr): http://localhost:9092/metrics"
echo "  - Flower UI:        http://localhost:5555"
echo "  - MinIO Console:    http://localhost:9001 (minioadmin/minioadmin)"
echo ""
echo "📝 Useful Commands:"
echo "  - View logs:        $COMPOSE_CMD logs -f"
echo "  - View API logs:    $COMPOSE_CMD logs -f api"
echo "  - View worker logs: $COMPOSE_CMD logs -f worker"
echo "  - Stop services:    ./docker-stop.sh"
echo "  - Restart:          $COMPOSE_CMD restart"
