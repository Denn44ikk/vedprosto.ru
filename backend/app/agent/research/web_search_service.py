from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ...config import AppSettings


def _collapse_spaces(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _pick_search_query(runtime_context: dict[str, Any], latest_user_message: str) -> str:
    current_case = runtime_context.get("current_case") if isinstance(runtime_context.get("current_case"), dict) else {}
    summary = current_case.get("summary") if isinstance(current_case.get("summary"), dict) else {}
    title_ru = _collapse_spaces(current_case.get("title_ru"))
    title_cn = _collapse_spaces(current_case.get("title_cn"))
    selected_code = _collapse_spaces(summary.get("tnved"))
    user_part = _collapse_spaces(latest_user_message)

    parts: list[str] = []
    if title_ru and title_ru != "—":
        parts.append(title_ru)
    elif title_cn and title_cn != "—":
        parts.append(title_cn)
    if selected_code and selected_code != "—" and any(token in user_part.casefold() for token in ("код", "тнвэд", "tnved")):
        parts.append(selected_code)
    if user_part:
        parts.append(user_part)
    return _collapse_spaces(" ".join(parts))


class AgentWebSearchService:
    _search_url = "https://html.duckduckgo.com/html/"
    _base_url = "https://duckduckgo.com"

    def __init__(self, *, settings: AppSettings) -> None:
        self._settings = settings

    def build_research_payload(
        self,
        *,
        runtime_context: dict[str, Any],
        latest_user_message: str,
    ) -> dict[str, Any]:
        if not self._settings.chat_cli_web_search_enabled:
            return {"status": "disabled", "query": "", "results": [], "note": "web search disabled"}

        query = _pick_search_query(runtime_context, latest_user_message)
        if not query:
            return {"status": "empty", "query": "", "results": [], "note": "empty query"}

        try:
            response = requests.post(
                self._search_url,
                data={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                },
                timeout=self._settings.chat_cli_web_search_timeout_sec,
            )
            response.raise_for_status()
        except Exception as exc:
            return {
                "status": "error",
                "query": query,
                "results": [],
                "note": str(exc),
            }

        soup = BeautifulSoup(response.text, "html.parser")
        result_items: list[dict[str, str]] = []
        for result in soup.select(".result"):
            title_link = result.select_one(".result__title a.result__a")
            if title_link is None:
                continue
            title = _collapse_spaces(title_link.get_text(" ", strip=True))
            href = str(title_link.get("href", "")).strip()
            if href.startswith("/"):
                href = urljoin(self._base_url, href)
            snippet_node = result.select_one(".result__snippet")
            snippet = _collapse_spaces(snippet_node.get_text(" ", strip=True)) if snippet_node else ""
            if not title or not href:
                continue
            result_items.append(
                {
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                }
            )
            if len(result_items) >= self._settings.chat_cli_web_search_max_results:
                break

        return {
            "status": "ok" if result_items else "empty",
            "query": query,
            "results": result_items,
            "note": "",
        }

    async def search_async(
        self,
        *,
        runtime_context: dict[str, Any],
        latest_user_message: str,
    ) -> dict[str, Any]:
        return await __import__("asyncio").to_thread(
            self.build_research_payload,
            runtime_context=runtime_context,
            latest_user_message=latest_user_message,
        )
