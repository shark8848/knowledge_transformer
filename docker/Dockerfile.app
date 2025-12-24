# Multi-target Dockerfile for rag_converter services (API, worker, Flower, docs, report)
# Refined to keep heavy system tools (LibreOffice, Inkscape, FFmpeg) only in images that need them.

FROM python:3.11-slim AS python-base

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Common troubleshooting and client tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        vim \
        nano \
        less \
        curl \
        wget \
        net-tools \
        iproute2 \
        procps \
        lsof \
        telnet \
        netcat-traditional \
        tree \
        htop \
        redis-tools \
        default-mysql-client \
        postgresql-client \
        libxml2 \
        libxml2-dev \
        libxslt1.1 \
        libxslt1-dev \
        libjpeg62-turbo-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG USE_VENV=true

# ---------- Python deps: base only (used by lightweight services) ----------
FROM python-base AS app-deps-base
ARG USE_VENV
RUN mkdir -p /opt/venv \
    && if [ "${USE_VENV}" = "true" ]; then python -m venv /opt/venv; fi
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
COPY src ./src
RUN if [ "${USE_VENV}" = "true" ]; then . /opt/venv/bin/activate; fi \
    && pip install --upgrade pip \
    && pip install --no-cache-dir .

# ---------- Python deps: converter extras (used by core/bundle/worker/api) ----------
FROM python-base AS app-deps
ARG USE_VENV
RUN mkdir -p /opt/venv \
    && if [ "${USE_VENV}" = "true" ]; then python -m venv /opt/venv; fi
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
COPY src ./src
RUN if [ "${USE_VENV}" = "true" ]; then . /opt/venv/bin/activate; fi \
    && pip install --upgrade pip \
    && pip install --no-cache-dir \
        '.[converter]' \
        pytest pytest-asyncio pytest-html pytest-metadata \
        huggingface-hub tiktoken dashscope boto3 \
        python-docx python-pptx pypdf lxml pillow openpyxl xlsxwriter

# ---------- Runtime without heavy system deps ----------
FROM python-base AS runtime-common
ARG USE_VENV
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=app-deps /opt/venv /opt/venv
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY secrets ./secrets
COPY scripts ./scripts
COPY start_*.sh stop_*.sh show_*.sh .
COPY .env ./.env
COPY api_docs_server.py test_report_server.py test-report.html README.md ./
COPY docker/entrypoint.sh ./entrypoint.sh
RUN set -e \
    && if [ "${USE_VENV}" != "true" ]; then \
         pip install --upgrade pip \
        && pip install --no-cache-dir \
            '.[converter]' \
            pytest pytest-asyncio pytest-html pytest-metadata \
            huggingface-hub tiktoken dashscope boto3 \
            python-docx python-pptx pypdf lxml pillow openpyxl xlsxwriter; \
       fi \
    && chmod +x /app/entrypoint.sh \
    && find /app -maxdepth 1 \( -name "start_*.sh" -o -name "stop_*.sh" -o -name "show_*.sh" \) -print0 | xargs -0 -r chmod +x
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]

# ---------- Runtime with conversion tools (used by worker/bundle) ----------
FROM runtime-common AS conversion-runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice \
        ffmpeg \
        inkscape \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ---------- Runtime with media tools only (FFmpeg) ----------
FROM runtime-common AS media-runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ---------- API ----------
FROM runtime-common AS api
EXPOSE 8000 9091
ENV RAG_CONFIG_FILE=/app/config/settings.yaml
CMD ["uvicorn", "rag_converter.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------- Worker ----------
FROM conversion-runtime AS worker
EXPOSE 9092
ENV RAG_CONFIG_FILE=/app/config/settings.yaml
CMD ["celery", "-A", "rag_converter.celery_app.celery_app", "worker", "-l", "info"]

# ---------- Flower ----------
FROM runtime-common AS flower
EXPOSE 5555
ENV RAG_CONFIG_FILE=/app/config/settings.yaml
CMD ["celery", "-A", "rag_converter.celery_app.celery_app", "flower", "--port=5555", "--url_prefix=/flower"]

# ---------- API Docs ----------
FROM runtime-common AS api-docs
EXPOSE 8090
ENV API_DOCS_PORT=8090 \
    API_DOCS_HOST=0.0.0.0 \
    API_DOCS_CONFIG=/app/config/settings.yaml
CMD ["python", "/app/api_docs_server.py"]

# ---------- Test Report Server ----------
FROM runtime-common AS test-report
EXPOSE 8088
ENV TEST_REPORT_PORT=8088 \
    TEST_REPORT_HOST=0.0.0.0 \
    TEST_REPORT_PATH=/app/test-report.html
CMD ["python", "/app/test_report_server.py"]

# ---------- Bundle (all tools preinstalled, choose entrypoint at runtime) ----------
FROM conversion-runtime AS bundle
EXPOSE 8000 8088 8090 9091 9092 5555
ENV RAG_CONFIG_FILE=/app/config/settings.yaml
CMD ["api"]

# ---------- Module: ASR Service ----------
FROM media-runtime AS asr-service
RUN pip install --no-cache-dir '.[asr]'
EXPOSE 8200 5558
ENV ASR_API_PORT=8200 \
    ASR_FLOWER_PORT=5558
CMD ["worker"]

# ---------- Module: LLM Service ----------
FROM python-base AS llm-service
ARG USE_VENV
RUN if [ "${USE_VENV}" = "true" ]; then python -m venv /opt/venv; fi
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY secrets ./secrets
RUN if [ "${USE_VENV}" = "true" ]; then . /opt/venv/bin/activate; fi \
    && pip install --upgrade pip \
    && pip install --no-cache-dir '.[llm]'
COPY config ./config
COPY scripts ./scripts
COPY start_*.sh stop_*.sh show_*.sh .
COPY api_docs_server.py test_report_server.py test-report.html README.md ./
COPY docker/entrypoint.sh ./entrypoint.sh
RUN set -e \
    && chmod +x /app/entrypoint.sh \
    && find /app -maxdepth 1 \( -name "start_*.sh" -o -name "stop_*.sh" -o -name "show_*.sh" \) -print0 | xargs -0 -r chmod +x
EXPOSE 5560
ENV LLM_FLOWER_PORT=5560
CMD ["worker"]

# ---------- Module: Multimodal Service ----------
FROM media-runtime AS multimodal-service
EXPOSE 8300 5559
ENV MM_API_PORT=8300 \
    MM_FLOWER_PORT=5559
CMD ["api"]

# ---------- Module: Pipeline Service ----------
FROM runtime-common AS pipeline-service
CMD ["api"]

# ---------- Module: Meta Service ----------
FROM runtime-common AS meta-service
CMD ["api"]

# ---------- Module: Slicer Service ----------
FROM runtime-common AS slicer-service
CMD ["api"]

# ---------- Module: UI Service ----------
FROM runtime-common AS ui-service
RUN pip install --no-cache-dir '.[ui]'
CMD ["api"]

# ---------- Module: Vector Service ----------
FROM python-base AS vector-service
ARG USE_VENV
RUN if [ "${USE_VENV}" = "true" ]; then python -m venv /opt/venv; fi
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN if [ "${USE_VENV}" = "true" ]; then . /opt/venv/bin/activate; fi \
    && pip install --upgrade pip \
    && pip install --no-cache-dir .
COPY config ./config
COPY scripts ./scripts
COPY start_*.sh stop_*.sh show_*.sh .
COPY api_docs_server.py test_report_server.py test-report.html README.md ./
COPY docker/entrypoint.sh ./entrypoint.sh
RUN set -e \
    && chmod +x /app/entrypoint.sh \
    && find /app -maxdepth 1 \( -name "start_*.sh" -o -name "stop_*.sh" -o -name "show_*.sh" \) -print0 | xargs -0 -r chmod +x
EXPOSE 5562
ENV VECTOR_FLOWER_PORT=5562
CMD ["worker"]

# ---------- Module: Video Service ----------
FROM media-runtime AS video-service
EXPOSE 9200
ENV SERVICE_NAME=video \
    VIDEO_API_PORT=9200
CMD ["api"]
