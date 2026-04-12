from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

import yaml

from .cheap_gpt import CheapGPTProvider
from .core.exceptions import (
    NoFallbackConfiguredError,
    ProfileNotFoundError,
    ProviderNotFoundError,
    RetryableAiError,
)
from .core.types import AiResult, ProfileName
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider
from .providers.base import BaseProvider

logger = logging.getLogger("backend.integrations.ai.gateway")


class AiGateway:
    def __init__(self, profiles_path: str | None = None, max_concurrency: int = 5):
        resolved_profiles_path = profiles_path or self._default_profiles_path()
        self.profiles = self._load_profiles(resolved_profiles_path)
        self.providers = self._build_providers()
        self.max_concurrency = max(1, max_concurrency)

    async def text(self, profile: ProfileName | str, prompt: str, **kwargs: Any) -> AiResult:
        return await self._dispatch("text", profile, prompt, **kwargs)

    async def image(self, profile: ProfileName | str, prompt: str, **kwargs: Any) -> AiResult:
        return await self._dispatch("image", profile, prompt, **kwargs)

    async def chat(self, profile: ProfileName | str, messages: list[dict[str, Any]], **kwargs: Any) -> AiResult:
        return await self._dispatch("text", profile, "", messages=messages, **kwargs)

    async def text_direct(self, provider: str, model: str, prompt: str, **kwargs: Any) -> AiResult:
        current = self.providers.get(provider)
        if current is None:
            raise ProviderNotFoundError(f"Provider '{provider}' is not configured")
        return await current.text(model, prompt, **kwargs)

    async def image_direct(self, provider: str, model: str, prompt: str, **kwargs: Any) -> AiResult:
        current = self.providers.get(provider)
        if current is None:
            raise ProviderNotFoundError(f"Provider '{provider}' is not configured")
        return await current.image(model, prompt, **kwargs)

    async def chat_with_fallback(self, profile: ProfileName | str, messages: list[dict[str, Any]], **kwargs: Any) -> AiResult:
        try:
            return await self.chat(profile, messages, **kwargs)
        except RetryableAiError:
            fallback = self._fallback_for(profile)
            result = await self.chat(fallback, messages, **kwargs)
            result.fallback_used = True
            return result

    async def text_with_fallback(self, profile: ProfileName | str, prompt: str, **kwargs: Any) -> AiResult:
        try:
            return await self.text(profile, prompt, **kwargs)
        except RetryableAiError:
            fallback = self._fallback_for(profile)
            result = await self.text(fallback, prompt, **kwargs)
            result.fallback_used = True
            return result

    async def image_with_fallback(self, profile: ProfileName | str, prompt: str, **kwargs: Any) -> AiResult:
        try:
            return await self.image(profile, prompt, **kwargs)
        except RetryableAiError:
            fallback = self._fallback_for(profile)
            result = await self.image(fallback, prompt, **kwargs)
            result.fallback_used = True
            return result

    async def text_json(
        self,
        profile: ProfileName | str,
        prompt: str,
        *,
        use_fallback: bool = True,
        schema: dict[str, Any] | None = None,
        strict: bool = True,
        **kwargs: Any,
    ) -> Any:
        response_format: dict[str, Any]
        if schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": schema,
                    "strict": strict,
                },
            }
        else:
            response_format = {"type": "json_object"}

        if use_fallback:
            result = await self.text_with_fallback(profile, prompt, response_format=response_format, **kwargs)
        else:
            result = await self.text(profile, prompt, response_format=response_format, **kwargs)
        return self.extract_json(result)

    async def ocr(
        self,
        profile: ProfileName | str,
        image: str,
        *,
        mode: str = "plain",
        prompt: str | None = None,
        detail: str | None = None,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> AiResult:
        mode_value = mode.lower().strip()
        if mode_value not in {"plain", "markdown", "json"}:
            raise ValueError("OCR mode must be one of: plain, markdown, json")

        final_prompt = prompt or self._default_ocr_prompt(mode_value)
        image_url = self._image_to_url(image)
        image_payload: dict[str, Any] = {"url": image_url}
        if detail:
            image_payload["detail"] = detail
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": final_prompt},
                    {"type": "image_url", "image_url": image_payload},
                ],
            }
        ]

        if mode_value == "json" and "response_format" not in kwargs:
            kwargs["response_format"] = {"type": "json_object"}

        if use_fallback:
            return await self.chat_with_fallback(profile, messages, **kwargs)
        return await self.chat(profile, messages, **kwargs)

    async def text_many(
        self,
        profile: ProfileName | str,
        prompts: list[str],
        *,
        use_fallback: bool = True,
        concurrency: int | None = None,
        **kwargs: Any,
    ) -> list[AiResult | Exception]:
        return await self._run_many("text", profile, prompts, use_fallback=use_fallback, concurrency=concurrency, **kwargs)

    async def image_many(
        self,
        profile: ProfileName | str,
        prompts: list[str],
        *,
        use_fallback: bool = True,
        concurrency: int | None = None,
        **kwargs: Any,
    ) -> list[AiResult | Exception]:
        return await self._run_many("image", profile, prompts, use_fallback=use_fallback, concurrency=concurrency, **kwargs)

    async def _run_many(
        self,
        mode: str,
        profile: ProfileName | str,
        prompts: list[str],
        *,
        use_fallback: bool,
        concurrency: int | None,
        **kwargs: Any,
    ) -> list[AiResult | Exception]:
        semaphore = asyncio.Semaphore(max(1, concurrency or self.max_concurrency))

        async def run_one(prompt: str) -> AiResult | Exception:
            async with semaphore:
                try:
                    if mode == "text":
                        if use_fallback:
                            return await self.text_with_fallback(profile, prompt, **kwargs)
                        return await self.text(profile, prompt, **kwargs)
                    if use_fallback:
                        return await self.image_with_fallback(profile, prompt, **kwargs)
                    return await self.image(profile, prompt, **kwargs)
                except Exception as exc:
                    return exc

        tasks = [run_one(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks)

    async def _dispatch(self, mode: str, profile: str, prompt: str, **kwargs: Any) -> AiResult:
        started = time.perf_counter()
        if profile not in self.profiles:
            raise ProfileNotFoundError(f"Profile '{profile}' not found in profiles.yaml")

        cfg = self.profiles[profile]
        provider_name = cfg["provider"]
        model = cfg["model"]

        provider = self.providers.get(provider_name)
        if provider is None:
            raise ProviderNotFoundError(f"Provider '{provider_name}' is not configured")

        try:
            if mode == "text":
                result = await provider.text(model, prompt, **kwargs)
            else:
                result = await provider.image(model, prompt, **kwargs)
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "ai_request_failed mode=%s profile=%s provider=%s model=%s latency_ms=%.2f",
                mode,
                profile,
                provider_name,
                model,
                latency_ms,
            )
            raise

        latency_ms = (time.perf_counter() - started) * 1000
        result.latency_ms = latency_ms
        logger.info(
            "ai_request_ok mode=%s profile=%s provider=%s model=%s attempts=%s fallback=%s latency_ms=%.2f",
            mode,
            profile,
            result.provider,
            result.model,
            result.attempts,
            result.fallback_used,
            latency_ms,
        )
        return result

    def _fallback_for(self, profile: str) -> str:
        fallback = self.profiles.get(profile, {}).get("fallback")
        if not fallback:
            raise NoFallbackConfiguredError(f"No fallback configured for profile '{profile}'")
        return fallback

    @staticmethod
    def extract_json(result: AiResult) -> Any:
        if result.text:
            try:
                return json.loads(result.text)
            except json.JSONDecodeError:
                pass

        raw = result.raw
        if not isinstance(raw, dict):
            raise ValueError("Provider response is not a JSON object")

        content = raw.get("choices", [{}])[0].get("message", {}).get("content")
        if isinstance(content, str):
            return json.loads(content)
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    return json.loads(item["text"])

        raise ValueError("Could not extract valid JSON from model response")

    @staticmethod
    def _default_ocr_prompt(mode: str) -> str:
        if mode == "markdown":
            return "Extract all text from this image and return clean markdown."
        if mode == "json":
            return (
                "Extract text from this image and return valid JSON with keys: "
                "language, full_text, blocks (array of objects with text and confidence if available)."
            )
        return "Extract all text from this image. Return plain text preserving line breaks."

    @staticmethod
    def _image_to_url(image: str) -> str:
        lowered = image.lower()
        if lowered.startswith(("http://", "https://", "data:")):
            return image

        path = Path(image).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file not found: {image}")

        mime_type, _ = mimetypes.guess_type(path.name)
        if not mime_type:
            mime_type = "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _default_profiles_path() -> str:
        from_env = os.getenv("AI_CONNECTOR_PROFILES")
        if from_env:
            return from_env
        return str(Path.cwd() / "profiles.yaml")

    @staticmethod
    def _load_profiles(path: str) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return data

    @staticmethod
    def _build_providers() -> dict[str, BaseProvider]:
        providers: dict[str, BaseProvider] = {}
        retries = int(os.getenv("AI_CONNECTOR_RETRIES", "3"))

        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            providers["openrouter"] = OpenRouterProvider(
                api_key=openrouter_key,
                base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                timeout=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "90")),
                max_retries=retries,
            )

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            providers["openai"] = OpenAIProvider(
                api_key=openai_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "90")),
                max_retries=retries,
            )

        cheap_key = os.getenv("CHEAP_GPT_API_KEY")
        if cheap_key:
            providers["cheap_gpt"] = CheapGPTProvider(
                api_key=cheap_key,
                base_url=os.getenv("CHEAPGPT_BASE_URL", "https://api.aiproductiv.ru/v1"),
                timeout=float(os.getenv("CHEAPGPT_TIMEOUT_SECONDS", "90")),
                max_retries=retries,
            )

        return providers
