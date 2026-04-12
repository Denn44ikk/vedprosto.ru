from __future__ import annotations

import base64
from dataclasses import dataclass

from .models import SigmaPaycalcResult, SigmaPriceSnapshot
from .parser import parse_sigma_paycalc_bytes, parse_sigma_paycalc_html
from .price_view import build_sigma_price_snapshot


@dataclass(frozen=True)
class SigmaParserInput:
    code: str
    query_date: str
    html_text: str | None = None
    raw_bytes: bytes | None = None
    source_url: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "SigmaParserInput":
        payload = payload if isinstance(payload, dict) else {}
        html_text = payload.get("html_text")
        raw_bytes_value = payload.get("raw_bytes")
        raw_base64 = payload.get("raw_base64")

        raw_bytes: bytes | None = None
        if isinstance(raw_bytes_value, bytes):
            raw_bytes = raw_bytes_value
        elif isinstance(raw_bytes_value, str) and raw_bytes_value.strip():
            raw_bytes = raw_bytes_value.encode("latin-1", errors="ignore")
        elif isinstance(raw_base64, str) and raw_base64.strip():
            try:
                raw_bytes = base64.b64decode(raw_base64)
            except Exception:
                raw_bytes = b""

        return cls(
            code=str(payload.get("code") or "").strip(),
            query_date=str(payload.get("query_date") or "").strip(),
            html_text=str(html_text) if isinstance(html_text, str) else None,
            raw_bytes=raw_bytes,
            source_url=str(payload.get("source_url") or "").strip() or None,
        )

    @property
    def input_kind(self) -> str:
        if self.html_text:
            return "html_text"
        if self.raw_bytes is not None:
            return "raw_bytes"
        return "empty"


@dataclass(frozen=True)
class SigmaParserOutput:
    request: SigmaParserInput
    result: SigmaPaycalcResult
    snapshot: SigmaPriceSnapshot

    def to_dict(self) -> dict[str, object]:
        return {
            "request": {
                "code": self.request.code,
                "query_date": self.request.query_date,
                "source_url": self.request.source_url,
                "input_kind": self.request.input_kind,
            },
            "status": self.result.status,
            "result": self.result.to_dict(),
            "summary": {
                "duty_rate": self.result.duty_text,
                "vat_rate": self.result.vat_text,
                "flags": list(self.result.emoji_flags),
                "eco_attention_prefix": self.result.eco_attention_prefix,
                "raw_lines": list(self.result.raw_text_lines),
                "customs_fee": self.result.customs_fee.to_dict(),
                "protective": self.result.protective.to_dict(),
                "excise": self.result.excise.to_dict(),
                "mandatory_marking": self.result.mandatory_marking.to_dict(),
                "eco": self.result.eco.to_dict(),
            },
            "snapshot": _snapshot_to_dict(self.snapshot),
        }


def _snapshot_to_dict(snapshot: SigmaPriceSnapshot) -> dict[str, object]:
    return {
        "code": snapshot.code,
        "source_url": snapshot.source_url,
        "query_date": snapshot.query_date,
        "item_name": snapshot.item_name,
        "leading_emojis": list(snapshot.leading_emojis),
        "optional_lines": list(snapshot.optional_lines),
        "warning_lines": list(snapshot.warning_lines),
        "is_partial": snapshot.is_partial,
        "is_technical_failure": snapshot.is_technical_failure,
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "status": section.status,
                "emoji": section.emoji,
                "short_value": section.short_value,
                "detail_text": section.detail_text,
                "calc_values": list(section.calc_values),
                "display_line": section.display_line,
                "extra_lines": list(section.extra_lines),
                "sigma_line": section.sigma_line,
                "contributes_to_leading_emoji": section.contributes_to_leading_emoji,
            }
            for section in snapshot.sections
        ],
    }


def parse_sigma_input(request: SigmaParserInput) -> SigmaParserOutput:
    if request.html_text:
        result = parse_sigma_paycalc_html(
            request.html_text,
            code=request.code,
            query_date=request.query_date,
            source_url=request.source_url,
        )
    else:
        result = parse_sigma_paycalc_bytes(
            request.raw_bytes or b"",
            code=request.code,
            query_date=request.query_date,
            source_url=request.source_url,
        )
    snapshot = build_sigma_price_snapshot(result)
    return SigmaParserOutput(request=request, result=result, snapshot=snapshot)


def parse_sigma_payload(payload: dict[str, object] | None) -> dict[str, object]:
    request = SigmaParserInput.from_dict(payload)
    return parse_sigma_input(request).to_dict()


__all__ = [
    "SigmaParserInput",
    "SigmaParserOutput",
    "parse_sigma_input",
    "parse_sigma_payload",
]
