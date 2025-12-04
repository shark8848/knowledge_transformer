PYTHON ?= python3
UVICORN ?= uvicorn
APP_MODULE ?= rag_converter.app:app
CELERY_APP ?= rag_converter.celery_app:celery_app

.PHONY: run worker lint format test keys

run:
	RAG_CONFIG_FILE=./config/settings.yaml $(UVICORN) $(APP_MODULE) --reload

worker:
	RAG_CONFIG_FILE=./config/settings.yaml celery -A rag_converter.celery_app.celery_app worker -l info

lint:
	ruff check src tests

format:
	ruff format src tests

test:
	pytest

keys:
	PYTHONPATH=src $(PYTHON) scripts/manage_appkey.py list
