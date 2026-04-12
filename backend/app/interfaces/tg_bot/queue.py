from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class _QueuedTask(Generic[T]):
    name: str
    runner: Callable[[], Awaitable[T]]
    future: asyncio.Future[T]


class TelegramTaskQueue:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("agent_ui.interfaces.tg_bot.queue")
        self._queue: asyncio.Queue[_QueuedTask[object] | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._guard = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        async with self._guard:
            if self.is_running:
                return
            self._worker = asyncio.create_task(self._worker_loop())

    async def close(self) -> None:
        async with self._guard:
            if self._worker is None:
                return
            await self._queue.put(None)
            await self._worker
            self._worker = None

    async def submit(self, *, name: str, runner: Callable[[], Awaitable[T]]) -> T:
        if not self.is_running:
            await self.start()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        await self._queue.put(_QueuedTask(name=name, runner=runner, future=future))
        return await future

    async def _worker_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            try:
                result = await item.runner()
            except Exception as exc:
                self._logger.exception("Telegram queue task failed name=%s", item.name)
                if not item.future.done():
                    item.future.set_exception(exc)
            else:
                if not item.future.done():
                    item.future.set_result(result)


__all__ = ["TelegramTaskQueue"]
