import pytest

from slicer_service import recommendation as rec


def test_custom_delimiter_gating():
    samples = ["a---b---c---d---e---f"]
    profile = rec.extract_signals_from_samples(samples)
    cfg = {"enable": True, "delimiters": ["---"], "min_segments": 2}
    result = rec.recommend_strategy(profile, samples=samples, custom_cfg=cfg)
    assert result["strategy_id"] == "custom_delimiter_split"
    assert result["delimiter_hits"] >= 2


def test_code_rule_triggers_code_strategy():
    samples = ["def foo():\n    pass\nclass Bar:\n    ..."]
    profile = rec.extract_signals_from_samples(samples)
    result = rec.recommend_strategy(profile, samples=samples)
    assert result["strategy_id"] in {"code_log_block", "heading_block_length_split", "sentence_split_sliding"}
    # when code density high enough, expect code_log_block
    if profile["code_ratio"] > rec.DEFAULT_THRESHOLDS["t2_code"]:
        assert result["strategy_id"] == "code_log_block"


@pytest.mark.parametrize(
    "label,samples,expected",
    [
        (
            "markdown_headings",
            [
                """# Title\n\n## Section 1\n- item 1\n- item 2\n\nParagraph with context.""",
                """1. Overview\n1.1 Details\n- sub item\nAnother line.""",
            ],
            {"heading_block_length_split", "sentence_split_sliding"},
        ),
        (
            "table_like_doc",
            [
                """Name,Role,Dept,Location\nAlice,Engineer,Platform,NYC\nBob,PM,Product,SF\nCarol,Designer,Design,LDN""",
                "Summary paragraph about the table above.",
            ],
            {"table_batch"},
        ),
        (
            "ppt_bullets",
            [
                """Slide 1: Project Update\n- Milestone A done\n- Milestone B in progress\n- Risks minimal""",
                """Slide 2: Metrics\n- DAU: 120k\n- MAU: 1.2M\n- Churn: 3%""",
            ],
            {"heading_block_length_split", "sentence_split_sliding"},
        ),
        (
            "pdf_extracted_text",
            [
                """This is a long paragraph extracted from a PDF. It contains multiple sentences that flow together without headings. """
                "The goal is to simulate contiguous narrative text across pages without structural markers.",
                """Another paragraph continues the discussion and remains largely free of headings, lists, or tables.""",
            ],
            {"sentence_split_sliding"},
        ),
        (
            "html_report",
            [
                """1. Introduction\n<div>Some content</div>\n2. Results\n<table>col1,col2,col3,col4</table>\nFooter""",
            ],
            {"heading_block_length_split", "table_batch", "sentence_split_sliding"},
        ),
        (
            "txt_notes",
            [
                """Notes from meeting:\nWe discussed roadmap items and action points. Follow-up is required next week.""",
                """Additional context lines with plain text and no obvious structure beyond simple sentences.""",
            ],
            {"sentence_split_sliding", "heading_block_length_split"},
        ),
        (
            "long_table_with_narrative",
            [
                """Quarter,Revenue,Cost,Profit,Margin\nQ1,120,80,40,33%\nQ2,150,90,60,40%\nQ3,170,110,60,35%\nQ4,200,140,60,30%""",
                "The report describes financial performance across quarters with supporting narrative text following the CSV-like table above.",
            ],
            {"table_batch", "heading_block_length_split"},
        ),
        (
            "code_and_log_with_table",
            [
                """INFO 2024-01-01 pipeline started\nINFO loading config\nWARN retrying request\nDEBUG payload={"id":1}\n""",
                """endpoint,status,latency_ms\n/api/v1/foo,200,123\n/api/v1/bar,500,892\n/api/v1/baz,200,210""",
                """def handler(event):\n    process(event)\n    return True""",
            ],
            {"code_log_block", "table_batch", "sentence_split_sliding"},
        ),
    ],
)
def test_recommendation_for_various_samples(label, samples, expected):
    """Validate strategy choices across common document shapes (md/doc/ppt/pdf/html/txt)."""

    profile = rec.extract_signals_from_samples(samples)
    result = rec.recommend_strategy(profile, samples=samples)
    assert result["strategy_id"] in expected, f"{label} -> {result['strategy_id']} not in {expected}"
    # ensure params returned to avoid regressions
    assert "params" in result and isinstance(result["params"], dict)
