import pytest
from httpx import ASGITransport, AsyncClient

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
    monkeypatch.setattr("app.api.routes.TextToSQLService", lambda: FakeTextToSQLService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/query", json={"question": "一共有多少订单？"})

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT COUNT(*) AS order_count FROM orders"
