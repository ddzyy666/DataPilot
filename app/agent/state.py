from typing import Any, TypedDict


class TextToSQLGraphState(TypedDict, total=False):
    question: str
    effective_question: str
    request_id: str
    schema_context: str
    semantic_context: str
    matched_metrics: list[str]
    matched_dimensions: list[str]
    sql: str
    explanation: str
    assumptions: list[str]
    conversation_history: list[dict[str, str]]
    clarification_question: str | None
    clarification_options: list[str]
    clarification_count: int
    requires_clarification: bool

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    result_summary: str
    insights: list[str]
    chart: dict[str, Any] | None
    data_profile: dict[str, Any]
    result_analysis_error: str | None

    reviewed: bool
    review_passed: bool | None
    review_issues: list[str]
    review_checks: dict[str, bool]
    was_review_corrected: bool

    repair_attempts: int
    execution_error: str | None
    risk_level: str
    risk_reasons: list[str]
    requires_confirmation: bool
    confirmed: bool | None
    status: str

    schema_processing_ms: float
    clarification_llm_ms: float
    generation_llm_ms: float
    review_llm_ms: float
    repair_llm_ms: float
    result_analysis_llm_ms: float
    sql_execution_ms: float
