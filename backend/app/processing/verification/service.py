from __future__ import annotations

from ...integrations.ai.service import AIIntegrationService
from ...storage.knowledge.catalogs import TnvedCatalogSnapshot, normalize_code_10
from .models import VerificationInput, VerificationOutput
from .prompts import build_repair_prompt


def _normalize_candidates(candidates: tuple[str, ...] | list[str] | object | None) -> list[str]:
    if candidates is None:
        return []
    if isinstance(candidates, str):
        raw_values = [part for part in candidates.replace(";", ",").split(",") if part.strip()]
    elif isinstance(candidates, (list, tuple)):
        raw_values = list(candidates)
    else:
        raw_values = [candidates]
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        code = normalize_code_10(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return normalized


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _find_children_in_catalog(code: str, catalog: TnvedCatalogSnapshot) -> list[str]:
    normalized = normalize_code_10(code)
    if not normalized:
        return []
    if normalized.endswith("0000"):
        return [item for item in catalog.idx6.get(normalized[:6], ()) if item != normalized and not item.endswith("0000")]
    if normalized.endswith("00"):
        return [item for item in catalog.idx8.get(normalized[:8], ()) if item != normalized and not item.endswith("00")]
    return []


def _suggest_by_prefix(raw_code: object, catalog: TnvedCatalogSnapshot) -> list[str]:
    digits = "".join(ch for ch in str(raw_code or "") if ch.isdigit())
    if len(digits) >= 8:
        by8 = list(catalog.idx8.get(digits[:8], ()))
        if by8:
            return by8[:3]
    if len(digits) >= 6:
        by6 = list(catalog.idx6.get(digits[:6], ()))
        if by6:
            return by6[:3]
    return []


def _collect_parent_codes(seed_codes: list[str], catalog: TnvedCatalogSnapshot) -> list[str]:
    parent_codes: list[str] = []
    for seed in seed_codes:
        if not seed:
            continue
        for candidate in (f"{seed[:8]}00", f"{seed[:6]}0000"):
            if candidate != seed and candidate in catalog.codes_set:
                parent_codes.append(candidate)
    return _dedupe_keep_order(parent_codes)


def _build_candidate_verbose(codes: list[str], descriptions: dict[str, str]) -> list[str]:
    verbose: list[str] = []
    for code in codes:
        description = str(descriptions.get(code, "")).strip()
        verbose.append(f"{code} ({description})" if description else code)
    return verbose


def validate_and_fix_code(
    *,
    chosen: object,
    candidates: tuple[str, ...] | list[str] | object | None,
    catalog: TnvedCatalogSnapshot | None,
) -> dict[str, object]:
    out: dict[str, object] = {
        "chosen_fixed": "",
        "candidates_fixed": (),
        "candidates_verbose": (),
        "candidate_pool_fixed": (),
        "candidate_pool_verbose": (),
        "error": "",
        "error_code": "",
    }
    candidate_norm = _normalize_candidates(candidates)
    if catalog is None or not catalog.codes_set:
        pool = _dedupe_keep_order(([normalize_code_10(chosen)] if normalize_code_10(chosen) else []) + candidate_norm)
        verbose = _build_candidate_verbose(pool[:8], {})
        out.update(
            {
                "chosen_fixed": normalize_code_10(chosen),
                "candidates_fixed": tuple(pool[:3]),
                "candidates_verbose": tuple(verbose[:3]),
                "candidate_pool_fixed": tuple(pool[:8]),
                "candidate_pool_verbose": tuple(verbose[:8]),
                "error": "catalog_unavailable",
                "error_code": "CATALOG_UNAVAILABLE",
            }
        )
        return out

    chosen_norm = normalize_code_10(chosen)
    pool_candidates: list[str] = []
    if chosen_norm:
        children = _find_children_in_catalog(chosen_norm, catalog)
        if chosen_norm in catalog.codes_set:
            if len(children) == 1:
                out["chosen_fixed"] = children[0]
                out["error"] = "Code refined to leaf from catalog"
                out["error_code"] = "LEAF_REFINED"
            elif len(children) > 1:
                out["error"] = "Code is not leaf, choose subcode"
                out["error_code"] = "NOT_LEAF"
                pool_candidates.extend(children)
            else:
                out["chosen_fixed"] = chosen_norm
        else:
            if len(children) == 1:
                out["chosen_fixed"] = children[0]
                out["error"] = "Code refined to leaf from catalog"
                out["error_code"] = "LEAF_REFINED"
            elif len(children) > 1:
                out["error"] = "Code is not leaf, choose subcode"
                out["error_code"] = "NOT_LEAF"
                pool_candidates.extend(children)
            else:
                siblings = _dedupe_keep_order(
                    [item for item in catalog.idx8.get(chosen_norm[:8], ()) if item != chosen_norm]
                    + [item for item in catalog.idx6.get(chosen_norm[:6], ()) if item != chosen_norm]
                )
                if siblings:
                    out["error"] = "Code is obsolete or missing, sibling variants suggested"
                    out["error_code"] = "OBSOLETE_OR_MISSING"
                    pool_candidates.extend(siblings)
                else:
                    out["error"] = "Code is missing and no sibling variants found"
                    out["error_code"] = "NOT_FOUND"
    elif any(ch.isdigit() for ch in str(chosen or "")):
        suggestions = _suggest_by_prefix(chosen, catalog)
        if suggestions:
            out["error"] = "Code is not 10-digit, candidates inferred by prefix"
            out["error_code"] = "NOT_10_DIGIT"
            pool_candidates.extend(suggestions)
        else:
            out["error"] = "Code is not 10-digit and no prefix candidates found"
            out["error_code"] = "NOT_10_DIGIT_NOT_FOUND"

    valid_candidates = [candidate for candidate in candidate_norm if candidate in catalog.codes_set]
    if out["chosen_fixed"]:
        pool_candidates.extend(valid_candidates)
    elif not pool_candidates:
        pool_candidates.extend(valid_candidates)
    pool_fixed = _dedupe_keep_order(pool_candidates)[:8]
    descriptions = catalog.descriptions
    out["candidate_pool_fixed"] = tuple(pool_fixed)
    out["candidate_pool_verbose"] = tuple(_build_candidate_verbose(pool_fixed, descriptions))
    out["candidates_fixed"] = tuple(pool_fixed[:3])
    out["candidates_verbose"] = tuple(_build_candidate_verbose(pool_fixed[:3], descriptions))
    return out


class VerificationService:
    def __init__(
        self,
        *,
        ai_service: AIIntegrationService,
        repair_profile: str = "text_cheap",
        use_fallback: bool = True,
    ) -> None:
        self._ai_service = ai_service
        self._repair_profile = repair_profile
        self._use_fallback = use_fallback

    async def _attempt_repair(
        self,
        *,
        item_context: str,
        original_code: str,
        candidates: list[str],
        descriptions: dict[str, str],
    ) -> tuple[str, str, str]:
        if not candidates:
            return "", "repair_skipped:no_candidates", ""
        options = []
        for code in candidates[:8]:
            desc = str(descriptions.get(code, "")).strip()
            options.append(f"- {code}: {desc[:240] if desc else 'описание отсутствует'}")
        prompt = build_repair_prompt(
            item_context=item_context.strip()[:3000],
            original_code=normalize_code_10(original_code),
            options_text="\n".join(options),
        )
        payload = await self._ai_service.text_json(
            profile=self._repair_profile,
            prompt=prompt,
            use_fallback=self._use_fallback,
            max_tokens=320,
        )
        if not isinstance(payload, dict):
            return "", "repair_llm_no_selection", ""
        selected = normalize_code_10(payload.get("tnved") or payload.get("code") or payload.get("tnved_code") or "")
        reason = str(payload.get("reason") or "").strip()[:300]
        if selected and selected in candidates:
            suffix = f":{reason[:180]}" if reason else ""
            return selected, f"repair_llm_selected{suffix}", reason
        if selected and selected not in candidates:
            return "", f"repair_llm_rejected_not_allowed:{selected}", reason
        return "", "repair_llm_no_selection", reason

    async def analyze(self, run_input: VerificationInput) -> VerificationOutput:
        validated = validate_and_fix_code(
            chosen=run_input.selected_code,
            candidates=run_input.candidate_codes,
            catalog=run_input.catalog,
        )
        chosen_fixed = str(validated.get("chosen_fixed") or "")
        candidate_pool_fixed = list(validated.get("candidate_pool_fixed") or ())
        descriptions = dict(run_input.descriptions)
        duty_rates = dict(run_input.catalog.duty_rates) if run_input.catalog is not None else {}
        if run_input.catalog is not None:
            descriptions = {**run_input.catalog.descriptions, **descriptions}

        repaired_code = ""
        repair_note = ""
        repair_reason_text = ""
        final_code = chosen_fixed
        final_status = "validated" if chosen_fixed else "needs_review"
        if run_input.enable_repair and not chosen_fixed and candidate_pool_fixed:
            repaired_code, repair_note, repair_reason_text = await self._attempt_repair(
                item_context=run_input.item_context,
                original_code=run_input.selected_code,
                candidates=candidate_pool_fixed,
                descriptions=descriptions,
            )
            if repaired_code:
                final_code = repaired_code
                final_status = "validated"
            elif validated.get("error_code"):
                final_status = "needs_review"
        elif validated.get("error_code") == "CATALOG_UNAVAILABLE" and normalize_code_10(run_input.selected_code):
            final_code = normalize_code_10(run_input.selected_code)
            final_status = "unverified"

        return VerificationOutput(
            chosen_fixed=chosen_fixed,
            candidates_fixed=tuple(validated.get("candidates_fixed") or ()),
            candidates_verbose=tuple(validated.get("candidates_verbose") or ()),
            candidate_pool_fixed=tuple(candidate_pool_fixed),
            candidate_pool_verbose=tuple(validated.get("candidate_pool_verbose") or ()),
            error=str(validated.get("error") or ""),
            error_code=str(validated.get("error_code") or ""),
            repaired_code=repaired_code,
            repair_note=repair_note,
            repair_reason_text=repair_reason_text,
            final_code=final_code,
            final_status=final_status,
            descriptions=descriptions,
            duty_rates=duty_rates,
            trace={
                "selected_code": run_input.selected_code,
                "candidate_codes": list(run_input.candidate_codes),
                "catalog_available": run_input.catalog is not None,
                "repair_enabled": run_input.enable_repair,
                "repair_note": repair_note,
            },
        )
