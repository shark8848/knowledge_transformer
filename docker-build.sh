#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🐳 Building RAG Conversion Engine Docker Images..."

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed"
    exit 1
fi

# 检查 Docker Compose 是否安装
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Error: Docker Compose is not installed"
    exit 1
fi

# 确保配置文件存在
if [ ! -f "config/settings.yaml" ]; then
    echo "⚙️  Creating default settings.yaml from example..."
    cp config/settings.example.yaml config/settings.yaml
fi

# 确保密钥目录存在
if [ ! -d "secrets" ]; then
    echo "🔑 Creating secrets directory..."
    mkdir -p secrets
fi

# 生成默认密钥（如果不存在）
if [ ! -f "secrets/appkeys.json" ]; then
    echo "🔑 Generating default API keys..."
    cat > secrets/appkeys.json <<EOF
{
  "demo-app": {
    "key": "$(openssl rand -hex 32)",
    "description": "Default demo application",
    "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  }
}
EOF
    echo "✓ Generated demo-app credentials (check secrets/appkeys.json)"
fi

# 构建镜像
echo "📦 Building Docker images..."
if docker compose version &> /dev/null; then
    docker compose build
else
    docker-compose build
fi

echo ""
echo "✅ Docker images built successfully!"
echo ""
echo "Next steps:"
echo "  1. Review config/settings.yaml for custom settings"
echo "  2. Start services: ./docker-start.sh"
echo "  3. View logs: docker-compose logs -f"
echo "  4. Stop services: ./docker-stop.sh"
