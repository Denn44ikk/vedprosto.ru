from __future__ import annotations

from dataclasses import dataclass, field

from .utils import (
    PP1637_CUSTOMS_FEE_EMOJI,
    SIGMA_ECO_ATTENTION_PREFIX,
    SIGMA_EXCISE_EMOJI,
    SIGMA_MANDATORY_MARKING_EMOJI,
    SIGMA_PROTECTIVE_EMOJI,
    normalize_code_10,
)


@dataclass(frozen=True)
class SigmaConfig:
    enabled: bool = False
    timeout_sec: int = 30
    delay_sec: float = 1.0
    max_retries: int = 3
    cache_ttl_days: int = 7


@dataclass(frozen=True)
class SigmaMeasureState:
    status: str = "blank"
    summary_value: str | None = None
    detail_text: str | None = None
    calc_values: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    @property
    def is_positive(self) -> bool:
        return self.status == "positive"

    @property
    def has_attention(self) -> bool:
        return self.status in {"positive", "conditional"}

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary_value": self.summary_value,
            "detail_text": self.detail_text,
            "calc_values": list(self.calc_values),
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "SigmaMeasureState":
        payload = payload or {}
        return cls(
            status=str(payload.get("status") or "blank"),
            summary_value=str(payload.get("summary_value")).strip() if payload.get("summary_value") is not None else None,
            detail_text=str(payload.get("detail_text")).strip() if payload.get("detail_text") is not None else None,
            calc_values=tuple(
                str(item).strip()
                for item in (payload.get("calc_values") if isinstance(payload.get("calc_values"), list) else [])
                if str(item).strip()
            ),
            source_ids=tuple(
                str(item).strip()
                for item in (payload.get("source_ids") if isinstance(payload.get("source_ids"), list) else [])
                if str(item).strip()
            ),
        )


@dataclass(frozen=True)
class SigmaRawRow:
    row_id: str
    label: str | None = None
    cell_id: str | None = None
    values: tuple[str, ...] = ()

    @property
    def value_text(self) -> str | None:
        joined = " | ".join(value for value in self.values if value)
        return joined or None

    def to_dict(self) -> dict[str, object]:
        return {
            "row_id": self.row_id,
            "label": self.label,
            "cell_id": self.cell_id,
            "values": list(self.values),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "SigmaRawRow":
        payload = payload or {}
        return cls(
            row_id=str(payload.get("row_id") or "").strip(),
            label=str(payload.get("label")).strip() if payload.get("label") is not None else None,
            cell_id=str(payload.get("cell_id")).strip() if payload.get("cell_id") is not None else None,
            values=tuple(
                str(item).strip()
                for item in (payload.get("values") if isinstance(payload.get("values"), list) else [])
                if str(item).strip()
            ),
        )


@dataclass(frozen=True)
class SigmaPaycalcResult:
    code: str
    query_date: str
    status: str
    source_url: str
    item_name: str | None = None
    duty_text: str | None = None
    vat_text: str | None = None
    customs_fee: SigmaMeasureState = field(default_factory=SigmaMeasureState)
    protective: SigmaMeasureState = field(default_factory=SigmaMeasureState)
    excise: SigmaMeasureState = field(default_factory=SigmaMeasureState)
    mandatory_marking: SigmaMeasureState = field(default_factory=SigmaMeasureState)
    eco: SigmaMeasureState = field(default_factory=SigmaMeasureState)
    main_tariff_rows: tuple[SigmaRawRow, ...] = ()
    error_text: str | None = None

    @property
    def is_technical_failure(self) -> bool:
        return self.status in {"timeout", "http_error", "transport_error", "fetch_error", "parse_error"}

    @property
    def emoji_flags(self) -> tuple[str, ...]:
        flags: list[str] = []
        if self.protective.is_positive:
            flags.append(SIGMA_PROTECTIVE_EMOJI)
        if self.excise.is_positive:
            flags.append(SIGMA_EXCISE_EMOJI)
        if self.mandatory_marking.has_attention:
            flags.append(SIGMA_MANDATORY_MARKING_EMOJI)
        if self.customs_fee.is_positive:
            flags.append(PP1637_CUSTOMS_FEE_EMOJI)
        return tuple(flags)

    @property
    def eco_attention_prefix(self) -> str:
        return SIGMA_ECO_ATTENTION_PREFIX if self.eco.has_attention else ""

    @property
    def raw_text_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        for row in self.main_tariff_rows:
            label = (row.label or row.row_id).strip()
            value_text = row.value_text
            if label and value_text:
                lines.append(f"{label}: {value_text}")
            elif value_text:
                lines.append(value_text)
            elif label:
                lines.append(label)
        return tuple(lines)

    @property
    def raw_text_dump(self) -> str:
        return "\n".join(self.raw_text_lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "query_date": self.query_date,
            "status": self.status,
            "source_url": self.source_url,
            "item_name": self.item_name,
            "duty_text": self.duty_text,
            "vat_text": self.vat_text,
            "customs_fee": self.customs_fee.to_dict(),
            "protective": self.protective.to_dict(),
            "excise": self.excise.to_dict(),
            "mandatory_marking": self.mandatory_marking.to_dict(),
            "eco": self.eco.to_dict(),
            "main_tariff_rows": [row.to_dict() for row in self.main_tariff_rows],
            "error_text": self.error_text,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SigmaPaycalcResult":
        return cls(
            code=normalize_code_10(str(payload.get("code") or "")),
            query_date=str(payload.get("query_date") or "").strip(),
            status=str(payload.get("status") or "blank").strip(),
            source_url=str(payload.get("source_url") or "").strip(),
            item_name=str(payload.get("item_name")).strip() if payload.get("item_name") is not None else None,
            duty_text=str(payload.get("duty_text")).strip() if payload.get("duty_text") is not None else None,
            vat_text=str(payload.get("vat_text")).strip() if payload.get("vat_text") is not None else None,
            customs_fee=SigmaMeasureState.from_dict(
                payload.get("customs_fee") if isinstance(payload.get("customs_fee"), dict) else None
            ),
            protective=SigmaMeasureState.from_dict(
                payload.get("protective") if isinstance(payload.get("protective"), dict) else None
            ),
            excise=SigmaMeasureState.from_dict(
                payload.get("excise") if isinstance(payload.get("excise"), dict) else None
            ),
            mandatory_marking=SigmaMeasureState.from_dict(
                payload.get("mandatory_marking") if isinstance(payload.get("mandatory_marking"), dict) else None
            ),
            eco=SigmaMeasureState.from_dict(payload.get("eco") if isinstance(payload.get("eco"), dict) else None),
            main_tariff_rows=tuple(
                SigmaRawRow.from_dict(item)
                for item in (payload.get("main_tariff_rows") if isinstance(payload.get("main_tariff_rows"), list) else [])
                if isinstance(item, dict)
            ),
            error_text=str(payload.get("error_text")).strip() if payload.get("error_text") is not None else None,
        )


@dataclass(frozen=True)
class SigmaPriceSection:
    key: str
    title: str
    status: str
    emoji: str | None
    short_value: str | None
    detail_text: str | None
    calc_values: tuple[str, ...]
    display_line: str | None
    extra_lines: tuple[str, ...] = ()
    sigma_line: str | None = None
    contributes_to_leading_emoji: bool = False

    @property
    def is_visible(self) -> bool:
        return bool(self.display_line)

    def render_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        if self.display_line:
            lines.append(self.display_line)
        lines.extend(line for line in self.extra_lines if line)
        if self.sigma_line:
            lines.append(self.sigma_line)
        return tuple(lines)


@dataclass(frozen=True)
class SigmaPriceSnapshot:
    code: str
    source_url: str
    query_date: str
    item_name: str | None
    sections: tuple[SigmaPriceSection, ...]
    leading_emojis: tuple[str, ...]
    optional_lines: tuple[str, ...]
    warning_lines: tuple[str, ...]
    is_partial: bool
    is_technical_failure: bool


@dataclass(frozen=True)
class SigmaEcoGroup:
    group_no: str | None
    group_title: str | None
    group_text: str | None


__all__ = [
    "SigmaConfig",
    "SigmaEcoGroup",
    "SigmaMeasureState",
    "SigmaPaycalcResult",
    "SigmaPriceSection",
    "SigmaPriceSnapshot",
    "SigmaRawRow",
]
