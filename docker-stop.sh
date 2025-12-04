#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Stopping RAG Conversion Engine services..."

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

# 停止服务
$COMPOSE_CMD down

echo ""
echo "✅ Services stopped successfully!"
echo ""
echo "💡 Tips:"
echo "  - Start again:      ./docker-start.sh"
echo "  - Remove volumes:   $COMPOSE_CMD down -v"
echo "  - Remove images:    docker rmi \$(docker images -q 'rag-*')"
