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
