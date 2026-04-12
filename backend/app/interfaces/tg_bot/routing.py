from __future__ import annotations

import html
import re
from dataclasses import dataclass

try:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None


@dataclass(frozen=True)
class ReplyBinding:
    chat_id: int
    source_topic_id: int | None
    source_message_id: int
    bot_message_id: int
    old_tnved: str | None = None
    source_message_ids: tuple[int, ...] = ()
    correction_prompt_message_id: int | None = None


@dataclass(frozen=True)
class CorrectionPayload:
    ref_text: str
    ref_chat_id: int
    request_topic_id: int
    source_message_id: int
    bot_message_id: int
    old_tnved: str | None
    new_tnved: str
    reason_text: str
    rule_text: str
    raw_text: str


def build_review_keyboard(
    *,
    callback_approve: str,
    callback_correct: str,
    callback_refresh: str,
    callback_reject: str,
) -> InlineKeyboardMarkup | None:
    if InlineKeyboardMarkup is None or InlineKeyboardButton is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="OK", callback_data=callback_approve),
                InlineKeyboardButton(text="Fix", callback_data=callback_correct),
                InlineKeyboardButton(text="Reload", callback_data=callback_refresh),
                InlineKeyboardButton(text="Stop", callback_data=callback_reject),
            ]
        ]
    )


def should_attach_review_buttons(*, tnved_status: str, tnved: str, report_short_text: str) -> bool:
    if not (report_short_text or "").strip():
        return False
    if not (tnved or "").strip():
        return False
    return (tnved_status or "").strip() not in {"pipeline_error", "pipeline_retry_queued", "validation_error", "empty"}


def extract_message_text(*, text: str | None = None, caption: str | None = None) -> str:
    return (text or caption or "").strip()


def is_correction_message(raw_text: str | None, *, correction_marker: str) -> bool:
    text = (raw_text or "").replace("\r\n", "\n").lstrip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\n?", "", text).lstrip()
    return text.upper().startswith(correction_marker)


def build_correction_template(*, link: ReplyBinding, correction_marker: str) -> str:
    old_tnved = link.old_tnved or "-"
    ref_text = f"{link.chat_id}:{link.source_topic_id or 0}:{link.source_message_id}:{link.bot_message_id}"
    template = "\n".join(
        [
            correction_marker,
            f"ref: {ref_text}",
            f"old_tnved: {old_tnved}",
            "new_tnved:",
            "reason:",
            "rule:",
        ]
    )
    return (
        "Скопируйте шаблон, заполните и отправьте в эту тему в любое время.\n\n"
        f"<pre>{html.escape(template)}</pre>"
    )


def parse_correction_payload(
    raw_text: str | None,
    *,
    correction_marker: str,
) -> tuple[CorrectionPayload | None, str | None]:
    text = (raw_text or "").replace("\r\n", "\n").strip()
    if not text:
        return None, "Пустое сообщение коррекции."

    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\n?", "", text).strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, "Пустой шаблон коррекции."
    if not lines[0].upper().startswith(correction_marker):
        return None, f"Сообщение должно начинаться с {correction_marker}."

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_norm = key.strip().lower()
        if key_norm:
            fields[key_norm] = value.strip()

    ref_text = fields.get("ref", "")
    ref_match = re.fullmatch(r"\s*(-?\d+)\s*:\s*(-?\d+)\s*:\s*(\d+)\s*:\s*(\d+)\s*", ref_text)
    if ref_match is None:
        return None, "Поле ref должно быть в формате chat_id:request_topic_id:source_message_id:bot_message_id."
    ref_chat_id = int(ref_match.group(1))
    request_topic_id = int(ref_match.group(2))
    source_message_id = int(ref_match.group(3))
    bot_message_id = int(ref_match.group(4))

    old_tnved_raw = fields.get("old_tnved", "")
    old_tnved = re.sub(r"\D", "", old_tnved_raw) if old_tnved_raw else ""
    if len(old_tnved) != 10:
        old_tnved = ""

    new_tnved = re.sub(r"\D", "", fields.get("new_tnved", ""))
    if len(new_tnved) != 10:
        return None, "Поле new_tnved должно содержать 10 цифр."

    reason_text = (fields.get("reason", "") or "").strip()
    if not reason_text:
        return None, "Поле reason обязательно."

    rule_text = (fields.get("rule", "") or "").strip()
    if not rule_text:
        return None, "Поле rule обязательно."

    return (
        CorrectionPayload(
            ref_text=f"{ref_chat_id}:{request_topic_id}:{source_message_id}:{bot_message_id}",
            ref_chat_id=ref_chat_id,
            request_topic_id=request_topic_id,
            source_message_id=source_message_id,
            bot_message_id=bot_message_id,
            old_tnved=old_tnved or None,
            new_tnved=new_tnved,
            reason_text=reason_text,
            rule_text=rule_text,
            raw_text=text,
        ),
        None,
    )


def collect_review_cleanup_message_ids(*, link: ReplyBinding) -> list[int]:
    source_message_ids = list(link.source_message_ids) if link.source_message_ids else [link.source_message_id]
    message_ids = source_message_ids + [link.bot_message_id]
    if link.correction_prompt_message_id is not None:
        message_ids.append(link.correction_prompt_message_id)
    return message_ids


def collect_correction_cleanup_message_ids(
    *,
    correction_message_id: int,
    payload: CorrectionPayload,
    source_message_ids: list[int] | None = None,
    correction_prompt_message_id: int | None = None,
) -> list[int]:
    message_ids = list(source_message_ids or [payload.source_message_id])
    message_ids.extend([payload.bot_message_id, correction_message_id])
    if correction_prompt_message_id is not None:
        message_ids.append(correction_prompt_message_id)
    return message_ids


__all__ = [
    "CorrectionPayload",
    "ReplyBinding",
    "build_correction_template",
    "build_review_keyboard",
    "collect_correction_cleanup_message_ids",
    "collect_review_cleanup_message_ids",
    "extract_message_text",
    "is_correction_message",
    "parse_correction_payload",
    "should_attach_review_buttons",
]
