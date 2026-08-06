from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from app.agent.runtime import create_text_to_sql_service
from app.audit.service import QueryAuditService
from app.core.config import settings
from app.db.base import engine
from app.db.metadata import inspect_schema
from app.llm.client import LLMConfigurationError, LLMResponseError
from app.schemas.audit import AuditRecordResponse
from app.schemas.query import QueryConfirmationRequest, QueryRequest, QueryResponse
from app.services.sql_executor import SQLExecutionError, SQLQueryTimeoutError
from app.services.sql_permissions import SQLPermissionError, SQLPermissionPolicy
from app.services.text_to_sql import SQLSafetyError

router = APIRouter(prefix="/api/v1")
audit_service = QueryAuditService()


@router.get(
    "/schema",
    tags=["数据库"],
    summary="读取数据库结构",
    description="返回数据库方言、数据表、字段、主键及外键关联关系。",
    response_description="数据库结构读取成功",
)
async def get_schema() -> dict[str, Any]:
    permission_policy = SQLPermissionPolicy.from_strings(
        allowed_tables=settings.query_allowed_tables,
        denied_columns=settings.query_denied_columns,
        dialect=engine.dialect.name,
    )
    return permission_policy.filter_schema(inspect_schema(engine))


@router.get(
    "/audit/{request_id}",
    tags=["审计"],
    summary="查询请求审计记录",
    response_model=AuditRecordResponse,
)
async def get_audit_record(request_id: str) -> AuditRecordResponse:
    record = audit_service.get_by_request_id(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="没有找到对应的审计记录。")
    return AuditRecordResponse.model_validate(record)


@router.post(
    "/query",
    tags=["数据库"],
    summary="生成并执行 SQL",
    description="根据中文数据分析问题生成安全的只读 SQL，执行查询并返回结构化数据。",
    response_description="SQL 生成及查询执行成功",
)
async def generate_sql(request: QueryRequest, response: Response) -> QueryResponse:
    request_id = str(uuid4())
    response.headers["X-Request-ID"] = request_id
    started_at = perf_counter()
    service = create_text_to_sql_service()
    try:
        result = await service.generate(request.question, request_id=request_id)
    except (
        LLMConfigurationError,
        LLMResponseError,
        SQLExecutionError,
        SQLQueryTimeoutError,
        SQLPermissionError,
        SQLSafetyError,
        ValueError,
        TypeError,
    ) as exc:
        total_time_ms = round((perf_counter() - started_at) * 1000, 2)
        audit_service.record(
            audit_service.failure_log(
                request_id=request_id,
                question=request.question,
                error=exc,
                total_time_ms=total_time_ms,
            )
        )
        if isinstance(exc, LLMConfigurationError):
            status_code = 503
        elif isinstance(exc, LLMResponseError):
            status_code = 502
        else:
            status_code = 422
        raise HTTPException(
            status_code=status_code,
            detail={"request_id": request_id, "message": str(exc)},
            headers={"X-Request-ID": request_id},
        ) from exc

    result = result.model_copy(update={"request_id": request_id})
    _record_result(result)
    return result


@router.post(
    "/query/{request_id}/confirm",
    tags=["数据库"],
    summary="确认或拒绝高风险 SQL",
    description="恢复被 checkpoint 暂停的查询，可批准、拒绝或提交修改后的只读 SQL。",
)
async def confirm_sql(
    request_id: str,
    request: QueryConfirmationRequest,
    response: Response,
) -> QueryResponse:
    response.headers["X-Request-ID"] = request_id
    service = create_text_to_sql_service()
    resume = getattr(service, "resume", None)
    if resume is None:
        raise HTTPException(status_code=409, detail="当前运行模式不支持人工确认。")
    try:
        result = await resume(
            request_id,
            approved=request.approved,
            edited_sql=request.edited_sql,
        )
    except (
        LLMConfigurationError,
        LLMResponseError,
        SQLExecutionError,
        SQLQueryTimeoutError,
        SQLPermissionError,
        SQLSafetyError,
        ValueError,
        TypeError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={"request_id": request_id, "message": str(exc)},
            headers={"X-Request-ID": request_id},
        ) from exc
    _record_result(result)
    return result


def _record_result(result: QueryResponse) -> None:
    audit_service.record(
        audit_service.success_log(
            request_id=result.request_id,
            question=result.question,
            generated_sql=result.sql,
            row_count=result.row_count,
            was_repaired=result.was_repaired,
            llm_time_ms=result.timings.llm_total_ms,
            sql_time_ms=result.timings.sql_execution_ms,
            total_time_ms=result.timings.total_ms,
            status=(
                "success" if result.status == "completed" else result.status
            ),
        )
    )
