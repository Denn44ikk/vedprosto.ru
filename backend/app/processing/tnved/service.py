from __future__ import annotations

from ...integrations.ai.service import AIIntegrationService
from .compaction import compact_image_description_for_tnved_assembly
from .criteria import extract_candidate_criteria_map, extract_main_criteria
from .models import TnvedCandidate, TnvedInput, TnvedOutput
from .parsing import (
    extract_candidate_codes,
    extract_candidate_probability_map,
    extract_clarification_questions,
    extract_candidate_reason_map,
    extract_observed_attributes,
    merge_product_facts_with_observed_attributes,
    normalize_tnved_payload,
    parse_confidence_percent,
)
from .prompts import build_tnved_assembly_prompt


class TnvedService:
    def __init__(
        self,
        *,
        ai_service: AIIntegrationService,
        profile: str = "text_exp",
        max_tokens: int = 1800,
        use_fallback: bool = True,
    ) -> None:
        self._ai_service = ai_service
        self._profile = profile
        self._max_tokens = max(600, int(max_tokens))
        self._use_fallback = use_fallback

    async def analyze(self, run_input: TnvedInput) -> TnvedOutput:
        merged_product_facts = merge_product_facts_with_observed_attributes(
            run_input.product_facts,
            run_input.observed_attributes,
        )
        compacted_image_description = compact_image_description_for_tnved_assembly(
            item_name=run_input.item_name,
            image_description=run_input.image_description,
            product_facts=merged_product_facts,
        )
        prompt = build_tnved_assembly_prompt(
            run_input=run_input,
            compacted_image_description=compacted_image_description,
        )
        raw_payload = await self._ai_service.text_json(
            profile=self._profile,
            prompt=prompt,
            use_fallback=self._use_fallback,
            max_tokens=self._max_tokens,
        )
        if not isinstance(raw_payload, dict):
            raw_payload = {}

        normalized = normalize_tnved_payload(raw_payload)
        selected_code = normalized["tnved"]
        selected_description = normalized["tnved_description"]
        selection_rationale = normalized["selection_rationale"]
        error_reason = normalized["error_reason"]
        confidence_percent = parse_confidence_percent(raw_payload)
        observed_attributes = extract_observed_attributes(raw_payload)
        merged_product_facts = merge_product_facts_with_observed_attributes(
            merged_product_facts,
            observed_attributes,
        )
        candidate_codes = extract_candidate_codes(raw_payload)
        probability_map = extract_candidate_probability_map(raw_payload)
        reason_map = extract_candidate_reason_map(raw_payload)
        criteria_map = extract_candidate_criteria_map(raw_payload)
        decisive_criteria = extract_main_criteria(raw_payload)
        clarification_questions = extract_clarification_questions(
            raw_payload,
            decisive_criteria=decisive_criteria,
            max_items=3,
        )

        ifcg_codes = set(run_input.ifcg_discovery.suggested_codes) if run_input.ifcg_discovery is not None else set()
        ordered_candidate_codes = (
            ([selected_code] if selected_code else [])
            + candidate_codes
            + list(run_input.ifcg_discovery.suggested_codes if run_input.ifcg_discovery is not None else ())
        )
        candidates: list[TnvedCandidate] = []
        seen: set[str] = set()
        for code in ordered_candidate_codes:
            if not code or code in seen:
                continue
            seen.add(code)
            candidates.append(
                TnvedCandidate(
                    code=code,
                    probability_percent=probability_map.get(code),
                    reason=reason_map.get(code, ""),
                    source="ifcg" if code in ifcg_codes else "tnved",
                    criteria=criteria_map.get(code, decisive_criteria if code == selected_code else criteria_map.get(code))
                    or decisive_criteria,
                )
            )

        return TnvedOutput(
            selected_code=selected_code,
            selected_description=selected_description,
            selection_rationale=selection_rationale,
            confidence_percent=confidence_percent,
            error_reason=error_reason,
            candidates=tuple(candidates),
            decisive_criteria=decisive_criteria,
            clarification_questions=clarification_questions,
            product_facts=merged_product_facts,
            observed_attributes=observed_attributes,
            compacted_image_description=compacted_image_description,
            ifcg_discovery_used=run_input.ifcg_discovery is not None,
            raw_payload=raw_payload,
            trace={
                "profile": self._profile,
                "prompt_chars": len(prompt),
                "selected_code": selected_code,
                "candidate_count": len(candidates),
                "ifcg_discovery_used": run_input.ifcg_discovery is not None,
            },
        )
