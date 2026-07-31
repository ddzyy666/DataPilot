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
    schema_inspection_ms: float = Field(default=0, description="读取数据库结构耗时")
    schema_formatting_ms: float = Field(default=0, description="格式化 Schema 上下文耗时")
    prompt_building_ms: float = Field(default=0, description="构造模型 Prompt 耗时")
    llm_call_ms: float = Field(default=0, description="调用模型服务耗时")
    response_parsing_ms: float = Field(default=0, description="解析模型响应耗时")
    sql_validation_ms: float = Field(default=0, description="SQL 安全校验耗时")
    sql_execution_ms: float = Field(default=0, description="执行 SQL 耗时")
    repair_prompt_building_ms: float = Field(default=0, description="构造 SQL 修复 Prompt 耗时")
    repair_llm_call_ms: float = Field(default=0, description="调用模型修复 SQL 耗时")
    repair_response_parsing_ms: float = Field(default=0, description="解析修复响应耗时")
    repair_sql_validation_ms: float = Field(default=0, description="修复后 SQL 安全校验耗时")
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
    timings: StageTimings = Field(default_factory=StageTimings, description="各处理阶段耗时")
