from __future__ import annotations

import re

from ...storage.knowledge.catalogs import normalize_code_10
from ...storage.knowledge.indexing import TnvedVbdIndexingService
from ...storage.knowledge.vector_db import KnowledgeVectorDbService, VectorDbHit
from .models import TnvedVbdHit, TnvedVbdInput, TnvedVbdOutput


def _collapse_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


class TnvedVbdService:
    def __init__(
        self,
        *,
        indexing_service: TnvedVbdIndexingService,
        vector_db_service: KnowledgeVectorDbService,
        max_reference_hits: int = 5,
        max_example_hits: int = 3,
    ) -> None:
        self._indexing_service = indexing_service
        self._vector_db_service = vector_db_service
        self._max_reference_hits = max(1, int(max_reference_hits))
        self._max_example_hits = max(1, int(max_example_hits))

    def analyze(self, run_input: TnvedVbdInput) -> TnvedVbdOutput:
        selected_code = normalize_code_10(run_input.selected_code)
        candidate_codes = self._normalize_codes(run_input.candidate_codes)
        if not selected_code:
            return TnvedVbdOutput(
                status="skipped",
                verification_status="skipped",
                selected_code="",
                summary="Код ТН ВЭД еще не выбран.",
                note="VBD-проверка запускается после финального выбора кода.",
                warnings=tuple(),
                index_status="idle",
                trace={"selected_code": "", "candidate_codes": candidate_codes},
            )

        index_payload = self._indexing_service.load_index_payload()
        manifest = index_payload.get("manifest") if isinstance(index_payload.get("manifest"), dict) else {}
        index_status = str(manifest.get("status", "")).strip() or "empty"
        reference_chunk_count = int(manifest.get("reference_chunk_count", 0) or 0)
        example_chunk_count = int(manifest.get("example_chunk_count", 0) or 0)
        if reference_chunk_count <= 0 and example_chunk_count <= 0:
            return TnvedVbdOutput(
                status="unavailable",
                verification_status="unavailable",
                selected_code=selected_code,
                summary=f"Для кода {selected_code} пока нет документов в ВБД.",
                note=(
                    "Добавьте файлы в папки VBD reference/examples и пересоберите индекс. "
                    f"Текущий каталог: {self._indexing_service.index_dir.parent}"
                ),
                product_facts=tuple(self._build_product_facts(run_input)),
                warnings=("vbd_empty",),
                index_status=index_status,
                trace={
                    "selected_code": selected_code,
                    "candidate_codes": candidate_codes,
                    "reference_chunks": reference_chunk_count,
                    "example_chunks": example_chunk_count,
                    "vector_backend": manifest.get("vector_backend", "chroma"),
                },
            )

        reference_hits = self._find_code_hits(
            collection_name="reference_chunks",
            selected_code=selected_code,
            top_k=self._max_reference_hits,
        )
        example_hits = self._find_code_hits(
            collection_name="example_chunks",
            selected_code=selected_code,
            top_k=self._max_example_hits,
        )
        verification_status = self._determine_verification_status(
            selected_code=selected_code,
            reference_hits=reference_hits,
            example_hits=example_hits,
        )
        alternative_codes: list[str] = []
        return TnvedVbdOutput(
            status="ready",
            verification_status=verification_status,
            selected_code=selected_code,
            summary=self._build_summary(
                selected_code=selected_code,
                verification_status=verification_status,
                reference_hits=reference_hits,
                example_hits=example_hits,
                alternative_codes=alternative_codes,
            ),
            note=self._build_note(verification_status=verification_status, alternative_codes=alternative_codes),
            product_facts=tuple(self._build_product_facts(run_input)),
            reference_hits=tuple(self._convert_hits(reference_hits)),
            example_hits=tuple(self._convert_hits(example_hits)),
            alternative_codes=tuple(alternative_codes),
            warnings=self._build_warnings(verification_status=verification_status),
            index_status=index_status,
            trace={
                "selected_code": selected_code,
                "candidate_codes": candidate_codes,
                "mode": "exact_selected_code_lookup",
                "queries": [selected_code],
                "reference_hits": len(reference_hits),
                "example_hits": len(example_hits),
                "reference_chunk_count": reference_chunk_count,
                "example_chunk_count": example_chunk_count,
                "vector_backend": manifest.get("vector_backend", "chroma"),
            },
        )

    @staticmethod
    def _normalize_codes(values: tuple[str, ...] | list[str] | object) -> list[str]:
        if isinstance(values, (list, tuple)):
            raw_values = list(values)
        elif values:
            raw_values = [values]
        else:
            raw_values = []
        out: list[str] = []
        seen: set[str] = set()
        for value in raw_values:
            code = normalize_code_10(value)
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
        return out

    def _build_queries(self, run_input: TnvedVbdInput) -> list[str]:
        product_facts = self._build_product_facts(run_input)
        parts = [
            normalize_code_10(run_input.selected_code),
            _collapse_spaces(run_input.item_name),
            _collapse_spaces(run_input.selected_description),
            _collapse_spaces(run_input.context_text)[:1000],
            "; ".join(product_facts[:6]),
            " ".join(self._normalize_codes(run_input.candidate_codes)[:4]),
        ]
        return [part for part in parts if part]

    @staticmethod
    def _build_product_facts(run_input: TnvedVbdInput) -> list[str]:
        facts: list[str] = []
        for raw_key, raw_values in run_input.product_facts.items():
            key = _collapse_spaces(raw_key)
            if not key:
                continue
            values = [
                _collapse_spaces(value)
                for value in (raw_values if isinstance(raw_values, list) else [raw_values])
                if _collapse_spaces(value)
            ]
            if not values:
                continue
            facts.append(f"{key}: {', '.join(values[:4])}")
        return facts[:8]

    def _find_code_hits(self, *, collection_name: str, selected_code: str, top_k: int) -> list[VectorDbHit]:
        chunks = self._vector_db_service.load_collection(
            index_dir=self._indexing_service.index_dir,
            collection_name=collection_name,
        )
        hits: list[VectorDbHit] = []
        for chunk in chunks:
            score = self._selected_code_hit_score(chunk, selected_code)
            if score <= 0:
                continue
            hits.append(
                VectorDbHit(
                    chunk_id=chunk.chunk_id,
                    source_path=chunk.source_path,
                    relative_path=chunk.relative_path,
                    source_kind=chunk.source_kind,
                    document_type=chunk.document_type,
                    section_context=chunk.section_context,
                    text=chunk.text,
                    score=score,
                    mentioned_codes=self._hit_mentioned_codes(chunk, selected_code),
                )
            )
        hits.sort(key=lambda item: (-item.score, item.relative_path, item.chunk_id))
        return hits[: max(1, int(top_k))]

    @staticmethod
    def _hit_mentioned_codes(chunk: object, selected_code: str) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for item in getattr(chunk, "mentioned_codes", ()) or ():
            code = normalize_code_10(item)
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
        if selected_code and selected_code not in seen:
            out.insert(0, selected_code)
        return tuple(out)

    @staticmethod
    def _selected_code_hit_score(chunk: object, selected_code: str) -> float:
        mentioned_codes = tuple(
            code
            for code in (normalize_code_10(item) for item in getattr(chunk, "mentioned_codes", ()) or ())
            if code
        )
        score = 0.0
        if selected_code in mentioned_codes:
            score += 100.0

        text = str(getattr(chunk, "text", "") or "")
        code_pattern = re.compile(r"(?<!\d)" + r"[\s./-]*".join(re.escape(char) for char in selected_code) + r"(?!\d)")
        occurrences = len(code_pattern.findall(text))
        if occurrences:
            score += min(30.0, 10.0 + occurrences * 2.0)

        if score > 0 and str(getattr(chunk, "source_kind", "")).strip() == "reference":
            score += 0.8
        return round(score, 4) if score > 0 else 0.0

    @staticmethod
    def _determine_verification_status(
        *,
        selected_code: str,
        reference_hits: list[VectorDbHit],
        example_hits: list[VectorDbHit],
    ) -> str:
        if reference_hits or example_hits:
            return "confirmed"
        return "no_hits"

    @staticmethod
    def _collect_alternative_codes(
        *,
        selected_code: str,
        reference_hits: list[VectorDbHit],
        example_hits: list[VectorDbHit],
    ) -> list[str]:
        out: list[str] = []
        seen: set[str] = {selected_code}
        for hit in [*reference_hits, *example_hits]:
            for code in hit.mentioned_codes:
                normalized = normalize_code_10(code)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                out.append(normalized)
                if len(out) >= 6:
                    return out
        return out

    @staticmethod
    def _convert_hits(hits: list[VectorDbHit]) -> list[TnvedVbdHit]:
        return [
            TnvedVbdHit(
                chunk_id=hit.chunk_id,
                source_path=hit.source_path,
                relative_path=hit.relative_path,
                source_kind=hit.source_kind,
                document_type=hit.document_type,
                section_context=hit.section_context,
                text=hit.text,
                score=hit.score,
                mentioned_codes=hit.mentioned_codes,
            )
            for hit in hits
        ]

    @staticmethod
    def _build_summary(
        *,
        selected_code: str,
        verification_status: str,
        reference_hits: list[VectorDbHit],
        example_hits: list[VectorDbHit],
        alternative_codes: list[str],
    ) -> str:
        if verification_status == "confirmed":
            return (
                f"Код {selected_code} найден в VBD: "
                f"{len(reference_hits)} фрагм. из документов и {len(example_hits)} фрагм. из примеров."
            )
        if verification_status == "needs_review":
            alt_line = ", ".join(alternative_codes[:4]) if alternative_codes else "без явной альтернативы"
            return f"По VBD для {selected_code} найден конфликтующий сигнал: {alt_line}."
        if verification_status == "no_signal":
            return f"Для {selected_code} нашлись документы по товару, но без прямой привязки к коду."
        return f"В VBD нет фрагментов с кодом {selected_code}."

    @staticmethod
    def _build_note(*, verification_status: str, alternative_codes: list[str]) -> str:
        if verification_status == "confirmed":
            return "Документы из VBD можно использовать как опору для карточки товара и описания в документах."
        if verification_status == "needs_review":
            if alternative_codes:
                return "Проверьте альтернативные коды в документах и сравните их с текущим выбором."
            return "Проверьте найденные документы вручную."
        if verification_status == "no_signal":
            return "Подтверждение по документам слабое. Нужны более точные спецификации, инвойсы или описания."
        return "Добавьте документы в VBD или расширьте reference/examples для этой группы товара."

    @staticmethod
    def _build_warnings(*, verification_status: str) -> tuple[str, ...]:
        if verification_status == "needs_review":
            return ("vbd_review_required",)
        if verification_status == "no_signal":
            return ("vbd_no_signal",)
        if verification_status == "no_hits":
            return ("vbd_no_hits",)
        return tuple()
