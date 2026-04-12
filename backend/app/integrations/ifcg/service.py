from __future__ import annotations

import re

from ...integrations.ai.service import AIIntegrationService
from .client import IfcgClient
from .judge import build_ifcg_v2_payload, run_ifcg_judge
from .models import (
    IfcgAnalysisResult,
    IfcgDiscoveryInput,
    IfcgDiscoveryOutput,
    IfcgInput,
    IfcgOutput,
    IfcgQueryPlan,
    IfcgSearchResult,
)
from .parser import parse_search_page
from .query_builder import build_focused_queries
from .query_planner import IfcgLlmQueryPlanner, build_fallback_query_plan
from .ranking import build_code_summaries
from .reporting import build_ifcg_long_lines, build_ifcg_short_line


class IfcgService:
    def __init__(
        self,
        *,
        client: IfcgClient,
        query_planner: IfcgLlmQueryPlanner | None = None,
        ai_service: AIIntegrationService | None = None,
        planner_profile: str = "text_cheap",
        judge_profile: str = "text_cheap",
        max_broad_queries: int = 5,
        max_focused_queries: int = 3,
        max_codes: int = 5,
        min_secondary_group_share_percent: int = 5,
        branch_share_percent: int = 50,
        branch_min_records: int = 5,
        judge_enabled: bool = True,
    ) -> None:
        self._client = client
        self._ai_service = ai_service
        self._query_planner = query_planner or (
            IfcgLlmQueryPlanner(ai_service=ai_service, profile=planner_profile)
            if ai_service is not None
            else None
        )
        self._judge_profile = judge_profile
        self._judge_enabled = judge_enabled
        self._max_broad_queries = max(1, max_broad_queries)
        self._max_focused_queries = max(1, max_focused_queries)
        self._max_codes = max(1, max_codes)
        self._min_secondary_group_share_percent = max(1, int(min_secondary_group_share_percent))
        self._branch_share_percent = max(1, int(branch_share_percent))
        self._branch_min_records = max(1, int(branch_min_records))
        self._cache: dict[str, IfcgSearchResult] = {}

    @staticmethod
    def _collapse_spaces(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _normalize_string_list(value: object, *, max_items: int = 12) -> list[str]:
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, tuple):
            raw_items = list(value)
        elif value is None:
            raw_items = []
        else:
            raw_items = [value]
        items: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            normalized = IfcgService._collapse_spaces(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            items.append(normalized[:240])
            if len(items) >= max_items:
                break
        return items

    @classmethod
    def build_discovery_input_from_ocr_payload(cls, ocr_payload: dict[str, object] | None) -> IfcgDiscoveryInput:
        payload = ocr_payload if isinstance(ocr_payload, dict) else {}
        text_cn = cls._collapse_spaces(payload.get("text_cn"))
        text_ru = cls._collapse_spaces(payload.get("text_ru"))
        source_description = cls._collapse_spaces(payload.get("source_description"))
        ocr_text = cls._collapse_spaces(payload.get("ocr_text"))
        image_description = cls._collapse_spaces(payload.get("image_description"))
        context_text = "\n".join(
            part for part in (text_cn, text_ru, source_description, ocr_text, image_description) if part
        ).strip()
        structured_attributes = payload.get("structured_attributes")
        product_facts: dict[str, list[str]] = {}
        observed_materials: list[str] = []
        if isinstance(structured_attributes, dict):
            for raw_key, raw_value in structured_attributes.items():
                key = cls._collapse_spaces(raw_key)
                if not key:
                    continue
                values = cls._normalize_string_list(raw_value)
                if not values:
                    continue
                product_facts[key] = values
                if key.lower() in {"material", "materials", "материал", "материалы", "состав", "composition"}:
                    observed_materials.extend(values)
        source_text = text_ru or text_cn or source_description
        item_name = source_text
        return IfcgDiscoveryInput(
            item_name=item_name,
            context_text=context_text,
            source_text=source_text,
            observed_materials=tuple(dict.fromkeys(observed_materials))[:8],
            product_facts=product_facts,
        )

    async def _fetch(self, query) -> IfcgSearchResult:
        cached = self._cache.get(query.cache_key)
        if cached is not None:
            return cached
        html_text, http_status, url = await self._client.fetch_search_html(query)
        parsed = parse_search_page(
            html_text=html_text,
            query=query,
            source_url=url,
            http_status=http_status,
        )
        self._cache[query.cache_key] = parsed
        return parsed

    async def _plan_broad_queries(self, search_input: IfcgInput) -> IfcgQueryPlan:
        planner = self._query_planner
        if planner is None:
            return build_fallback_query_plan(search_input, max_queries=self._max_broad_queries)

        try:
            plan = await planner.plan(search_input, max_queries=self._max_broad_queries)
        except Exception as exc:
            return build_fallback_query_plan(
                search_input,
                max_queries=self._max_broad_queries,
                warning=f"Planner failed: {type(exc).__name__}",
            )

        if not isinstance(plan, IfcgQueryPlan) or not plan.broad_queries:
            return build_fallback_query_plan(
                search_input,
                max_queries=self._max_broad_queries,
                warning="Planner returned no usable broad queries",
            )
        return plan

    def _discover_focus_filters(
        self,
        *,
        broad_searches: tuple[IfcgSearchResult, ...],
    ) -> list[tuple[str, str]]:
        ranked: dict[str, tuple[int, int, str]] = {}
        for search in broad_searches:
            for bucket in search.clarifications:
                if bucket.scope != "group":
                    continue
                previous = ranked.get(bucket.code)
                candidate = (bucket.share_percent, bucket.record_count, search.query.text)
                if previous is None or candidate > previous:
                    ranked[bucket.code] = candidate

        ordered = sorted(
            ranked.items(),
            key=lambda item: (item[1][0], item[1][1]),
            reverse=True,
        )
        focus_pairs: list[tuple[str, str]] = []
        for index, (group_code, (share, _records, query_text)) in enumerate(ordered):
            if index > 0 and share < self._min_secondary_group_share_percent:
                continue
            focus_pairs.append((group_code, query_text))
            if len(focus_pairs) >= self._max_focused_queries:
                break
        return focus_pairs

    @staticmethod
    def _discover_allowed_codes(focused_searches: tuple[IfcgSearchResult, ...]) -> set[str] | None:
        allowed_codes: set[str] = set()
        for search in focused_searches:
            for section in search.stat_sections:
                if section.scope == "code" and len(section.code) == 10:
                    allowed_codes.add(section.code)
        return allowed_codes or None

    def _build_search_trace(self, searches: tuple[IfcgSearchResult, ...]) -> list[dict[str, object]]:
        trace_rows: list[dict[str, object]] = []
        for search in searches:
            trace_rows.append(
                {
                    "query": search.query.text,
                    "group_filter": search.query.group_filter,
                    "kind": search.query.kind,
                    "status": search.status,
                    "http_status": search.http_status,
                    "tree_hits": len(search.tree_hits),
                    "note_hits": len(search.note_hits),
                    "predecision_hits": len(search.predecision_hits),
                    "declaration_examples": len(search.declaration_examples),
                    "clarifications": [
                        {
                            "code": bucket.code,
                            "record_count": bucket.record_count,
                            "share_percent": bucket.share_percent,
                            "scope": bucket.scope,
                            "anchor": bucket.anchor,
                            "title": bucket.title,
                        }
                        for bucket in search.clarifications[:12]
                    ],
                    "stat_sections": [
                        {
                            "anchor": section.anchor,
                            "title": section.title,
                            "code": section.code,
                            "scope": section.scope,
                            "description": section.description,
                            "record_count": section.record_count,
                            "share_percent": section.share_percent,
                            "examples": [
                                {
                                    "code": example.code,
                                    "description": example.description,
                                }
                                for example in section.examples[:3]
                            ],
                        }
                        for section in search.stat_sections[:12]
                    ],
                    "url": search.url,
                }
            )
        return trace_rows

    def _build_query_map_trace(self, broad_searches: tuple[IfcgSearchResult, ...]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for search in broad_searches:
            rows.append(
                {
                    "query": search.query.text,
                    "groups": [
                        {
                            "code": bucket.code,
                            "record_count": bucket.record_count,
                            "share_percent": bucket.share_percent,
                        }
                        for bucket in search.clarifications
                        if bucket.scope == "group"
                    ][:8],
                    "stat_sections": [
                        {
                            "code": section.code,
                            "scope": section.scope,
                            "record_count": section.record_count,
                            "share_percent": section.share_percent,
                            "example_count": len(section.examples),
                        }
                        for section in search.stat_sections[:8]
                    ],
                }
            )
        return rows

    async def analyze_raw(self, search_input: IfcgInput) -> IfcgAnalysisResult:
        query_plan = await self._plan_broad_queries(search_input)
        broad_queries = query_plan.broad_queries
        if not broad_queries:
            error = "ifcg_llm_query_plan_unavailable"
            trace = {
                "used": False,
                "error": error,
                "query_plan": {
                    "planner_name": query_plan.planner_name,
                    "rationale": query_plan.rationale,
                    "warnings": list(query_plan.warnings),
                    "fallback_used": query_plan.fallback_used,
                },
                "broad_queries": [],
                "focused_queries": [],
                "search_statuses": [],
                "top_codes": [],
            }
            return IfcgAnalysisResult(
                used=False,
                query_plan=query_plan,
                broad_queries=(),
                focused_queries=(),
                searches=(),
                top_codes=(),
                operator_short_line="IFCG: LLM не сформировал корректные запросы",
                operator_long_lines=("IFCG: broad-запросы не построены, анализ остановлен.",),
                error=error,
                trace=trace,
            )

        broad_searches = tuple([await self._fetch(query) for query in broad_queries])
        focus_pairs = self._discover_focus_filters(broad_searches=broad_searches)
        focused_queries = tuple(
            query
            for group_code, base_query in focus_pairs
            for query in build_focused_queries(
                base_query=base_query,
                focus_codes=[group_code],
                max_queries=1,
            )
        )
        focused_searches = tuple([await self._fetch(query) for query in focused_queries])

        searches = broad_searches + focused_searches
        allowed_codes = self._discover_allowed_codes(focused_searches)
        top_codes = build_code_summaries(
            search_input=search_input,
            searches=searches,
            allowed_codes=allowed_codes,
            max_codes=self._max_codes,
        )
        short_line = build_ifcg_short_line(top_codes)
        long_lines = build_ifcg_long_lines(top_codes)
        used = any(
            search.tree_hits
            or search.note_hits
            or search.predecision_hits
            or search.clarifications
            or search.stat_sections
            for search in searches
        )
        trace = {
            "used": used,
            "query_plan": {
                "planner_name": query_plan.planner_name,
                "rationale": query_plan.rationale,
                "warnings": list(query_plan.warnings),
                "fallback_used": query_plan.fallback_used,
            },
            "query_map": self._build_query_map_trace(broad_searches),
            "search_statuses": self._build_search_trace(searches),
            "top_codes": [
                {
                    "code": item.code,
                    "support_level": item.support_level,
                    "support_score": item.support_score,
                    "signal_type": item.signal_type,
                    "relation_flag": item.relation_flag,
                    "clarification_records": item.clarification_records,
                    "clarification_share_percent": item.clarification_share_percent,
                    "total_examples": item.total_examples,
                    "matched_candidate": item.matched_candidate,
                    "why": item.why,
                }
                for item in top_codes
            ],
        }
        return IfcgAnalysisResult(
            used=used,
            query_plan=query_plan,
            broad_queries=broad_queries,
            focused_queries=focused_queries,
            searches=searches,
            top_codes=top_codes,
            operator_short_line=short_line,
            operator_long_lines=long_lines,
            error="",
            trace=trace,
        )

    @staticmethod
    def _discover_group_codes(result: IfcgAnalysisResult) -> tuple[str, ...]:
        seen: set[str] = set()
        groups: list[str] = []
        for item in result.top_codes:
            code_group = item.code[:4] if len(item.code) >= 4 else ""
            if code_group and code_group not in seen:
                seen.add(code_group)
                groups.append(code_group)
            for source_group in item.source_groups:
                normalized = re.sub(r"\D", "", source_group or "")
                group_code = normalized[:4] if len(normalized) >= 4 else ""
                if group_code and group_code not in seen:
                    seen.add(group_code)
                    groups.append(group_code)
        return tuple(groups[:6])

    async def analyze_discovery(self, discovery_input: IfcgDiscoveryInput) -> IfcgDiscoveryOutput:
        if not any(
            (
                self._collapse_spaces(discovery_input.item_name),
                self._collapse_spaces(discovery_input.context_text),
                self._collapse_spaces(discovery_input.source_text),
            )
        ):
            return IfcgDiscoveryOutput(
                status="empty",
                summary="IFCG discovery: пустой вход.",
                suggested_groups=(),
                suggested_codes=(),
                broad_queries=(),
                top_codes=(),
                operator_short_line="IFCG discovery: пустой вход",
                operator_long_lines=("IFCG discovery не запускался: нет текстового контекста.",),
                used=False,
                warnings=("empty_input",),
                error="empty_input",
                trace={"skipped": True},
            )

        search_input = IfcgInput(
            item_name=self._collapse_spaces(discovery_input.item_name or discovery_input.source_text),
            selected_code="",
            candidate_codes=(),
            context_text=self._collapse_spaces(discovery_input.context_text or discovery_input.source_text),
            decision_rationale="",
            observed_materials=tuple(self._normalize_string_list(discovery_input.observed_materials, max_items=8)),
            product_facts={
                self._collapse_spaces(key): self._normalize_string_list(values)
                for key, values in discovery_input.product_facts.items()
                if self._collapse_spaces(key) and self._normalize_string_list(values)
            },
        )
        result = await self.analyze_raw(search_input)
        suggested_codes = tuple(item.code for item in result.top_codes[:5] if len(item.code) == 10)
        suggested_groups = self._discover_group_codes(result)
        warnings = tuple(result.query_plan.warnings) if result.query_plan is not None else ()
        if result.error:
            status = "error"
            summary = "IFCG discovery завершился с ошибкой."
        elif result.top_codes:
            status = "ready"
            summary = result.operator_short_line or "IFCG discovery собрал дополнительные коды."
        else:
            status = "no_signal"
            summary = "IFCG discovery не нашел устойчивых кодов."
        trace = dict(result.trace)
        trace.update(
            {
                "suggested_groups": list(suggested_groups),
                "suggested_codes": list(suggested_codes),
            }
        )
        return IfcgDiscoveryOutput(
            status=status,
            summary=summary,
            suggested_groups=suggested_groups,
            suggested_codes=suggested_codes,
            broad_queries=tuple(query.text for query in result.broad_queries),
            top_codes=result.top_codes,
            operator_short_line=result.operator_short_line,
            operator_long_lines=result.operator_long_lines,
            used=result.used,
            warnings=warnings,
            error=result.error,
            trace=trace,
        )

    def _classify_result(self, *, search_input: IfcgInput, result: IfcgAnalysisResult) -> tuple[str, str, bool]:
        if not result.used or not result.top_codes:
            return "no_signal", "IFCG не дал устойчивой практики по выбранным связкам слов.", False

        selected_code = re.sub(r"\D", "", search_input.selected_code or "")
        top = result.top_codes[0]
        top_group = top.code[:4]
        selected_group = selected_code[:4] if len(selected_code) >= 4 else ""
        candidate_codes = {
            re.sub(r"\D", "", code or "")
            for code in search_input.candidate_codes
            if len(re.sub(r"\D", "", code or "")) == 10
        }
        candidate_groups = {code[:4] for code in candidate_codes if len(code) >= 4}

        if top.code == selected_code:
            return "confirm", "IFCG подтверждает текущий код по практике декларирования.", False

        if top_group and top_group == selected_group:
            return "confirm", "IFCG подтверждает текущую товарную ветку, но leaf-детализация еще спорная.", False

        if top.code in candidate_codes:
            return "mixed", "IFCG усиливает альтернативный код, уже найденный основным подбором.", False

        if top_group and top_group in candidate_groups:
            return "mixed", "IFCG усиливает альтернативную ветку, уже найденную основным подбором.", False

        stable_signal = bool(
            top.clarification_records >= max(1, self._branch_min_records)
            or top.clarification_share_percent >= max(10, self._branch_share_percent)
            or top.total_examples >= 3
        )
        if not stable_signal:
            return "no_signal", "IFCG нашел только слабые или единичные совпадения без устойчивой статистики.", False

        dangerous_branch = bool(
            top_group
            and top_group != selected_group
            and top_group not in candidate_groups
            and top.clarification_records >= max(1, self._branch_min_records)
            and top.clarification_share_percent >= max(10, self._branch_share_percent)
        )
        if dangerous_branch:
            return "branch", "IFCG устойчиво уводит товар в другую 4-значную ветку.", True

        return "mixed", "IFCG дает практику, но сигнал пока смешанный и требует перепроверки.", False

    @staticmethod
    def _has_confirming_top_code(*, search_input: IfcgInput, result: IfcgAnalysisResult) -> bool:
        selected_code = re.sub(r"\D", "", search_input.selected_code or "")
        selected_group = selected_code[:4] if len(selected_code) >= 4 else ""
        candidate_codes = {
            re.sub(r"\D", "", code or "")
            for code in search_input.candidate_codes
            if len(re.sub(r"\D", "", code or "")) == 10
        }
        candidate_groups = {code[:4] for code in candidate_codes if len(code) >= 4}

        for item in result.top_codes:
            if item.code == selected_code:
                return True
            if item.relation_flag in {"same_leaf", "same_branch_other_leaf"}:
                return True
            if item.matched_candidate:
                return True
            if selected_group and item.code.startswith(selected_group):
                return True
            if candidate_groups and item.code[:4] in candidate_groups:
                return True
        return False

    async def analyze(self, search_input: IfcgInput) -> IfcgOutput:
        result = await self.analyze_raw(search_input)
        if result.error == "ifcg_llm_query_plan_unavailable":
            return IfcgOutput(
                status="no_signal",
                summary="IFCG не запущен: LLM не сформировал корректные запросы.",
                selected_code=search_input.selected_code,
                candidate_codes=search_input.candidate_codes,
                top_codes=result.top_codes,
                operator_short_line=result.operator_short_line,
                operator_long_lines=result.operator_long_lines,
                dangerous_signal=False,
                rerun_recommended=False,
                used=result.used,
                query_plan=result.query_plan,
                judge_result=None,
                error=result.error,
                trace=result.trace,
            )

        status, summary, dangerous_signal = self._classify_result(search_input=search_input, result=result)
        judge_result = None
        if self._judge_enabled and self._ai_service is not None and result.error != "ifcg_llm_query_plan_unavailable":
            judge_payload = build_ifcg_v2_payload(
                search_input=search_input,
                result=result,
                initial_status=status,
                initial_summary=summary,
            )
            judge_result = await run_ifcg_judge(
                ai_service=self._ai_service,
                payload=judge_payload,
                profile=self._judge_profile,
            )
            if judge_result is not None:
                allow_confirm_override = not (
                    judge_result.status == "confirm"
                    and not self._has_confirming_top_code(search_input=search_input, result=result)
                )
                if allow_confirm_override:
                    status = judge_result.status
                    dangerous_signal = judge_result.dangerous_signal
                    if judge_result.operator_summary:
                        summary = judge_result.operator_summary

        rerun_recommended = bool(
            dangerous_signal and (judge_result.rerun_recommended if judge_result is not None else status == "branch")
        )
        trace = dict(result.trace)
        trace.update(
            {
                "status": status,
                "summary": summary,
                "dangerous_signal": dangerous_signal,
                "rerun_recommended": rerun_recommended,
                "judge_result": judge_result.raw if judge_result is not None else {},
            }
        )
        return IfcgOutput(
            status=status,  # type: ignore[arg-type]
            summary=summary,
            selected_code=search_input.selected_code,
            candidate_codes=search_input.candidate_codes,
            top_codes=result.top_codes,
            operator_short_line=result.operator_short_line,
            operator_long_lines=result.operator_long_lines,
            dangerous_signal=dangerous_signal,
            rerun_recommended=rerun_recommended,
            used=result.used,
            query_plan=result.query_plan,
            judge_result=judge_result,
            error=result.error,
            trace=trace,
        )
