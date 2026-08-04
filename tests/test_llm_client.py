import httpx
import pytest

from app.llm.client import LLMResponseError, OpenAICompatibleClient


@pytest.mark.anyio
async def test_llm_client_wraps_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(api_key="test-key", max_retries=0)

    with pytest.raises(LLMResponseError, match="请求超时"):
        await client.complete([{"role": "user", "content": "hello"}])


@pytest.mark.anyio
async def test_llm_client_wraps_remote_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.RemoteProtocolError("server disconnected")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(api_key="test-key", max_retries=0)

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


@pytest.mark.anyio
async def test_llm_client_retries_timeout_and_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"sql\":\"SELECT 1\"}"}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(
        api_key="test-key",
        max_retries=1,
        retry_delay_seconds=0,
    )

    content = await client.complete([{"role": "user", "content": "hello"}])

    assert call_count == 2
    assert "SELECT 1" in content


@pytest.mark.anyio
async def test_llm_client_retries_retryable_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        httpx.Response(503),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"sql\":\"SELECT 1\"}"}}]},
        ),
    ]

    async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        return responses.pop(0)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenAICompatibleClient(
        api_key="test-key",
        max_retries=1,
        retry_delay_seconds=0,
    )

    await client.complete([{"role": "user", "content": "hello"}])

    assert responses == []
