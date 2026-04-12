from __future__ import annotations


SHARED_PIPELINE_STAGES: tuple[str, ...] = (
    "prepare_input",
    "triage",
    "ocr",
    "tnved_assembly",
    "verification",
    "semantic_guard",
    "web_hint",
    "rerank",
    "ifcg",
    "its",
    "sigma_and_fees",
    "build_result",
)

