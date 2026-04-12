from __future__ import annotations

import asyncio
import time
from typing import Final
from urllib.parse import urlencode

from .models import IfcgQuery


IFCG_SEARCH_URL: Final[str] = "https://www.ifcg.ru/kb/tnved/search/"
IFCG_DEFAULT_USER_AGENT: Final[str] = "Mozilla/5.0 (compatible; agent_ui_ifcg/0.1)"


class IfcgClient:
    def __init__(
        self,
        *,
        timeout_sec: int = 20,
        min_interval_sec: float = 2.0,
        user_agent: str = IFCG_DEFAULT_USER_AGENT,
    ) -> None:
        self._timeout_sec = max(5, int(timeout_sec))
        self._min_interval_sec = max(0.0, float(min_interval_sec))
        self._user_agent = user_agent.strip() or IFCG_DEFAULT_USER_AGENT
        self._session = None
        self._session_loop: asyncio.AbstractEventLoop | None = None
        self._rate_lock: asyncio.Lock | None = None
        self._rate_lock_loop: asyncio.AbstractEventLoop | None = None
        self._next_allowed_at = 0.0

    async def __aenter__(self) -> "IfcgClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        await self._ensure_loop_state()
        if self._session is not None and not self._session.closed:
            return
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=self._timeout_sec)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": self._user_agent},
        )
        self._session_loop = asyncio.get_running_loop()

    async def close(self) -> None:
        await self._close_session()
        self._session = None
        self._session_loop = None

    async def _close_session(self) -> None:
        if self._session is None or self._session.closed:
            return
        current_loop = asyncio.get_running_loop()
        if self._session_loop is not None and self._session_loop is not current_loop and self._session_loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._session.close(), self._session_loop)
                await asyncio.wrap_future(future)
                return
            except Exception:
                pass
        await self._session.close()

    async def _ensure_loop_state(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._rate_lock is None or self._rate_lock_loop is not current_loop:
            self._rate_lock = asyncio.Lock()
            self._rate_lock_loop = current_loop
        if self._session is not None and self._session_loop is not current_loop:
            await self._close_session()
            self._session = None
            self._session_loop = None

    def build_url(self, query: IfcgQuery) -> str:
        params = {"q": query.text.strip()}
        if query.group_filter.strip():
            params["g"] = query.group_filter.strip()
        if query.stat_mode:
            params["s"] = "stat"
        return IFCG_SEARCH_URL + "?" + urlencode(params)

    async def _wait_for_slot(self) -> None:
        if self._min_interval_sec <= 0:
            return
        await self._ensure_loop_state()
        if self._rate_lock is None:
            return
        async with self._rate_lock:
            now = time.monotonic()
            delay = self._next_allowed_at - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_allowed_at = time.monotonic() + self._min_interval_sec

    async def fetch_search_html(self, query: IfcgQuery) -> tuple[str, int, str]:
        await self.start()
        if self._session is None:
            return "", 0, self.build_url(query)

        await self._wait_for_slot()
        url = self.build_url(query)
        async with self._session.get(url) as response:
            return await response.text(), response.status, url
