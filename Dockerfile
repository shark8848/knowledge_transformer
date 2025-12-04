FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # LibreOffice for doc->docx conversion
    libreoffice \
    libreoffice-writer \
    # Inkscape for svg->png conversion
    inkscape \
    # FFmpeg for multimedia conversions
    ffmpeg \
    # 其他工具
    curl \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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
