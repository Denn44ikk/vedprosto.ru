from __future__ import annotations

from typing import Any

from ...integrations.ai.service import AIIntegrationService
from .models import ChatTranscriptMessage


class ChatEngine:
    def __init__(self, *, ai_integration_service: AIIntegrationService) -> None:
        self.ai_integration_service = ai_integration_service

    def build_messages(
        self,
        *,
        system_prompt: str,
        context_markdown: str,
        recent_messages: list[ChatTranscriptMessage],
        intro_text: str,
        attachment_blocks: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        content_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Контекст кейса:\n\n{context_markdown.strip()}",
            }
        ]
        if attachment_blocks:
            content_blocks.extend(attachment_blocks)

        messages.append(
            {
                "role": "user",
                "content": content_blocks if attachment_blocks else content_blocks[0]["text"],
            }
        )

        for message in recent_messages:
            text = message.text.strip()
            if not text or text == intro_text:
                continue
            role = "assistant" if message.role == "model" else "user"
            messages.append({"role": role, "content": text})

        return messages

    def run_sync(
        self,
        *,
        profile: str,
        use_fallback: bool,
        system_prompt: str,
        context_markdown: str,
        recent_messages: list[ChatTranscriptMessage],
        intro_text: str,
        attachment_blocks: list[dict[str, Any]] | None = None,
    ) -> str:
        result = self.ai_integration_service.chat_sync(
            profile=profile,
            messages=self.build_messages(
                system_prompt=system_prompt,
                context_markdown=context_markdown,
                recent_messages=recent_messages,
                intro_text=intro_text,
                attachment_blocks=attachment_blocks,
            ),
            use_fallback=use_fallback,
        )
        answer = str(getattr(result, "text", "") or "").strip()
        if not answer:
            raise RuntimeError("Chat engine returned an empty answer.")
        return answer

    async def run_async(
        self,
        *,
        profile: str,
        use_fallback: bool,
        system_prompt: str,
        context_markdown: str,
        recent_messages: list[ChatTranscriptMessage],
        intro_text: str,
        attachment_blocks: list[dict[str, Any]] | None = None,
    ) -> str:
        result = await self.ai_integration_service.chat(
            profile=profile,
            messages=self.build_messages(
                system_prompt=system_prompt,
                context_markdown=context_markdown,
                recent_messages=recent_messages,
                intro_text=intro_text,
                attachment_blocks=attachment_blocks,
            ),
            use_fallback=use_fallback,
        )
        answer = str(getattr(result, "text", "") or "").strip()
        if not answer:
            raise RuntimeError("Chat engine returned an empty answer.")
        return answer
