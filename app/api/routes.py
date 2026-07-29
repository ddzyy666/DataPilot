from typing import Any

from fastapi import APIRouter

from app.db.base import engine
from app.db.metadata import inspect_schema

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
