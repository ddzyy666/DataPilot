import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_docs_include_chinese_translation_layer() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/docs")

    assert response.status_code == 200
    assert "DataPilot API 文档" in response.text
    assert '["Execute", "执行"]' in response.text
