from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicRouterConfig:
    target_chat_id: int = 0
    allowed_topic_ids: set[int] = field(default_factory=set)
    request_comment_topic_map: dict[int, int] = field(default_factory=dict)
    price_topic_id: int | None = None
    settings_topic_id: int | None = None
    supplier_topic_map: dict[str, int] = field(default_factory=dict)


class TopicRouter:
    def __init__(self, config: TopicRouterConfig) -> None:
        self._config = config

    @property
    def config(self) -> TopicRouterConfig:
        return self._config

    def is_allowed_message(self, *, chat_id: int, topic_id: int | None) -> bool:
        chat_allowed = self._config.target_chat_id == 0 or chat_id == self._config.target_chat_id
        if not chat_allowed or topic_id is None:
            return False
        if 0 in self._config.allowed_topic_ids:
            return True
        return topic_id in self._config.allowed_topic_ids

    def is_price_topic(self, topic_id: int | None) -> bool:
        return topic_id is not None and self._config.price_topic_id == topic_id

    def is_settings_topic(self, topic_id: int | None) -> bool:
        return topic_id is not None and self._config.settings_topic_id == topic_id

    def comment_topic_for(self, request_topic_id: int | None) -> int | None:
        if request_topic_id is None:
            return None
        return self._config.request_comment_topic_map.get(request_topic_id)

    def supplier_topic_for(self, supplier_key: str | None) -> int | None:
        if supplier_key is None:
            return None
        return self._config.supplier_topic_map.get(supplier_key.strip().lower())
