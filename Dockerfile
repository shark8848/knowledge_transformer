FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 预先复制插件依赖声明，便于构建期自动安装
ARG PLUGIN_DEPS_FILE=/tmp/plugins-deps.yaml
COPY config/plugins-deps.yaml ${PLUGIN_DEPS_FILE}

# 安装系统依赖（包含插件声明的外部依赖）
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3-yaml; \
    BASE_PACKAGES="curl wget"; \
    PLUGIN_PACKAGES="$(python3 - <<'PY'
import yaml, pathlib
path = pathlib.Path("${PLUGIN_DEPS_FILE}")
pkgs: list[str] = []
if path.exists():
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    deps = data.get('dependencies', {}) or {}
    for items in deps.values():
        if items:
            pkgs.extend(items)
pkgs = sorted(set(pkgs))
print(' '.join(pkgs))
PY
)"; \
    INSTALL_PACKAGES="$BASE_PACKAGES $PLUGIN_PACKAGES"; \
    apt-get install -y --no-install-recommends ${INSTALL_PACKAGES}; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml ./
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY README.md ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -e .

# 创建必要的目录
RUN mkdir -p logs secrets .run

# 暴露端口
# 8000: FastAPI
# 9091: Prometheus metrics (API)
# 9092: Prometheus metrics (Worker)
# 5555: Flower UI
EXPOSE 8000 9091 9092 5555

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# 默认启动 FastAPI 应用
CMD ["uvicorn", "rag_converter.app:app", "--host", "0.0.0.0", "--port", "8000"]
