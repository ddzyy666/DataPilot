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


class StageTimings(BaseModel):
    schema_processing_ms: float = Field(default=0, description="读取并格式化数据库结构耗时")
    llm_total_ms: float = Field(default=0, description="所有模型调用的累计耗时")
    sql_execution_ms: float = Field(default=0, description="所有 SQL 执行的累计耗时")
    other_processing_ms: float = Field(default=0, description="解析、校验等其他处理耗时")
    total_ms: float = Field(default=0, description="完整请求处理耗时")


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
    was_repaired: bool = Field(default=False, description="SQL 是否经过模型自动修复")
    repair_attempts: int = Field(default=0, description="SQL 自动修复次数")
    reviewed: bool = Field(default=False, description="是否执行了 SQL 语义审核")
    review_passed: bool | None = Field(default=None, description="首次 SQL 是否通过语义审核")
    review_issues: list[str] = Field(default_factory=list, description="语义审核发现的问题")
    review_checks: dict[str, bool] = Field(default_factory=dict, description="语义审核检查项")
    was_review_corrected: bool = Field(default=False, description="SQL 是否被审核器改写")
    timings: StageTimings = Field(default_factory=StageTimings, description="各处理阶段耗时")
