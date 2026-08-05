from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AuditBase(DeclarativeBase):
    pass


class QueryAuditLog(AuditBase):
    __tablename__ = "query_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(200))
    review_enabled: Mapped[bool] = mapped_column(Boolean)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_repaired: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    sql_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_time_ms: Mapped[float] = mapped_column(Float)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
