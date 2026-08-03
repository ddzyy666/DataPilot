import pytest
from sqlalchemy import create_engine

from app.db import models  # noqa: F401
from app.db.base import Base
from app.llm.client import OpenAICompatibleClient
from app.services.text_to_sql import SQLSafetyError, TextToSQLService


class FakeLLMClient(OpenAICompatibleClient):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        if "SQL 语义审核器" in messages[0]["content"]:
            return """
            {
              "is_correct": true,
              "issues": [],
              "corrected_sql": null,
              "explanation": "SQL 与用户问题一致。"
            }
            """
        return """
        {
          "sql": "SELECT status, COUNT(*) AS order_count FROM orders GROUP BY status",
          "explanation": "按订单状态分组统计订单数量。",
          "assumptions": []
        }
        """


class RepairingFakeLLMClient(OpenAICompatibleClient):
    def __init__(self) -> None:
        self.call_count = 0
        self.messages: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.call_count += 1
        self.messages.append(messages)
        if "SQL 语义审核器" in messages[0]["content"]:
            return """
            {
              "is_correct": true,
              "issues": [],
              "corrected_sql": null,
              "explanation": "审核通过。"
            }
            """
        if self.call_count == 1:
            return """
            {
              "sql": "SELECT missing_column FROM orders",
              "explanation": "第一次生成了错误字段。",
              "assumptions": []
            }
            """
        return """
        {
          "sql": "SELECT status FROM orders",
          "explanation": "根据执行错误修复了字段。",
          "assumptions": []
        }
        """


class ReviewingFakeLLMClient(OpenAICompatibleClient):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        if "SQL 语义审核器" in messages[0]["content"]:
            return """
            {
              "is_correct": false,
              "issues": ["用户要求统计数量，但候选 SQL 没有使用 COUNT。"],
              "corrected_sql": "SELECT COUNT(*) AS order_count FROM orders",
              "explanation": "改为使用 COUNT 统计订单数量。"
            }
            """
        return """
        {
          "sql": "SELECT status FROM orders",
          "explanation": "错误地查询了订单状态。",
          "assumptions": []
        }
        """


@pytest.mark.anyio
async def test_generate_sql_returns_readonly_query() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = TextToSQLService(llm_client=FakeLLMClient(), target_engine=test_engine)

    response = await service.generate("不同订单状态分别有多少订单？")

    assert response.question == "不同订单状态分别有多少订单？"
    assert response.sql.startswith("SELECT")
    assert "表: orders" in response.schema_context
    assert response.columns == ["status", "order_count"]
    assert response.rows == []
    assert response.row_count == 0
    assert response.timings.total_ms >= response.timings.sql_execution_ms
    assert response.timings.llm_total_ms >= 0
    assert response.timings.other_processing_ms >= 0
    assert response.reviewed is True
    assert response.review_passed is True
    assert response.was_review_corrected is False


@pytest.mark.anyio
async def test_reviewer_corrects_semantically_wrong_sql_before_execution() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = TextToSQLService(llm_client=ReviewingFakeLLMClient(), target_engine=test_engine)

    response = await service.generate("统计订单数量")

    assert response.sql == "SELECT COUNT(*) AS order_count FROM orders"
    assert response.reviewed is True
    assert response.review_passed is False
    assert response.was_review_corrected is True
    assert response.review_issues == ["用户要求统计数量，但候选 SQL 没有使用 COUNT。"]
    assert response.rows == [{"order_count": 0}]
    assert response.timings.llm_total_ms >= 0


@pytest.mark.anyio
async def test_generate_repairs_failed_sql_and_executes_again() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    fake_client = RepairingFakeLLMClient()
    service = TextToSQLService(llm_client=fake_client, target_engine=test_engine)

    response = await service.generate("查询订单状态")

    assert fake_client.call_count == 3
    assert "missing_column" in fake_client.messages[2][1]["content"]
    assert "数据库执行错误" in fake_client.messages[2][1]["content"]
    assert response.sql == "SELECT status FROM orders"
    assert response.was_repaired is True
    assert response.repair_attempts == 1
    assert response.timings.llm_total_ms >= 0


def test_validate_readonly_sql_rejects_mutating_statement() -> None:
    service = TextToSQLService(llm_client=FakeLLMClient())

    with pytest.raises(SQLSafetyError):
        service._validate_readonly_sql("DELETE FROM orders")


def test_parse_model_json_accepts_json_inside_markdown() -> None:
    service = TextToSQLService(llm_client=FakeLLMClient())

    payload = service._parse_model_json(
        """
        ```json
        {"sql": "SELECT COUNT(*) FROM orders", "explanation": "统计订单数"}
        ```
        """
    )

    assert payload["sql"] == "SELECT COUNT(*) FROM orders"
