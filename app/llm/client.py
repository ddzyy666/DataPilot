import asyncio
from typing import Any

import httpx

from app.core.config import settings


class LLMConfigurationError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str = settings.llm_base_url,
        api_key: str | None = settings.llm_api_key,
        model: str = settings.llm_model,
        timeout_seconds: float = settings.llm_timeout_seconds,
        max_tokens: int = settings.llm_max_tokens,
        use_response_format: bool = settings.llm_use_response_format,
        trust_env: bool = settings.llm_trust_env,
        enable_thinking: bool | None = settings.llm_enable_thinking,
        max_retries: int = settings.llm_max_retries,
        retry_delay_seconds: float = settings.llm_retry_delay_seconds,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.use_response_format = use_response_format
        self.trust_env = trust_env
        self.enable_thinking = enable_thinking
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise LLMConfigurationError("请先在 .env 中配置 LLM_API_KEY。")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if self.use_response_format:
            payload["response_format"] = {"type": "json_object"}
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "DataPilot/0.1.0",
        }

        retryable_status_codes = {429, 502, 503, 504}
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            trust_env=self.trust_env,
        ) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_delay_seconds)
                        continue
                    if isinstance(exc, httpx.TimeoutException):
                        raise LLMResponseError(
                            "模型服务请求超时，已达到最大重试次数。"
                        ) from exc
                    raise LLMResponseError(
                        "模型服务连接被中途断开，已达到最大重试次数。"
                    ) from exc
                except httpx.RequestError as exc:
                    raise LLMResponseError(f"模型服务请求失败: {exc.__class__.__name__}") from exc

                if response.status_code in retryable_status_codes and attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds)
                    continue
                if response.status_code >= 400:
                    raise LLMResponseError(f"模型服务返回异常: HTTP {response.status_code}")

                data = response.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise LLMResponseError("模型响应格式不符合 OpenAI-compatible 规范。") from exc

        raise LLMResponseError("模型服务请求失败。")
