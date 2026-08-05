from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit.models import AuditBase, QueryAuditLog
from app.core.config import settings

audit_engine = create_engine(settings.audit_database_url)


class QueryAuditService:
    def __init__(self, target_engine: Engine = audit_engine) -> None:
        self.target_engine = target_engine
        self._initialized = False
        self._initialization_lock = Lock()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._initialization_lock:
            if not self._initialized:
                AuditBase.metadata.create_all(self.target_engine)
                self._initialized = True

    def record(self, log: QueryAuditLog) -> bool:
        try:
            self._ensure_initialized()
            with Session(self.target_engine) as session:
                session.add(log)
                session.commit()
            return True
        except SQLAlchemyError:
            return False

    def get_by_request_id(self, request_id: str) -> QueryAuditLog | None:
        try:
            self._ensure_initialized()
            with Session(self.target_engine) as session:
                return session.scalar(
                    select(QueryAuditLog).where(QueryAuditLog.request_id == request_id)
                )
        except SQLAlchemyError:
            return None

    @staticmethod
    def success_log(
        *,
        request_id: str,
        question: str,
        generated_sql: str,
        row_count: int,
        was_repaired: bool,
        llm_time_ms: float,
        sql_time_ms: float,
        total_time_ms: float,
    ) -> QueryAuditLog:
        return QueryAuditLog(
            request_id=request_id,
            question=question,
            model=settings.llm_model,
            review_enabled=settings.query_enable_sql_review,
            generated_sql=generated_sql,
            status="success",
            row_count=row_count,
            was_repaired=was_repaired,
            llm_time_ms=llm_time_ms,
            sql_time_ms=sql_time_ms,
            total_time_ms=total_time_ms,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def failure_log(
        *,
        request_id: str,
        question: str,
        error: Exception,
        total_time_ms: float,
    ) -> QueryAuditLog:
        return QueryAuditLog(
            request_id=request_id,
            question=question,
            model=settings.llm_model,
            review_enabled=settings.query_enable_sql_review,
            generated_sql=None,
            status="failed",
            row_count=None,
            was_repaired=False,
            llm_time_ms=None,
            sql_time_ms=None,
            total_time_ms=total_time_ms,
            error_type=error.__class__.__name__,
            error_message=str(error),
            created_at=datetime.now(UTC),
        )
