from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.base import engine
from app.db.metadata import inspect_schema
from app.llm.client import LLMConfigurationError, LLMResponseError
from app.schemas.query import QueryRequest, QueryResponse
from app.services.text_to_sql import SQLSafetyError, TextToSQLService

router = APIRouter(prefix="/api/v1")


@router.get(
    "/schema",
    tags=["数据库"],
    summary="读取数据库结构",
    description="返回数据库方言、数据表、字段、主键及外键关联关系。",
    response_description="数据库结构读取成功",
)
async def get_schema() -> dict[str, Any]:
    return inspect_schema(engine)


@router.post(
    "/query",
    tags=["数据库"],
    summary="生成 SQL",
    description="根据中文数据分析问题和数据库结构生成安全的只读 SQL，当前阶段只生成 SQL，不执行查询。",
    response_description="SQL 生成成功",
)
async def generate_sql(request: QueryRequest) -> QueryResponse:
    service = TextToSQLService()
    try:
        return await service.generate(request.question)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (SQLSafetyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
