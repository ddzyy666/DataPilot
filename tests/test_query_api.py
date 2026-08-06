import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine

from app.audit.service import QueryAuditService
from app.llm.client import LLMResponseError
from app.main import app
from app.schemas.query import QueryResponse


class FakeTextToSQLService:
    async def generate(self, question: str) -> QueryResponse:
        return QueryResponse(
            question=question,
            sql="SELECT COUNT(*) AS order_count FROM orders",
            explanation="统计订单总数。",
            assumptions=[],
            schema_context="表: orders",
        )


@pytest.mark.anyio
async def test_query_endpoint_returns_generated_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    test_audit_service = QueryAuditService(create_engine("sqlite://"))
    monkeypatch.setattr(
        "app.api.routes.create_text_to_sql_service", lambda: FakeTextToSQLService()
    )
    monkeypatch.setattr("app.api.routes.audit_service", test_audit_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/query", json={"question": "一共有多少订单？"})

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT COUNT(*) AS order_count FROM orders"
    assert response.json()["timings"]["total_ms"] == 0
    assert response.json()["request_id"] == response.headers["X-Request-ID"]

    audit = test_audit_service.get_by_request_id(response.json()["request_id"])
    assert audit is not None
    assert audit.status == "success"
    assert audit.generated_sql == "SELECT COUNT(*) AS order_count FROM orders"


class FailingTextToSQLService:
    async def generate(self, question: str) -> QueryResponse:
        raise LLMResponseError("模型暂时不可用")


@pytest.mark.anyio
async def test_query_endpoint_audits_failed_request(monkeypatch: pytest.MonkeyPatch) -> None:
    test_audit_service = QueryAuditService(create_engine("sqlite://"))
    monkeypatch.setattr(
        "app.api.routes.create_text_to_sql_service", lambda: FailingTextToSQLService()
    )
    monkeypatch.setattr("app.api.routes.audit_service", test_audit_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/query", json={"question": "统计订单数量"})

    assert response.status_code == 502
    request_id = response.json()["detail"]["request_id"]
    assert request_id == response.headers["X-Request-ID"]

    audit = test_audit_service.get_by_request_id(request_id)
    assert audit is not None
    assert audit.status == "failed"
    assert audit.error_type == "LLMResponseError"


@pytest.mark.anyio
async def test_audit_endpoint_returns_record(monkeypatch: pytest.MonkeyPatch) -> None:
    test_audit_service = QueryAuditService(create_engine("sqlite://"))
    test_audit_service.record(
        test_audit_service.failure_log(
            request_id="test-request-id",
            question="统计订单数量",
            error=ValueError("测试错误"),
            total_time_ms=12.5,
        )
    )
    monkeypatch.setattr("app.api.routes.audit_service", test_audit_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/audit/test-request-id")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "测试错误"
