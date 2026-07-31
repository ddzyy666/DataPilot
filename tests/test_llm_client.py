import httpx
import pytest

from app.llm.client import LLMResponseError, OpenAICompatibleClient


@pytest.mark.anyio
async def test_llm_client_wraps_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(api_key="test-key")

    with pytest.raises(LLMResponseError, match="请求超时"):
        await client.complete([{"role": "user", "content": "hello"}])


@pytest.mark.anyio
async def test_llm_client_wraps_remote_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.RemoteProtocolError("server disconnected")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(api_key="test-key")

    with pytest.raises(LLMResponseError, match="连接被中途断开"):
        await client.complete([{"role": "user", "content": "hello"}])


@pytest.mark.anyio
async def test_llm_client_sends_enable_thinking_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload: dict[str, object] = {}

    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        captured_payload.update(kwargs["json"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"sql\":\"SELECT 1\"}"}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(api_key="test-key", enable_thinking=False)

    await client.complete([{"role": "user", "content": "hello"}])

    assert captured_payload["enable_thinking"] is False
