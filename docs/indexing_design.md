# 索引设计方案（基于通用多模态 RAG mm-schema）

本文给出基于 `src/schema/mm-schema.json` 的索引设计，涵盖关键词（倒排）、向量以及混合检索，并说明索引的管理、更新与重建策略。

## 1. 数据切面与索引字段

- 文档级：`document_id`, `kb_id`, `kb_type`, `status`, `vector_status`, `document_metadata.title`, `document_metadata.tags`, `document_metadata.duration`, `document_metadata.total_chunks`, `document_metadata.audio.url`。
- 分块级：`chunks[].chunk_id`, `chunks[].temporal.start_time/end_time/duration/chunk_index`, `chunks[].media_type`, `chunks[].content.text.full_text`, `chunks[].content.text.segments[]`, `chunks[].content.audio.url`, `chunks[].content.video.url`, `chunks[].keyframes[].description`, `chunks[].keyframes[].timestamp`, `chunks[].processing.processing_time/status`。
- 结构化：`document_summary.*`, `analysis.*`（如实体、情感、关键词、visual_objects），`quality_metrics.*`。

## 2. 关键词倒排索引

- 建议分索引库：
  - `doc_meta_idx`：面向文档级过滤与排序；字段：`kb_id`, `kb_type`, `status`, `vector_status`, `document_metadata.title`, `document_metadata.tags`, `document_metadata.duration`, `document_metadata.total_chunks`。
  - `chunk_text_idx`：面向分块检索；字段：`chunk_id`, `document_id`, `chunk_index`, `content.text.full_text`, `content.text.segments.text`（分词后加入位置），`keyframes.description`（合并为 chunk-level text），`analysis.entities.text`, `analysis.keywords`。
  - `analysis_idx`（可选）：专门索引用于结构化过滤，字段：`analysis.speakers.speaker_id/name`, `analysis.sentiment.label`, `analysis.visual_objects.label`, `quality_metrics.*`。
- 分词与规范化：
  - 中文：使用 jieba / ICU；英文：lowercase + stemming；数字/时间保留。
  - 存储 `chunk_index`、`timestamp` 作为 payload，便于命中回放。
- 排序：BM25 + 时间衰减（可选）；支持按 `processing.processing_time`、`quality_metrics.clarity_score` 进行二级排序。

## 3. 向量索引

- 向量类型：
  - 文本向量（块）：对 `content.text.full_text`（或拼接 segments）生成文本 embedding，用于精确段落/时间片召回。
  - 文本向量（摘要）：对 `document_summary.abstract`、`document_summary.key_points` 拼接生成摘要 embedding，用于文档级快速粗排或导航。
  - 图像向量：对 `keyframes.thumbnail_url` 抽取视觉 embedding（可离线提取并存储至 `keyframes.embedding`）。
  - 多模态向量（可选）：对文本+关键帧拼接生成多模态 embedding，存入 `vector.embedding`，`embedding_type="multimodal"`。
- 索引库建议：
  - `vec_text`: 维度 d_t，度量 cosine；存储 `chunk_id`, `document_id`, `kb_id`, `chunk_index`, `start_time`, `end_time`。
  - `vec_summary`: 维度 d_s，度量 cosine；存储 `document_id`, `kb_id`, `summary_type` (abstract/key_points)；用于文档级导航或预过滤后再下钻到 chunk。
  - `vec_image`: 维度 d_i，度量 cosine；存储 `chunk_id`, `document_id`, `kb_id`, `keyframe_ts`。
  - `vec_mm`（可选）: 多模态向量，度量 cosine。
- 过滤字段：在向量库中保留可过滤的元数据（`kb_id`, `kb_type`, `status`, `media_type`, `chunk_index`, `start_time`）。
- 引擎：Milvus / Qdrant / Vespa / Elasticsearch vector；启用 HNSW（M=16-32, ef_construction=200-400, ef_search 可调）。

## 4. 混合检索（Lexical + Vector）

- Flow：
  1) 关键词检索获取候选 chunk_id（BM25）。
  2) 向量检索（文本/多模态）获取候选。
  3) 候选集合归并去重；使用加权打分：`score = alpha * bm25_norm + beta * vec_norm (+ gamma * recency)`。
  4) 结构化过滤（`kb_id`, `status`, 时间范围、`media_type`、情感/实体标签等）。
  5) 重排（可用轻量 LTR / cross-encoder / reranker）。
- 参数：
  - `alpha/beta` 默认 0.5/0.5，可按查询类型动态调节（问答偏向向量，导航偏向关键词）。
  - 截断：向量前 k=200，关键词前 k=200，归并后保留 top N=50 进入 rerank。

## 5. 索引管理与更新

- 写入路径：
  - `process_video` 产出 manifest：
    - 文本入倒排：`chunk_text_idx`；
    - 向量入 `vec_text`（文本 embedding）/`vec_image`（关键帧 embedding）。
    - 文档摘要向量入 `vec_summary`（`abstract`、`key_points` 拼接后各自生成 embedding，可双写两条记录标记 `summary_type`）。
  - 关键帧描述更新：重新写入倒排与向量（若 embedding 重算）。
- 更新策略：
  - 增量：按 `document_id` / `chunk_id` upsert（倒排删除旧文档再写；向量 upsert 覆盖）。
  - 部分字段更新（如 tags/状态）：直接更新 meta，不重建向量。
  - 内容更新（文本/描述变更）：重算对应 embedding；倒排重写；向量 upsert。
- 状态字段：
  - `vector_status`：`pending/ready/failed`，控制是否可被向量检索。
  - `status`：过滤不可用文档（`archived/disabled/draft`）。

## 6. 重建策略

- 触发条件：
  - 模型版本升级（文本/图像 embedding 模型变更）。
 向量类型：
  - 索引参数大改（HNSW M/ef，或存储引擎迁移）。
 索引库建议（实体存放在向量引擎，manifest 仅保留必要引用/ID）：
  1) 离线重算 embedding（新模型写入新集合 `vec_text_v2` / `vec_image_v2`）。
 过滤字段：在向量库中保留可过滤的元数据（`kb_id`, `kb_type`, `status`, `media_type`, `chunk_index`, `start_time`）。
 引擎：Milvus / Qdrant / Vespa / Elasticsearch vector；启用 HNSW（M=16-32, ef_construction=200-400, ef_search 可调）。
 存储建议：
  - 在 manifest（MinIO/S3）中不落地完整向量，仅保留 `vector_ref_id` 或 `embedding_store` 元数据；
  - 向量引擎存储：`id`=chunk_id 或 keyframe_id，附带元数据（kb_id/kb_type/status/timestamps）；
  - 若必须随 manifest 交付，可截断或量化（如 float16 / PQ code）以减小体积，并提供 `embedding_format` 标识。
  4) 切换：更新路由配置指向 v2；观察；再淘汰 v1。
  - `vec_text`: 维度 d_t，度量 cosine；存储 `chunk_id`, `document_id`, `kb_id`, `chunk_index`, `start_time`, `end_time`。
  - `vec_summary`: 维度 d_s，度量 cosine；存储 `document_id`, `kb_id`, `summary_type` (abstract/key_points)；用于文档级导航或预过滤后再下钻到 chunk。
  - `vec_image`: 维度 d_i，度量 cosine；存储 `chunk_id`, `document_id`, `kb_id`, `keyframe_ts`。
  - `vec_mm`（可选）: 多模态向量，度量 cosine。
  - 写入/查询 QPS、P99；向量召回率（A/B 对比）；BM25 与混合的 NDCG；
  - 索引大小、碎片率；HNSW ef_search 变化对延迟/召回的影响；
  - 失败率：向量 upsert 失败、倒排写失败；
  - 延迟：embedding 生成耗时、caption 生成耗时、整体 processing_time。
- 任务与调度：
  - 日常增量：消费 `process_video` 产出队列，实时 upsert。
  - 周期校验：夜间跑一致性校验（chunk_id 总数、hash 比对）。
  - 失效链接清理：定期校验 `storage_url`/`thumbnail_url` 可达性。

## 8. 查询示例（伪接口）

- 关键词：`/search?kb_id=...&q=交付计划&media=video&time_gte=300&time_lt=600` → 命中 `chunk_text_idx`，按 BM25 排序。
- 向量：`/search/vec`，body: `{ "kb_id": "...", "embedding": [...], "topk": 50 }` → 命中 `vec_text`。
- 混合：`/search/hybrid`，body: `{ "kb_id": "...", "q": "交付计划", "embedding": [...], "alpha":0.4, "beta":0.6 }` → 归并重排。

## 9. 权限与多租户

- 所有索引保留 `kb_id/kb_type/org_id` 作为强过滤字段；可将 org_id 作为路由分片键。
- 跨租户隔离：可采用独立 collection（按 org/kb 划分）或全局索引 + 路由过滤；向量库同理。

## 10. 异常与回滚

- 写失败：记录 dead-letter，定期补偿；
- 部分字段更新失败：保持旧版本，待重试；
- 重建失败：保持 v1 索引，重建任务回滚，告警。
