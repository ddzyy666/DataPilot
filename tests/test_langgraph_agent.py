import pytest
from sqlalchemy import create_engine

from app.agent.graph import LangGraphTextToSQLService
from app.agent.runtime import create_text_to_sql_service
from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.llm.client import OpenAICompatibleClient


class GraphFakeLLMClient(OpenAICompatibleClient):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        return """
        {
          "sql": "SELECT status, COUNT(*) AS order_count FROM orders GROUP BY status",
          "explanation": "按订单状态统计。",
          "assumptions": []
        }
        """


class GraphRepairFakeLLMClient(OpenAICompatibleClient):
    def __init__(self) -> None:
        self.call_count = 0

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return """
            {
              "sql": "SELECT missing_column FROM orders",
              "explanation": "使用了错误字段。",
              "assumptions": []
            }
            """
        return """
        {
          "sql": "SELECT status FROM orders",
          "explanation": "根据数据库错误修复字段。",
          "assumptions": []
        }
        """


@pytest.mark.anyio
async def test_langgraph_wraps_existing_services_and_returns_query_response() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=GraphFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
    )

    response = await service.generate("统计不同订单状态的订单数量")

    assert response.sql.startswith("SELECT status")
    assert response.columns == ["status", "order_count"]
    assert response.reviewed is False
    assert response.timings.total_ms >= response.timings.sql_execution_ms


@pytest.mark.anyio
async def test_langgraph_routes_execution_failure_to_repair_node() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    fake_client = GraphRepairFakeLLMClient()
    service = LangGraphTextToSQLService(
        llm_client=fake_client,
        target_engine=test_engine,
        enable_sql_review=False,
    )

    response = await service.generate("查询订单状态")

    assert fake_client.call_count == 2
    assert response.sql == "SELECT status FROM orders"
    assert response.was_repaired is True
    assert response.repair_attempts == 1


def test_langgraph_contains_expected_business_nodes() -> None:
    service = LangGraphTextToSQLService(
        llm_client=GraphFakeLLMClient(),
        enable_sql_review=False,
    )

    node_names = set(service.graph.get_graph().nodes)

    assert {
        "load_schema",
        "generate_sql",
        "review_sql",
        "execute_sql",
        "repair_sql",
        "raise_execution_error",
    }.issubset(node_names)


def test_runtime_factory_selects_langgraph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_runtime", "langgraph")

    service = create_text_to_sql_service()

    assert isinstance(service, LangGraphTextToSQLService)
