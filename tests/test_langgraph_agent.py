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


class HighRiskFakeLLMClient(OpenAICompatibleClient):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        return """
        {
          "sql": "SELECT status, RANK() OVER (ORDER BY COUNT(*) DESC) AS ranking FROM orders GROUP BY status",
          "explanation": "使用窗口函数对订单状态排名。",
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
        "assess_risk",
        "human_approval",
        "reject_query",
        "execute_sql",
        "repair_sql",
        "raise_execution_error",
    }.issubset(node_names)


@pytest.mark.anyio
async def test_high_risk_sql_pauses_then_resumes_after_approval() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
    )

    pending = await service.generate("按订单状态排名", request_id="approval-test")

    assert pending.status == "waiting_for_confirmation"
    assert pending.requires_confirmation is True
    assert pending.risk_level == "high"
    assert pending.rows == []

    completed = await service.resume("approval-test", approved=True)

    assert completed.status == "completed"
    assert completed.requires_confirmation is False
    assert completed.columns == ["status", "ranking"]


@pytest.mark.anyio
async def test_high_risk_sql_can_be_rejected() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
    )
    await service.generate("按订单状态排名", request_id="reject-test")

    rejected = await service.resume("reject-test", approved=False)

    assert rejected.status == "rejected"
    assert rejected.rows == []


@pytest.mark.anyio
async def test_sqlite_checkpoint_can_resume_after_service_restart(tmp_path) -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    checkpoint_path = str(tmp_path / "checkpoints.db")
    first_service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
        checkpoint_path=checkpoint_path,
    )
    pending = await first_service.generate("按订单状态排名", request_id="restart-test")
    await first_service.close()

    second_service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
        checkpoint_path=checkpoint_path,
    )
    completed = await second_service.resume("restart-test", approved=True)
    await second_service.close()

    assert pending.status == "waiting_for_confirmation"
    assert completed.status == "completed"


@pytest.mark.anyio
async def test_resume_rejects_unknown_request_id() -> None:
    service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        enable_sql_review=False,
    )

    with pytest.raises(ValueError, match="没有找到等待人工确认"):
        await service.resume("unknown-request", approved=True)


def test_runtime_factory_selects_langgraph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_runtime", "langgraph")

    service = create_text_to_sql_service()

    assert isinstance(service, LangGraphTextToSQLService)
