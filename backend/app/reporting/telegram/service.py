from __future__ import annotations

from dataclasses import dataclass

from ...integrations.its.models import ITSFetchResult
from ...orchestrator.shared_flow import SharedFlowResult


@dataclass(frozen=True)
class TelegramReplyPayload:
    text: str
    report_short_text: str
    report_full_text: str
    tnved: str | None
    tnved_status: str
    payload_json: dict[str, object]


def _preview_text(value: str, *, limit: int = 320) -> str:
    trimmed = (value or "").strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[: limit - 1].rstrip() + "…"


def _build_its_lines(its_result: ITSFetchResult | None) -> list[str]:
    if its_result is None:
        return ["ITS: не запрашивался"]
    if its_result.status == "ok":
        value = f"{its_result.its_value:g}" if its_result.its_value is not None else "-"
        bracket = f"{its_result.its_bracket_value:g}" if its_result.its_bracket_value is not None else "-"
        date_text = its_result.date_text or "-"
        return [
            f"ITS: ok, ставка={value}, диапазон={bracket}, дата={date_text}",
        ]
    return [f"ITS: {its_result.status}" + (f" ({its_result.error_text})" if its_result.error_text else "")]


def build_tg_analysis_reply(
    *,
    shared_result: SharedFlowResult,
    its_result: ITSFetchResult | None = None,
) -> TelegramReplyPayload:
    lines: list[str] = ["Результат TG-анализа"]
    preview = _preview_text(shared_result.normalized_text or shared_result.source_text, limit=280)
    if preview:
        lines.extend(["", f"Текст: {preview}"])

    if shared_result.primary_code:
        lines.append(f"Код: {shared_result.primary_code}")
    elif shared_result.detected_codes:
        lines.append("Кандидаты кодов: " + ", ".join(shared_result.detected_codes))
    else:
        lines.append("Код в сообщении не найден.")

    lines.extend(_build_its_lines(its_result))

    if shared_result.tnved_status == "input_only":
        lines.append("Дальше нужен перенос полноценного shared pipeline: OCR/TNVED/verification.")
    elif shared_result.tnved_status == "empty":
        lines.append("Сообщение пустое или без текстовой части.")

    report_full_text = "\n".join(lines)
    report_short_text = lines[-1] if lines else "TG analysis completed"
    return TelegramReplyPayload(
        text=report_full_text,
        report_short_text=report_short_text,
        report_full_text=report_full_text,
        tnved=shared_result.primary_code,
        tnved_status=shared_result.tnved_status,
        payload_json={
            "source_text": shared_result.source_text,
            "normalized_text": shared_result.normalized_text,
            "detected_codes": list(shared_result.detected_codes),
            "primary_code": shared_result.primary_code,
            "tnved_status": shared_result.tnved_status,
            "its": (
                {
                    "code": its_result.code,
                    "status": its_result.status,
                    "its_value": its_result.its_value,
                    "its_bracket_value": its_result.its_bracket_value,
                    "date_text": its_result.date_text,
                    "error_text": its_result.error_text,
                }
                if its_result is not None
                else None
            ),
        },
    )


__all__ = ["TelegramReplyPayload", "build_tg_analysis_reply"]
