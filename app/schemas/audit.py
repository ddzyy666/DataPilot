from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditRecordResponse(BaseModel):
    request_id: str
    question: str
    model: str
    review_enabled: bool
    generated_sql: str | None
    status: str
    row_count: int | None
    was_repaired: bool
    llm_time_ms: float | None
    sql_time_ms: float | None
    total_time_ms: float
    error_type: str | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
