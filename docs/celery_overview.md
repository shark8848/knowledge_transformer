# Celery 组件与启动命令总览

| 组件/用途 | 启动命令摘要 | 队列 / 进程名 | 注册任务 | 端口 / 备注 |
| --- | --- | --- | --- | --- |
| 主转换 Worker | celery -A rag_converter.celery_app:celery_app worker --loglevel=info --concurrency=4 | 默认队列；worker 名 docker-ocr-service@SharkyAI | conversion.handle_batch（文档/多媒体转换与落盘） | 文档转换主力（转换/抽取管线） |
| 主 Flower | celery -A rag_converter.celery_app:celery_app flower --port=5555 --url_prefix=/flower | 监控 docker-ocr-service 等 | 监控转换任务 | 端口 5555（/flower） |
| Pipeline Worker | celery -A pipeline_service.celery_app:pipeline_celery worker -l info -Q pipeline -n docker-pipeline-service@SharkyAI | 队列 pipeline；worker 名 docker-pipeline-service@SharkyAI | pipeline.extract_and_probe（取样/探针）<br>pipeline.run_document_pipeline（编排 conversion+probe） | SI-TECH 下载/转换链路 |
| Slicer Worker | celery -A slicer_service.celery_app:celery_app worker --loglevel=info --concurrency=2 -n docker-slicer-service@SharkyAI | 默认队列；worker 名 docker-slicer-service@SharkyAI | probe.extract_signals（画像提取）<br>probe.recommend_strategy（策略推荐） | 文档切片 |
| Slicer Flower | celery -A slicer_service.celery_app:celery_app flower --port=5556 | 监控 docker-slicer-service | 监控切片任务 | 端口 5556 |
| ES Index Worker | celery -A es_index_service.tasks.celery_app worker -l info -n es-index-service@SharkyAI | 默认队列；worker 名 es-index-service@SharkyAI | es_schema.create_index（建索引）<br>es_schema.alias_switch（别名切换）<br>es_schema.bulk_ingest（批量写）<br>es_schema.rebuild_full（全量重建）<br>es_schema.rebuild_partial（局部重建） | ES 写入/管理任务 |
| ES Search Worker | celery -A es_search_service.tasks.celery_app worker -l info -n es-search-service@SharkyAI | 默认队列；worker 名 es-search-service@SharkyAI | es_search.text_search（全文检索）<br>es_search.vector_search（向量检索）<br>es_search.hybrid_search（混合检索） | ES 查询任务 |
| LLM Worker | celery -A llm_service.celery_app:llm_celery worker -l info -Q llm -n docker-llm-service@SharkyAI | 队列 llm；worker 名 docker-llm-service@SharkyAI | llm.chat（大模型对话）<br>llm.orchestrate（异步封装） | 大模型调用 |
| Vector Worker | celery -A vector_service.celery_app:vector_celery worker -l info -Q vector -n docker-vector-service@SharkyAI | 队列 vector；worker 名 docker-vector-service@SharkyAI | vector.embed（生成向量）<br>vector.rerank（重排）<br>vector.orchestrate（异步封装） | 向量检索/写入 |
| ASR Worker | celery -A asr_service.celery_app:asr_celery worker -l info -Q asr,video_asr -n docker-audio-service@SharkyAI | 队列 asr, video_asr；worker 名 docker-audio-service@SharkyAI | asr.prepare（下载/准备音频）<br>asr.transcribe（转写）<br>asr.orchestrate（异步封装） | 语音/视频音频转写 |
| Multimodal Worker | celery -A multimodal_service.celery_app:mm_celery worker -l info -Q mm,video_vision -n docker-multimodal-service@SharkyAI | 队列 mm, video_vision；worker 名 docker-multimodal-service@SharkyAI | mm.call（多模态调用）<br>mm.orchestrate（异步封装） | 多模态解析 |
| Video Worker | celery -A video_service.celery_app:video_celery worker -l info -Q video -n docker-video-service@SharkyAI | 队列 video；worker 名 docker-video-service@SharkyAI | video.process（切片/抽帧/上传清单）<br>video.orchestrate（异步封装） | 视频转码/处理 |
| Meta Worker（若启用） | celery -A meta_service.celery_app:meta_celery worker -l info -Q meta -n docker-meta-service@SharkyAI | 队列 meta；worker 名 docker-meta-service@SharkyAI | meta.process（聚合元数据）<br>meta.orchestrate（异步封装） | 元数据补充（未必默认拉起） |

> 以上为当前环境运行中的 Celery 进程及对应命令/队列；容器化部署时命令由 docker-compose.yml 中的服务定义自动拉起。
