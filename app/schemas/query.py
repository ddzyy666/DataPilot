from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="用户的中文数据分析问题",
        examples=["最近一年每个地区的销售额是多少？"],
    )


class QueryResponse(BaseModel):
    question: str = Field(description="原始用户问题")
    sql: str = Field(description="生成的只读 SQL")
    explanation: str = Field(description="SQL 思路说明")
    assumptions: list[str] = Field(default_factory=list, description="生成 SQL 时使用的假设")
    schema_context: str = Field(description="本次生成 SQL 使用的数据库结构上下文")
    columns: list[str] = Field(default_factory=list, description="查询结果的列名")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="查询结果数据")
    row_count: int = Field(default=0, description="本次实际返回的数据行数")
    truncated: bool = Field(default=False, description="结果是否因行数限制被截断")
    execution_time_ms: float = Field(default=0, description="SQL 执行耗时（毫秒）")
