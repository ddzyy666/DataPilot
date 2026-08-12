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


class ClarificationFakeLLMClient(OpenAICompatibleClient):
    def __init__(self, always_incomplete: bool = False) -> None:
        self.analysis_count = 0
        self.always_incomplete = always_incomplete

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if "问题完整性检查器" in messages[0]["content"]:
            self.analysis_count += 1
            if self.analysis_count == 1 or self.always_incomplete:
                return """
                {
                  "is_complete": false,
                  "clarification_question": "销量按销售数量还是销售金额计算？",
                  "missing_information": ["销量口径"],
                  "options": ["销售数量", "销售金额"]
                }
                """
            return """
            {
              "is_complete": true,
              "clarification_question": null,
              "missing_information": [],
              "options": []
            }
            """
        return """
        {
          "sql": "SELECT COUNT(*) AS order_count FROM orders",
          "explanation": "统计订单数量。",
          "assumptions": []
        }
        """


class ResultAnalysisFakeLLMClient(OpenAICompatibleClient):
    def __init__(self, invalid_analysis: bool = False) -> None:
        self.invalid_analysis = invalid_analysis

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if "查询结果解读器" in messages[0]["content"]:
            if self.invalid_analysis:
                return "not-json"
            return """
            {
              "summary": "当前共有0条订单记录。",
              "insights": ["订单数量为0"]
            }
            """
        return """
        {
          "sql": "SELECT COUNT(*) AS order_count FROM orders",
          "explanation": "统计订单总数。",
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
        enable_clarification=False,
        enable_result_analysis=False,
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
        enable_clarification=False,
        enable_result_analysis=False,
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
        enable_clarification=False,
        enable_result_analysis=False,
    )

    node_names = set(service.graph.get_graph().nodes)

    assert {
        "load_schema",
        "resolve_semantics",
        "analyze_question",
        "clarify_question",
        "generate_sql",
        "review_sql",
        "assess_risk",
        "human_approval",
        "reject_query",
        "execute_sql",
        "analyze_result",
        "repair_sql",
        "raise_execution_error",
    }.issubset(node_names)


@pytest.mark.anyio
async def test_langgraph_exposes_matched_business_semantics() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=GraphFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=False,
        enable_result_analysis=False,
    )

    response = await service.generate("按订单状态统计订单数量")

    assert response.matched_metrics == ["order_count"]
    assert response.matched_dimensions == ["order_status"]
    assert "订单数量" in response.semantic_context


@pytest.mark.anyio
async def test_high_risk_sql_pauses_then_resumes_after_approval() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=False,
        enable_result_analysis=False,
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
        enable_clarification=False,
        enable_result_analysis=False,
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
        enable_clarification=False,
        enable_result_analysis=False,
        checkpoint_path=checkpoint_path,
    )
    pending = await first_service.generate("按订单状态排名", request_id="restart-test")
    await first_service.close()

    second_service = LangGraphTextToSQLService(
        llm_client=HighRiskFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=False,
        enable_result_analysis=False,
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
        enable_clarification=False,
        enable_result_analysis=False,
    )

    with pytest.raises(ValueError, match="没有找到等待人工确认"):
        await service.resume("unknown-request", approved=True)


@pytest.mark.anyio
async def test_ambiguous_question_pauses_and_continues_after_clarification() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    fake_client = ClarificationFakeLLMClient()
    service = LangGraphTextToSQLService(
        llm_client=fake_client,
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=True,
        enable_result_analysis=False,
    )

    pending = await service.generate("销量最好的产品", request_id="clarify-test")

    assert pending.status == "waiting_for_clarification"
    assert pending.requires_clarification is True
    assert pending.clarification_options == ["销售数量", "销售金额"]
    assert pending.sql == ""

    completed = await service.clarify("clarify-test", answer="按照销售金额")

    assert completed.status == "completed"
    assert completed.requires_clarification is False
    assert completed.clarification_count == 1
    assert completed.sql.startswith("SELECT COUNT")
    assert fake_client.analysis_count == 2


@pytest.mark.anyio
async def test_clarification_stops_after_configured_maximum_rounds() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=ClarificationFakeLLMClient(always_incomplete=True),
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=True,
        enable_result_analysis=False,
        max_clarification_rounds=1,
    )
    await service.generate("销量最好的产品", request_id="max-round-test")

    completed = await service.clarify("max-round-test", answer="销售金额")

    assert completed.status == "completed"
    assert completed.clarification_count == 1


@pytest.mark.anyio
async def test_clarification_checkpoint_survives_service_restart(tmp_path) -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    checkpoint_path = str(tmp_path / "clarification-checkpoints.db")
    fake_client = ClarificationFakeLLMClient()
    first_service = LangGraphTextToSQLService(
        llm_client=fake_client,
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=True,
        enable_result_analysis=False,
        checkpoint_path=checkpoint_path,
    )
    pending = await first_service.generate("销量最好的产品", request_id="clarify-restart")
    await first_service.close()

    second_service = LangGraphTextToSQLService(
        llm_client=fake_client,
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=True,
        enable_result_analysis=False,
        checkpoint_path=checkpoint_path,
    )
    completed = await second_service.clarify(
        "clarify-restart", answer="按照销售金额"
    )
    await second_service.close()

    assert pending.status == "waiting_for_clarification"
    assert completed.status == "completed"


@pytest.mark.anyio
async def test_result_analysis_returns_summary_profile_and_chart() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=ResultAnalysisFakeLLMClient(),
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=False,
        enable_result_analysis=True,
    )

    response = await service.generate("一共有多少订单？")

    assert response.result_summary == "当前共有0条订单记录。"
    assert response.insights == ["订单数量为0"]
    assert response.data_profile["numeric_summary"]["order_count"]["sum"] == 0
    assert response.chart is not None
    assert response.chart.type == "metric"
    assert response.result_analysis_error is None


@pytest.mark.anyio
async def test_result_analysis_failure_does_not_discard_sql_result() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    service = LangGraphTextToSQLService(
        llm_client=ResultAnalysisFakeLLMClient(invalid_analysis=True),
        target_engine=test_engine,
        enable_sql_review=False,
        enable_clarification=False,
        enable_result_analysis=True,
    )

    response = await service.generate("一共有多少订单？")

    assert response.status == "completed"
    assert response.rows == [{"order_count": 0}]
    assert response.result_summary == "查询执行成功，共返回 1 行数据。"
    assert response.result_analysis_error == "结果分析器没有返回合法 JSON。"


def test_runtime_factory_selects_langgraph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_runtime", "langgraph")

    service = create_text_to_sql_service()

    assert isinstance(service, LangGraphTextToSQLService)
