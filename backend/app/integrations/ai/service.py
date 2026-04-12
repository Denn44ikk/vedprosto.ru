from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from ...config import AppSettings
from .gateway import AiGateway


class AIIntegrationService:
    """Project-local AI integration entrypoint for scripts and services."""

    def __init__(self, *, settings: AppSettings) -> None:
        self.settings = settings
        self._gateway: Any | None = None
        self._gateway_import_path = ""

    def describe(self) -> dict[str, Any]:
        resolved_profiles_path = self._resolve_profiles_path()
        package_dir = Path(__file__).resolve().parent
        payload: dict[str, Any] = {
            "connector_dir": str(package_dir),
            "profiles_path": str(resolved_profiles_path),
            "available": False,
            "profiles": [],
            "import_path": str(package_dir),
        }
        try:
            gateway = self.get_gateway()
        except Exception as exc:
            payload["error"] = str(exc)
            return payload

        payload["available"] = True
        payload["profiles"] = sorted(str(key) for key in getattr(gateway, "profiles", {}).keys())
        return payload

    def list_profiles(self) -> list[str]:
        gateway = self.get_gateway()
        return sorted(str(key) for key in getattr(gateway, "profiles", {}).keys())

    def get_gateway(self) -> Any:
        if self._gateway is not None:
            return self._gateway

        self._bridge_legacy_env()
        profiles_path = self._resolve_profiles_path()
        self._gateway = AiGateway(
            str(profiles_path),
            max_concurrency=self.settings.ai_connector_max_concurrency,
        )
        self._gateway_import_path = str(Path(__file__).resolve().parent)
        return self._gateway

    async def text(
        self,
        *,
        profile: str,
        prompt: str,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        if use_fallback:
            return await gateway.text_with_fallback(profile, prompt, **kwargs)
        return await gateway.text(profile, prompt, **kwargs)

    async def chat(
        self,
        *,
        profile: str,
        messages: list[dict[str, Any]],
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        if use_fallback:
            return await gateway.chat_with_fallback(profile, messages, **kwargs)
        return await gateway.chat(profile, messages, **kwargs)

    async def text_json(
        self,
        *,
        profile: str,
        prompt: str,
        use_fallback: bool = True,
        schema: dict[str, Any] | None = None,
        strict: bool = True,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        return await gateway.text_json(
            profile,
            prompt,
            use_fallback=use_fallback,
            schema=schema,
            strict=strict,
            **kwargs,
        )

    async def ocr(
        self,
        *,
        profile: str,
        image: str,
        mode: str = "plain",
        prompt: str | None = None,
        detail: str | None = None,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        return await gateway.ocr(
            profile,
            image=image,
            mode=mode,
            prompt=prompt,
            detail=detail,
            use_fallback=use_fallback,
            **kwargs,
        )

    async def image(
        self,
        *,
        profile: str,
        prompt: str,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        if use_fallback:
            return await gateway.image_with_fallback(profile, prompt, **kwargs)
        return await gateway.image(profile, prompt, **kwargs)

    async def text_many(
        self,
        *,
        profile: str,
        prompts: list[str],
        use_fallback: bool = True,
        concurrency: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        gateway = self.get_gateway()
        return await gateway.text_many(
            profile,
            prompts,
            use_fallback=use_fallback,
            concurrency=concurrency,
            **kwargs,
        )

    async def image_many(
        self,
        *,
        profile: str,
        prompts: list[str],
        use_fallback: bool = True,
        concurrency: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        gateway = self.get_gateway()
        return await gateway.image_many(
            profile,
            prompts,
            use_fallback=use_fallback,
            concurrency=concurrency,
            **kwargs,
        )

    async def text_direct(
        self,
        *,
        provider: str,
        model: str,
        prompt: str,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        return await gateway.text_direct(provider=provider, model=model, prompt=prompt, **kwargs)

    async def image_direct(
        self,
        *,
        provider: str,
        model: str,
        prompt: str,
        **kwargs: Any,
    ) -> Any:
        gateway = self.get_gateway()
        return await gateway.image_direct(provider=provider, model=model, prompt=prompt, **kwargs)

    def text_sync(
        self,
        *,
        profile: str,
        prompt: str,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        return self._run_sync(self.text(profile=profile, prompt=prompt, use_fallback=use_fallback, **kwargs))

    def text_json_sync(
        self,
        *,
        profile: str,
        prompt: str,
        use_fallback: bool = True,
        schema: dict[str, Any] | None = None,
        strict: bool = True,
        **kwargs: Any,
    ) -> Any:
        return self._run_sync(
            self.text_json(
                profile=profile,
                prompt=prompt,
                use_fallback=use_fallback,
                schema=schema,
                strict=strict,
                **kwargs,
            )
        )

    def chat_sync(
        self,
        *,
        profile: str,
        messages: list[dict[str, Any]],
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        return self._run_sync(self.chat(profile=profile, messages=messages, use_fallback=use_fallback, **kwargs))

    def ocr_sync(
        self,
        *,
        profile: str,
        image: str,
        mode: str = "plain",
        prompt: str | None = None,
        detail: str | None = None,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        return self._run_sync(
            self.ocr(
                profile=profile,
                image=image,
                mode=mode,
                prompt=prompt,
                detail=detail,
                use_fallback=use_fallback,
                **kwargs,
            )
        )

    def image_sync(
        self,
        *,
        profile: str,
        prompt: str,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> Any:
        return self._run_sync(self.image(profile=profile, prompt=prompt, use_fallback=use_fallback, **kwargs))

    @staticmethod
    def _run_sync(awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("Use async AIIntegrationService methods inside an active event loop.")

    def _bridge_legacy_env(self) -> None:
        profiles_path = self._resolve_profiles_path()

        if "CHEAP_GPT_API_KEY" not in os.environ and os.getenv("CHEAPGPT_API_KEY"):
            os.environ["CHEAP_GPT_API_KEY"] = os.environ["CHEAPGPT_API_KEY"]
        if "AI_CONNECTOR_PROFILES" not in os.environ:
            os.environ["AI_CONNECTOR_PROFILES"] = str(profiles_path)

    def _resolve_profiles_path(self) -> Path:
        candidate = self.settings.ai_connector_profiles_path.expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate

        raise RuntimeError(
            f"AI connector profiles file not found: {candidate}. "
            "Check AI_CONNECTOR_PROFILES_PATH."
        )


def build_ai_integration_service(*, settings: AppSettings) -> AIIntegrationService:
    return AIIntegrationService(settings=settings)


__all__ = ["AIIntegrationService", "build_ai_integration_service"]
