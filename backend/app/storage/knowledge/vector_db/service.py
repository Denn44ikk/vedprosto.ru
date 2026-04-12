from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from ..chunking import KnowledgeChunk
from .models import VectorDbHit


def _tokenize(value: object) -> list[str]:
    text = str(value or "").lower()
    return [token for token in re.findall(r"[a-zа-я0-9]{2,}", text, flags=re.IGNORECASE) if token]


def _json_dumps_list(values: tuple[str, ...] | list[str]) -> str:
    return json.dumps([str(value).strip() for value in values if str(value).strip()], ensure_ascii=False)


class KnowledgeVectorDbService:
    def __init__(
        self,
        *,
        embedding_backend: str = "default",
        embedding_model: str = "text-embedding-3-small",
        openai_api_key: str = "",
        openai_base_url: str = "",
    ) -> None:
        self._embedding_backend = str(embedding_backend or "default").strip().lower() or "default"
        self._embedding_model = str(embedding_model or "text-embedding-3-small").strip() or "text-embedding-3-small"
        self._openai_api_key = str(openai_api_key or "").strip()
        self._openai_base_url = str(openai_base_url or "").strip()
        self._clients: dict[str, chromadb.PersistentClient] = {}
        self._embedding_functions: dict[str, Any] = {}

    def rebuild_collection(self, *, index_dir: Path, collection_name: str, chunks: list[KnowledgeChunk]) -> int:
        client = self._client(index_dir)
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        collection = client.get_or_create_collection(
            collection_name,
            embedding_function=self._embedding_function(),
            metadata={
                "embedding_backend": self._embedding_backend,
                "embedding_model": self._embedding_model,
            },
        )
        if not chunks:
            return 0
        batch_size = 128
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.text for chunk in batch],
                metadatas=[self._metadata_for_chunk(chunk) for chunk in batch],
            )
        return int(collection.count())

    def load_collection(self, *, index_dir: Path, collection_name: str) -> list[KnowledgeChunk]:
        client = self._client(index_dir)
        try:
            collection = client.get_collection(collection_name, embedding_function=self._embedding_function())
        except Exception:
            return []
        payload = collection.get(include=["documents", "metadatas"])
        ids = payload.get("ids") if isinstance(payload.get("ids"), list) else []
        documents = payload.get("documents") if isinstance(payload.get("documents"), list) else []
        metadatas = payload.get("metadatas") if isinstance(payload.get("metadatas"), list) else []
        chunks: list[KnowledgeChunk] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            text = documents[index] if index < len(documents) else ""
            chunks.append(
                KnowledgeChunk(
                    chunk_id=str(chunk_id or "").strip(),
                    source_path=str(metadata.get("source_path", "")).strip(),
                    relative_path=str(metadata.get("relative_path", "")).strip(),
                    source_kind=str(metadata.get("source_kind", "")).strip(),
                    document_type=str(metadata.get("document_type", "")).strip(),
                    chunk_index=int(metadata.get("chunk_index", 0) or 0),
                    text=str(text or ""),
                    section_context=str(metadata.get("section_context", "")).strip(),
                    mentioned_codes=tuple(self._mentioned_codes_from_metadata(metadata)),
                    text_length=int(metadata.get("text_length", 0) or 0),
                )
            )
        return chunks

    def query(
        self,
        *,
        index_dir: Path,
        collection_name: str,
        query_texts: list[str],
        top_k: int,
        preferred_codes: list[str] | tuple[str, ...] = (),
    ) -> list[VectorDbHit]:
        client = self._client(index_dir)
        try:
            collection = client.get_collection(collection_name, embedding_function=self._embedding_function())
        except Exception:
            return []
        if collection.count() <= 0:
            return []
        query_text = "\n".join(text for text in query_texts if str(text).strip()).strip()
        if not query_text:
            return []
        n_results = max(int(top_k), min(int(top_k) * 4, 24))
        result = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        raw_ids = result.get("ids") if isinstance(result.get("ids"), list) else []
        raw_documents = result.get("documents") if isinstance(result.get("documents"), list) else []
        raw_metadatas = result.get("metadatas") if isinstance(result.get("metadatas"), list) else []
        raw_distances = result.get("distances") if isinstance(result.get("distances"), list) else []
        ids = raw_ids[0] if raw_ids and isinstance(raw_ids[0], list) else []
        documents = raw_documents[0] if raw_documents and isinstance(raw_documents[0], list) else []
        metadatas = raw_metadatas[0] if raw_metadatas and isinstance(raw_metadatas[0], list) else []
        distances = raw_distances[0] if raw_distances and isinstance(raw_distances[0], list) else []

        query_counter = Counter(_tokenize(query_text))
        preferred = [str(code).strip() for code in preferred_codes if str(code).strip()]
        hits: list[VectorDbHit] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            document = str(documents[index] or "") if index < len(documents) else ""
            distance = float(distances[index]) if index < len(distances) and distances[index] is not None else 1.0
            score = self._rerank_score(
                document=document,
                metadata=metadata,
                distance=distance,
                query_counter=query_counter,
                preferred_codes=preferred,
            )
            hits.append(
                VectorDbHit(
                    chunk_id=str(chunk_id or "").strip(),
                    source_path=str(metadata.get("source_path", "")).strip(),
                    relative_path=str(metadata.get("relative_path", "")).strip(),
                    source_kind=str(metadata.get("source_kind", "")).strip(),
                    document_type=str(metadata.get("document_type", "")).strip(),
                    section_context=str(metadata.get("section_context", "")).strip(),
                    text=document,
                    score=round(score, 4),
                    mentioned_codes=tuple(self._mentioned_codes_from_metadata(metadata)),
                )
            )
        hits.sort(key=lambda item: (-item.score, item.relative_path, item.chunk_id))
        return hits[: max(1, int(top_k))]

    def collection_count(self, *, index_dir: Path, collection_name: str) -> int:
        client = self._client(index_dir)
        try:
            collection = client.get_collection(collection_name, embedding_function=self._embedding_function())
        except Exception:
            return 0
        return int(collection.count())

    def _client(self, index_dir: Path) -> chromadb.PersistentClient:
        resolved = str(Path(index_dir).resolve())
        if resolved not in self._clients:
            self._clients[resolved] = chromadb.PersistentClient(path=resolved)
        return self._clients[resolved]

    def _embedding_function(self) -> Any:
        cache_key = f"{self._embedding_backend}:{self._embedding_model}:{self._openai_base_url}"
        if cache_key in self._embedding_functions:
            return self._embedding_functions[cache_key]
        if self._embedding_backend == "openai":
            api_key = self._openai_api_key or os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("TNVED_VBD_EMBEDDING_BACKEND=openai requires OPENAI_API_KEY.")
            function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name=self._embedding_model,
                api_base=self._openai_base_url or None,
            )
        else:
            function = embedding_functions.DefaultEmbeddingFunction()
        self._embedding_functions[cache_key] = function
        return function

    @staticmethod
    def _metadata_for_chunk(chunk: KnowledgeChunk) -> dict[str, Any]:
        return {
            "source_path": chunk.source_path,
            "relative_path": chunk.relative_path,
            "source_kind": chunk.source_kind,
            "document_type": chunk.document_type,
            "chunk_index": int(chunk.chunk_index),
            "section_context": chunk.section_context,
            "mentioned_codes": _json_dumps_list(chunk.mentioned_codes),
            "text_length": int(chunk.text_length or len(chunk.text or "")),
        }

    @staticmethod
    def _mentioned_codes_from_metadata(metadata: dict[str, Any]) -> list[str]:
        raw = metadata.get("mentioned_codes")
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str) and raw.strip():
            try:
                payload = json.loads(raw)
            except Exception:
                payload = []
            if isinstance(payload, list):
                return [str(item).strip() for item in payload if str(item).strip()]
        return []

    @classmethod
    def _rerank_score(
        cls,
        *,
        document: str,
        metadata: dict[str, Any],
        distance: float,
        query_counter: Counter[str],
        preferred_codes: list[str],
    ) -> float:
        similarity = 1.0 / (1.0 + max(0.0, float(distance)))
        score = similarity * 10.0
        chunk_counter = Counter(_tokenize(document))
        overlap = sum(min(chunk_counter[token], count) for token, count in query_counter.items())
        score += float(overlap) * 0.35
        mentioned = set(cls._mentioned_codes_from_metadata(metadata))
        for index, code in enumerate(preferred_codes):
            if code in mentioned:
                score += max(6.0, 12.0 - index * 1.5)
            elif code and code in document:
                score += max(4.0, 9.0 - index)
            elif code[:8] and any(item.startswith(code[:8]) for item in mentioned):
                score += 3.5
            elif code[:6] and any(item.startswith(code[:6]) for item in mentioned):
                score += 2.0
        if str(metadata.get("source_kind", "")).strip() == "reference":
            score += 0.8
        return score
