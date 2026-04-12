from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..chunking import KnowledgeChunkingService
from ..vector_db import KnowledgeVectorDbService


class TnvedVbdIndexingService:
    def __init__(
        self,
        *,
        docs_dir: Path,
        reference_dir: Path,
        examples_dir: Path,
        index_dir: Path,
        chunking_service: KnowledgeChunkingService,
        vector_db_service: KnowledgeVectorDbService,
    ) -> None:
        self._docs_dir = Path(docs_dir)
        self._reference_dir = Path(reference_dir)
        self._examples_dir = Path(examples_dir)
        self._index_dir = Path(index_dir)
        self._chunking_service = chunking_service
        self._vector_db_service = vector_db_service

    @property
    def index_dir(self) -> Path:
        return self._index_dir

    def ensure_index(self, *, force: bool = False) -> dict[str, Any]:
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        self._reference_dir.mkdir(parents=True, exist_ok=True)
        self._examples_dir.mkdir(parents=True, exist_ok=True)
        self._index_dir.mkdir(parents=True, exist_ok=True)

        manifest = self._build_manifest_payload()
        current_signature = json.dumps(manifest.get("documents", []), ensure_ascii=False, sort_keys=True)
        existing_manifest = self.load_manifest()
        existing_signature = json.dumps(existing_manifest.get("documents", []), ensure_ascii=False, sort_keys=True)
        existing_reference_count = self._vector_db_service.collection_count(
            index_dir=self._index_dir,
            collection_name="reference_chunks",
        )
        existing_example_count = self._vector_db_service.collection_count(
            index_dir=self._index_dir,
            collection_name="example_chunks",
        )
        manifest_reference_count = int(existing_manifest.get("reference_chunk_count", 0) or 0)
        manifest_example_count = int(existing_manifest.get("example_chunk_count", 0) or 0)
        needs_rebuild = (
            force
            or existing_signature != current_signature
            or str(existing_manifest.get("vector_backend", "")).strip().lower() != "chroma"
            or existing_reference_count != manifest_reference_count
            or existing_example_count != manifest_example_count
        )
        if needs_rebuild:
            reference_documents = self._chunking_service.scan_documents(self._reference_dir, source_kind="reference")
            example_documents = self._chunking_service.scan_documents(self._examples_dir, source_kind="example")
            reference_chunks = self._chunking_service.build_chunks(reference_documents)
            example_chunks = self._chunking_service.build_chunks(example_documents)
            reference_chunk_count = self._vector_db_service.rebuild_collection(
                index_dir=self._index_dir,
                collection_name="reference_chunks",
                chunks=reference_chunks,
            )
            example_chunk_count = self._vector_db_service.rebuild_collection(
                index_dir=self._index_dir,
                collection_name="example_chunks",
                chunks=example_chunks,
            )
            manifest = {
                **manifest,
                "status": "ready" if (reference_chunk_count or example_chunk_count) else "empty",
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "reference_chunk_count": int(reference_chunk_count),
                "example_chunk_count": int(example_chunk_count),
                "vector_backend": "chroma",
            }
            self._write_manifest(manifest)
            return manifest

        if existing_manifest:
            existing_manifest.setdefault("vector_backend", "chroma")
            return existing_manifest
        manifest["vector_backend"] = "chroma"
        return manifest

    def load_manifest(self) -> dict[str, Any]:
        path = self._index_dir / "manifest.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def load_index_payload(self) -> dict[str, Any]:
        manifest = self.ensure_index()
        return {
            "manifest": manifest,
            "reference_chunks": [],
            "example_chunks": [],
        }

    def _build_manifest_payload(self) -> dict[str, Any]:
        reference_documents = self._chunking_service.scan_documents(self._reference_dir, source_kind="reference")
        example_documents = self._chunking_service.scan_documents(self._examples_dir, source_kind="example")
        documents = [item.to_payload() for item in [*reference_documents, *example_documents]]
        return {
            "status": "pending" if documents else "empty",
            "docs_dir": str(self._docs_dir),
            "reference_dir": str(self._reference_dir),
            "examples_dir": str(self._examples_dir),
            "documents": documents,
            "document_count": len(documents),
            "reference_document_count": len(reference_documents),
            "example_document_count": len(example_documents),
            "vector_backend": "chroma",
        }

    def _write_manifest(self, payload: dict[str, Any]) -> None:
        path = self._index_dir / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
