from __future__ import annotations

from typing import Any

from ..research import AgentWebSearchService


class WebSearchTool:
    def __init__(self, *, web_search_service: AgentWebSearchService) -> None:
        self._web_search_service = web_search_service

    def search(self, *, runtime_context: dict[str, Any], latest_user_message: str) -> dict[str, Any]:
        return self._web_search_service.build_research_payload(
            runtime_context=runtime_context,
            latest_user_message=latest_user_message,
        )

    async def search_async(self, *, runtime_context: dict[str, Any], latest_user_message: str) -> dict[str, Any]:
        return self.search(runtime_context=runtime_context, latest_user_message=latest_user_message)
