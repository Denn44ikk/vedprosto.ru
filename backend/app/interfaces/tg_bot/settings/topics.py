from __future__ import annotations

from dataclasses import replace

from .service import (
    TgBotRuntimeSettings,
    _parse_csv_int_set,
    _parse_optional_int,
    _parse_request_comment_topic_map,
    _parse_supplier_topic_map,
)


TOPIC_EDIT_TOKEN_MAP = {
    "chat": "target_chat_id",
    "allowed": "allowed_topic_ids",
    "comments": "request_comment_topic_map",
    "price": "price_topic_id",
    "settings": "settings_topic_id",
    "suppliers": "supplier_topic_map",
}

TOPIC_FIELD_LABELS = {
    "target_chat_id": "TARGET_CHAT_ID",
    "allowed_topic_ids": "TG_ALLOWED_TOPIC_IDS",
    "request_comment_topic_map": "TG_REQUEST_COMMENT_TOPIC_MAP",
    "price_topic_id": "TG_PRICE_TOPIC_ID",
    "settings_topic_id": "TG_SETTINGS_TOPIC_ID",
    "supplier_topic_map": "TG_PRICE_SUPPLIER_TOPIC_MAP",
}


def apply_runtime_settings_update(
    *,
    runtime_settings: TgBotRuntimeSettings,
    field: str,
    raw_value: str,
) -> TgBotRuntimeSettings:
    value = raw_value.strip()
    if field == "target_chat_id":
        parsed = _parse_optional_int(value)
        if parsed is None:
            raise ValueError("Нужен числовой chat id.")
        return replace(runtime_settings, target_chat_id=parsed)
    if field == "allowed_topic_ids":
        parsed = () if value in {"", "-"} else _parse_csv_int_set(value)
        return replace(runtime_settings, allowed_topic_ids=parsed)
    if field == "request_comment_topic_map":
        parsed = {} if value in {"", "-"} else _parse_request_comment_topic_map(value)
        return replace(runtime_settings, request_comment_topic_map=parsed)
    if field == "price_topic_id":
        parsed = None if value in {"", "-"} else _parse_optional_int(value)
        return replace(runtime_settings, price_topic_id=parsed)
    if field == "settings_topic_id":
        parsed = None if value in {"", "-"} else _parse_optional_int(value)
        return replace(runtime_settings, settings_topic_id=parsed)
    if field == "supplier_topic_map":
        parsed = {} if value in {"", "-"} else _parse_supplier_topic_map(value)
        return replace(runtime_settings, supplier_topic_map=parsed)
    raise ValueError(f"Неизвестное поле настроек: {field}")


__all__ = [
    "TOPIC_EDIT_TOKEN_MAP",
    "TOPIC_FIELD_LABELS",
    "apply_runtime_settings_update",
]
