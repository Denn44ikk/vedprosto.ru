from __future__ import annotations

from threading import Event
from threading import Lock


class PipelineWorkerRuntime:
    def __init__(self) -> None:
        self._lock = Lock()
        self._root_stop_events: dict[str, Event] = {}

    def _get_root_event(self, root_path: str) -> Event:
        with self._lock:
            event = self._root_stop_events.get(root_path)
            if event is None:
                event = Event()
                self._root_stop_events[root_path] = event
            return event

    def clear_root_stop(self, root_path: str) -> None:
        self._get_root_event(root_path).clear()

    def request_root_stop(self, root_path: str) -> None:
        self._get_root_event(root_path).set()

    def is_root_stop_requested(self, root_path: str) -> bool:
        return self._get_root_event(root_path).is_set()
