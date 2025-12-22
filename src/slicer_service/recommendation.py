"""Lightweight probe feature extraction and strategy recommendation (standalone)."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

FORMAT_TABLE = {"xlsx", "xls", "csv", "tsv"}
FORMAT_CODE = {"py", "c", "cpp", "java", "js", "ts", "go", "rs", "rb", "php", "sh", "log"}
FORMAT_SLIDE = {"ppt", "pptx"}
FORMAT_TEXT_BIASED_HEADING = {"doc", "docx", "pdf", "html", "htm"}

# 统一对外的切分模式（仅三类）
MODE_DIRECT = "direct_delimiter"
MODE_SEMANTIC = "semantic_sentence"
MODE_HIERARCHICAL = "hierarchical_heading"
MODE_ID_MAP = {MODE_DIRECT: 1, MODE_SEMANTIC: 2, MODE_HIERARCHICAL: 3}


def _normalize_fmt(fmt: str | None) -> str:
    return (fmt or "").strip().lower().lstrip(".")


def _format_prior_bias(fmt: str | None) -> Dict[str, float]:
    fmt_norm = _normalize_fmt(fmt)
    bias = {
        "heading_block_length_split": 0.0,
        "sentence_split_sliding": 0.0,
        "table_batch": 0.0,
        "code_log_block": 0.0,
    }

    if not fmt_norm:
        return bias

    if fmt_norm in FORMAT_TABLE:
        bias["table_batch"] += 0.35
        bias["heading_block_length_split"] -= 0.15
        bias["sentence_split_sliding"] -= 0.15
    elif fmt_norm in FORMAT_CODE:
        bias["code_log_block"] += 0.35
        bias["heading_block_length_split"] -= 0.1
        bias["sentence_split_sliding"] -= 0.1
        bias["table_batch"] -= 0.1
    elif fmt_norm in FORMAT_TEXT_BIASED_HEADING:
        bias["heading_block_length_split"] += 0.1
        bias["sentence_split_sliding"] += 0.05
    # slides单独硬路由，不在打分中加偏置
    return bias

DEFAULT_WEIGHTS = {
    "w_h": 0.6,
    "w_l": 0.4,
    "w_t": 0.8,
    "w_c": 0.8,
    "w_p": 0.3,
}

DEFAULT_THRESHOLDS = {
    "t1_table": 0.10,
    "t2_code": 0.05,
    "m1_math": 0.08,
    "epsilon": 0.05,
}

DEFAULT_TEXT_PARAMS = {
    "target_length": 220,
    "overlap_ratio": 0.15,
}

DEFAULT_CUSTOM_CFG = {
    "enable": False,
    "delimiters": [],
    "min_segments": 5,
    "min_segment_len": 30,
    "max_segment_len": 800,
    "overlap_ratio": None,
}


def _compress_scores_to_unit(scores: Dict[str, float]) -> Dict[str, float]:
    """将分数压缩/截断到[-1, 1]区间，用于跨页累计后归一化。"""
    return {k: max(-1.0, min(1.0, v)) for k, v in scores.items()}


def _quantile(values: Sequence[float], q: float) -> float:
    """计算分位数，输入为空时返回 0."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    low = int(pos)
    high = min(low + 1, len(sorted_vals) - 1)
    if low == high:
        return float(sorted_vals[low])
    frac = pos - low
    return float(sorted_vals[low] * (1 - frac) + sorted_vals[high] * frac)


def _paragraph_lengths(samples: Iterable[str]) -> List[int]:
    """按空行分段，统计每段长度，用于估计段落分布."""
    lengths: List[int] = []
    for text in samples:
        if not text:
            continue
        parts = re.split(r"\n\s*\n", text)
        for part in parts:
            clean = part.strip()
            if clean:
                lengths.append(len(clean))
    return lengths


def _line_iter(samples: Iterable[str]) -> List[str]:
    """逐行提取非空文本，便于特征计数."""
    lines: List[str] = []
    for text in samples:
        if not text:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def extract_signals_from_samples(samples: Sequence[str]) -> Dict[str, Any]:
    """基于文本样本提取结构信号（标题/列表/表格/代码比例等）。"""
    if not samples:
        raise ValueError("At least one text sample is required for probing")

    lines = _line_iter(samples)
    total_lines = max(len(lines), 1)

    heading_pattern = re.compile(
        r"^(#{1,6}\s+|\d+(?:\.\d+)*[\.\)]?\s*|\d+\.\[[^\]]*\]\s*|[一二三四五六七八九十]+、\s*)"
    )
    list_pattern = re.compile(r"^(?:[-*+•]\s+|\d+\.\s+)")
    table_like_pattern = re.compile(r"\|")
    code_like_pattern = re.compile(r"(```|\bclass\b|\bdef\b|\bfunction\b|;\s*$)")

    heading_hits = sum(1 for line in lines if heading_pattern.match(line))
    list_hits = sum(1 for line in lines if list_pattern.match(line))
    table_hits = sum(
        1
        for line in lines
        if (table_like_pattern.search(line) and line.count("|") >= 2)
        or line.count(",") >= 3
    )
    code_hits = sum(1 for line in lines if code_like_pattern.search(line))

    digit_symbol_count = sum(1 for ch in "".join(lines) if not ch.isalpha())
    total_chars = max(len("".join(lines)), 1)

    para_lengths = _paragraph_lengths(samples)
    p90_len = int(_quantile(para_lengths, 0.9)) if para_lengths else 0
    p50_len = int(_quantile(para_lengths, 0.5)) if para_lengths else 0

    return {
        "heading_ratio": heading_hits / total_lines,
        "list_ratio": list_hits / total_lines,
        "table_ratio": table_hits / total_lines,
        "code_ratio": code_hits / total_lines,
        "p90_para_len": p90_len,
        "p50_para_len": p50_len,
        "digit_symbol_ratio": digit_symbol_count / total_chars,
        "samples": list(samples),
    }


def detect_delimiter_hits(samples: Sequence[str], delimiters: Sequence[str]) -> int:
    """检测自定义分隔符可切分出的最大片段数，用于定制策略强制触发。"""
    if not samples or not delimiters:
        return 0
    max_segments = 0
    for delim in delimiters:
        try:
            pattern = re.compile(delim)
        except re.error:
            continue
        for text in samples:
            if not text:
                continue
            split_segments = [seg for seg in pattern.split(text) if seg.strip()]
            max_segments = max(max_segments, len(split_segments))
    return max_segments


def _round_value(val: Any, places: int) -> Any:
    """限制浮点精度，避免下游展示过多小数。"""
    if not isinstance(val, (int, float)):
        return val
    return float(f"{float(val):.{places}f}")


def _round_scores(scores: Dict[str, Any] | None, places: int = 3) -> Dict[str, Any] | None:
    """批量四舍五入分数字典。"""
    if scores is None:
        return None
    return {k: _round_value(v, places) for k, v in scores.items()}


def _round_profile(profile: Dict[str, Any], places: int = 3) -> Dict[str, Any]:
    """对探测 profile 的数值字段做精度限制。"""
    return {k: _round_value(v, places) for k, v in profile.items()}


def estimate_params(profile: Dict[str, Any], strategy: str, custom_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """根据选定策略生成参数，例如目标长度、重叠率或表格/代码特殊参数。"""
    target_length_hint = profile.get("p50_para_len") or DEFAULT_TEXT_PARAMS["target_length"]
    target_length = min(max(int(target_length_hint), 150), 400)
    overlap_ratio = custom_cfg.get("overlap_ratio") or DEFAULT_TEXT_PARAMS["overlap_ratio"]

    params: Dict[str, Any] = {
        "target_length": target_length,
        "overlap_ratio": overlap_ratio,
    }

    if strategy == "custom_delimiter_split":
        params.update(
            {
                "delimiters": custom_cfg.get("delimiters") or [],
                "min_segment_len": custom_cfg.get("min_segment_len", 30),
                "max_segment_len": custom_cfg.get("max_segment_len", 800),
                "overlap_ratio": overlap_ratio,
            }
        )
    elif strategy == "table_batch":
        params.update({"preserve_tables": True})
    elif strategy == "code_log_block":
        params.update({"no_overlap": True})
    elif strategy == "slide_block_textbox_merge":
        params.update({"merge_textboxes": True})

    return params


def recommend_strategy(
    profile: Dict[str, Any],
    *,
    samples: Sequence[str] | None = None,
    custom_cfg: Dict[str, Any] | None = None,
    emit_candidates: bool = False,
    source_format: str | None = None,
) -> Dict[str, Any]:
    """核心推荐逻辑：依据结构信号与阈值/权重，选出最优切分策略。"""
    cfg = {**DEFAULT_CUSTOM_CFG, **(custom_cfg or {})}
    weights = DEFAULT_WEIGHTS
    thresholds = DEFAULT_THRESHOLDS
    fmt_norm = _normalize_fmt(source_format or profile.get("source_format"))
    prior_bias = _format_prior_bias(fmt_norm)

    samples_for_hits = samples or profile.get("samples") or []
    delimiter_hits = detect_delimiter_hits(samples_for_hits, cfg.get("delimiters") or [])

    def _build_response(
        *,
        strategy_id: str,
        mode: str,
        params: Dict[str, Any],
        candidates: Dict[str, Any] | None,
        delimiter_hits_val: int,
        profile_out: Dict[str, Any],
        notes: str,
        segments: Any = None,
        extra_note: str | None = None,
    ) -> Dict[str, Any]:
        """统一输出：限制为三类 mode，并补充数字 id 与描述元信息。"""
        mode_desc = {
            MODE_DIRECT: "分隔符直切，命中即用",
            MODE_SEMANTIC: "语义/句级分段，适合结构信号弱文本",
            MODE_HIERARCHICAL: "父子层级分段，基于标题/列表/长段落",
        }.get(mode, "")
        full_notes = notes + (f"|{extra_note}" if extra_note else "")
        return {
            "strategy_id": strategy_id,
            "mode": mode,
            "mode_id": MODE_ID_MAP.get(mode),
            "mode_desc": mode_desc,
            "params": params,
            "candidates": _round_scores(candidates, 3) if candidates else None,
            "delimiter_hits": delimiter_hits_val,
            "profile": profile_out,
            "notes": full_notes,
            "segments": segments,
        }

    # 硬路由：格式先验优先（表格/代码/幻灯片）。
    if fmt_norm in FORMAT_TABLE:
        params = estimate_params(profile, "table_batch", cfg)
        scores = {"table_batch": 1.0} if emit_candidates else None
        return _build_response(
            strategy_id="table_batch",
            mode=MODE_HIERARCHICAL,
            params=params,
            candidates=scores,
            delimiter_hits_val=delimiter_hits,
            profile_out=_round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3),
            notes="格式优先: 表格格式优先使用表格切片",
            extra_note="mapped_to_hierarchical",
        )

    if fmt_norm in FORMAT_CODE:
        params = estimate_params(profile, "code_log_block", cfg)
        scores = {"code_log_block": 1.0} if emit_candidates else None
        return _build_response(
            strategy_id="code_log_block",
            mode=MODE_HIERARCHICAL,
            params=params,
            candidates=scores,
            delimiter_hits_val=delimiter_hits,
            profile_out=_round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3),
            notes="格式优先: 代码/日志格式优先使用代码块切片",
            extra_note="mapped_to_hierarchical",
        )

    if fmt_norm in FORMAT_SLIDE:
        params = estimate_params(profile, "slide_block_textbox_merge", cfg)
        scores = {"slide_block_textbox_merge": 1.0} if emit_candidates else None
        return _build_response(
            strategy_id="slide_block_textbox_merge",
            mode=MODE_HIERARCHICAL,
            params=params,
            candidates=scores,
            delimiter_hits_val=delimiter_hits,
            profile_out=_round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3),
            notes="格式优先: 幻灯片优先合并文本框",
            extra_note="mapped_to_hierarchical",
        )

    def _score_profile(current_profile: Dict[str, Any], current_delim_hits: int) -> tuple[str, Dict[str, float], str | None]:
        """对单个 profile 打分，返回策略、分数字典（仅数值），以及可选备注。"""
        heading_ratio = float(current_profile.get("heading_ratio", 0.0))
        list_ratio = float(current_profile.get("list_ratio", 0.0))
        table_ratio = float(current_profile.get("table_ratio", 0.0))
        code_ratio = float(current_profile.get("code_ratio", 0.0))
        p90_len = float(current_profile.get("p90_para_len", 0.0))

        if cfg.get("enable") and current_delim_hits >= cfg.get("min_segments", 5):
            return "custom_delimiter_split", {"custom_delimiter_split": 1.0}, None
        if table_ratio > thresholds["t1_table"]:
            return "table_batch", {"table_batch": table_ratio}, "table_detected"
        if p90_len >= 800 or (p90_len >= 600 and heading_ratio > 0.01):
            return "heading_block_length_split", {"heading_block_length_split": 1.0}, "forced_long_paragraph_override"
        if code_ratio > thresholds["t2_code"]:
            return "code_log_block", {"code_log_block": code_ratio}, "code_detected"

        w_h = weights["w_h"]
        w_l = weights["w_l"]
        w_t = weights["w_t"]
        w_c = weights["w_c"]
        w_p = weights["w_p"]

        s_heading = (
            0.55
            + 1.5 * heading_ratio
            + 1.0 * list_ratio
            + 0.35 * (heading_ratio + list_ratio > 0.03)
            + 0.35 * (p90_len > 500)
            + 0.4 * (heading_ratio > 0.25 or list_ratio > 0.25)
        )
        s_sentence = (
            0.22
            - 0.9 * heading_ratio
            - 0.5 * list_ratio
            - 0.35 * table_ratio
            - 0.35 * code_ratio
            + w_p * min(1.0, p90_len / 400 if p90_len else 0.0)
            - 0.95 * max(0.0, (p90_len - 500) / 400)
        )
        s_table = w_t * table_ratio
        s_code = w_c * code_ratio

        score_map: Dict[str, float] = {
            "heading_block_length_split": s_heading,
            "sentence_split_sliding": s_sentence,
            "table_batch": s_table,
            "code_log_block": s_code,
        }
        # 将格式先验偏置加到分数上，满足“格式优先，探针微调”。
        if prior_bias:
            for k in score_map:
                score_map[k] += prior_bias.get(k, 0.0)
        best = max(score_map, key=score_map.get)
        return best, score_map, None

    # 多页样本：逐页打分累加，最后压缩到[-1,1]
    if samples and len(samples) > 1:
        page_profiles = [extract_signals_from_samples([s]) for s in samples if s]
        if page_profiles:
            # 若任一页明确命中表格阈值，直接优先表格策略，避免表头/标题页拉高 heading 分。
            table_hit_profiles = [p for p in page_profiles if float(p.get("table_ratio", 0.0)) > thresholds["t1_table"]]
            if table_hit_profiles:
                max_table_ratio = max(float(p.get("table_ratio", 0.0)) for p in table_hit_profiles)
                params = estimate_params(profile, "table_batch", cfg)
                scores_out = {"table_batch": _round_value(max_table_ratio, 3)} if emit_candidates else None
                return _build_response(
                    strategy_id="table_batch",
                    mode=MODE_HIERARCHICAL,
                    params=params,
                    candidates=scores_out,
                    delimiter_hits_val=delimiter_hits,
                    profile_out=_round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3),
                    notes="推荐的策略仅供参考(跨页累计打分)",
                    extra_note="table_detected|mapped_to_hierarchical",
                )

            agg_scores: Dict[str, float] = {}
            max_delim_hits = 0
            note_text: str | None = None
            for prof in page_profiles:
                page_delim_hits = detect_delimiter_hits(prof.get("samples") or [], cfg.get("delimiters") or [])
                max_delim_hits = max(max_delim_hits, page_delim_hits)
                _, page_scores, page_note = _score_profile(prof, page_delim_hits)
                if not note_text and page_note:
                    note_text = page_note
                for k, v in page_scores.items():
                    agg_scores[k] = agg_scores.get(k, 0.0) + v

            avg_scores = {k: v / len(page_profiles) for k, v in agg_scores.items()}
            compressed_scores = _compress_scores_to_unit(avg_scores)
            strategy = max(compressed_scores, key=compressed_scores.get)
            scores_out = _round_scores(compressed_scores, 3) if emit_candidates else None
            params = estimate_params(profile, strategy, cfg)
            mode_for_strategy = MODE_DIRECT if strategy == "custom_delimiter_split" else (
                MODE_HIERARCHICAL if strategy == "heading_block_length_split" else MODE_SEMANTIC
            )
            return _build_response(
                strategy_id=strategy,
                mode=mode_for_strategy,
                params=params,
                candidates=scores_out,
                delimiter_hits_val=max_delim_hits,
                profile_out=_round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3),
                notes="推荐的策略仅供参考(跨页累计打分)",
                extra_note=note_text,
            )

    # 单一或聚合样本：按原逻辑打分
    best_strategy, raw_scores, note_text = _score_profile(profile, delimiter_hits)
    scores = _round_scores(raw_scores, 3) if emit_candidates else None
    params = estimate_params(profile, best_strategy, cfg)
    mode_for_strategy = MODE_DIRECT if best_strategy == "custom_delimiter_split" else (
        MODE_HIERARCHICAL if best_strategy == "heading_block_length_split" else MODE_SEMANTIC
    )
    return _build_response(
        strategy_id=best_strategy,
        mode=mode_for_strategy,
        params=params,
        candidates=scores,
        delimiter_hits_val=delimiter_hits,
        profile_out=_round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3),
        notes="推荐的策略仅供参考",
        extra_note=note_text,
    )

