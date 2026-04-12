from __future__ import annotations

from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from ..core.exceptions import (
    AiConnectorError,
    AiTimeoutError,
    AuthError,
    NetworkError,
    ProviderError,
    ProviderTemporaryError,
    RateLimitError,
    RetryableAiError,
)
from ..core.types import AiResult
from .base import BaseProvider

_RETRYABLE_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, RetryableAiError):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUSES
    return False


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        timeout: float = 90.0,
        max_retries: int = 3,
    ):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def text(self, model: str, prompt: str, **kwargs: Any) -> AiResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        payload.update(kwargs)
        data, attempts = await self._post("/chat/completions", payload, model=model)

        content = self._extract_text(data)
        usage = data.get("usage", {})
        return AiResult(
            text=content,
            provider=self.name,
            model=model,
            usage=usage,
            attempts=attempts,
            raw=data,
        )

    async def image(self, model: str, prompt: str, **kwargs: Any) -> AiResult:
        payload = {
            "model": model,
            "prompt": prompt,
            "size": kwargs.pop("size", "1024x1024"),
        }
        payload.update(kwargs)
        data, attempts = await self._post("/images/generations", payload, model=model)

        image_url = None
        images = data.get("data", [])
        if images and isinstance(images, list):
            image_url = images[0].get("url") or images[0].get("b64_json")

        return AiResult(
            image_url=image_url,
            provider=self.name,
            model=model,
            attempts=attempts,
            raw=data,
        )

    async def _post(self, endpoint: str, payload: dict[str, Any], *, model: str) -> tuple[dict[str, Any], int]:
        last_attempt = 1
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max(1, self.max_retries)),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception(_should_retry),
            reraise=True,
        ):
            with attempt:
                last_attempt = attempt.retry_state.attempt_number
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.post(
                            f"{self.base_url}{endpoint}",
                            headers=self._headers(),
                            json=payload,
                        )
                        response.raise_for_status()
                        return response.json(), last_attempt
                except httpx.HTTPStatusError as exc:
                    raise self._map_http_error(exc, model=model) from exc
                except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
                    raise AiTimeoutError(
                        f"Request timeout for provider '{self.name}'",
                        provider=self.name,
                        model=model,
                    ) from exc
                except httpx.ConnectError as exc:
                    raise NetworkError(
                        f"Network connection failed for provider '{self.name}'",
                        provider=self.name,
                        model=model,
                    ) from exc

        raise RuntimeError("Unexpected retry flow termination")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str | None:
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
            if parts:
                return "".join(parts)
        return None

    def _map_http_error(self, exc: httpx.HTTPStatusError, *, model: str) -> AiConnectorError:
        status = exc.response.status_code
        if status in (401, 403):
            return AuthError(
                f"Authentication/authorization error from provider '{self.name}'",
                provider=self.name,
                model=model,
                status_code=status,
            )
        if status == 429:
            return RateLimitError(
                f"Rate limit reached for provider '{self.name}'",
                provider=self.name,
                model=model,
                status_code=status,
            )
        if status in (408, 409, 425, 500, 502, 503, 504):
            return ProviderTemporaryError(
                f"Temporary provider error from '{self.name}'",
                provider=self.name,
                model=model,
                status_code=status,
            )
        return ProviderError(
            f"Provider '{self.name}' returned HTTP {status}",
            provider=self.name,
            model=model,
            status_code=status,
        )
