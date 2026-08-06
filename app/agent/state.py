from typing import Any, TypedDict


class TextToSQLGraphState(TypedDict, total=False):
    question: str
    request_id: str
    schema_context: str
    sql: str
    explanation: str
    assumptions: list[str]

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool

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
    generation_llm_ms: float
    review_llm_ms: float
    repair_llm_ms: float
    sql_execution_ms: float
