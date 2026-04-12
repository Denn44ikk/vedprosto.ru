from __future__ import annotations

import json
import shutil
from pathlib import Path

from ...config import AppSettings
from ..runtime_state.service import RuntimeStateService


class CaseStorageService:
    def __init__(
        self,
        *,
        settings: AppSettings,
        runtime_state_service: RuntimeStateService,
    ) -> None:
        self.settings = settings
        self.runtime_state_service = runtime_state_service

    @staticmethod
    def read_json(path: Path) -> dict | list | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def discover_roots(self) -> list[Path]:
        roots: dict[str, Path] = {}
        for marker in self.settings.agent_ui_dir.rglob("review_queue.json"):
            root_path = marker.parent.resolve()
            roots[str(root_path)] = root_path

        discovered = sorted(
            roots.values(),
            key=lambda item: item.stat().st_mtime if item.exists() else 0,
            reverse=True,
        )

        active_root_path = self.runtime_state_service.get_active_case_root_path().strip()
        if active_root_path:
            active_root = Path(active_root_path)
            if active_root.exists() and (active_root / "review_queue.json").exists():
                roots.setdefault(str(active_root.resolve()), active_root.resolve())
                discovered = sorted(
                    roots.values(),
                    key=lambda item: item.stat().st_mtime if item.exists() else 0,
                    reverse=True,
                )
        return discovered

    def resolve_active_root(self) -> Path | None:
        roots = self.discover_roots()
        active_root_path = self.runtime_state_service.get_active_case_root_path().strip()
        if active_root_path:
            active_root = Path(active_root_path)
            if active_root.exists() and (active_root / "review_queue.json").exists():
                resolved = active_root.resolve()
                self.runtime_state_service.ensure_workspace_root(str(resolved))
                return resolved
        if roots:
            fallback_root = roots[0].resolve()
            self.runtime_state_service.set_active_case_root_path(str(fallback_root))
            self.runtime_state_service.ensure_workspace_root(str(fallback_root))
            return fallback_root
        return None

    @staticmethod
    def root_label(root_path: Path) -> str:
        parent_label = root_path.parent.name.strip() or root_path.parent.as_posix()
        return f"{parent_label} / {root_path.name}"

    def load_review_queue(self, root_path: Path) -> list[dict]:
        payload = self.read_json(root_path / "review_queue.json")
        return payload if isinstance(payload, list) else []

    @staticmethod
    def case_dir(root_path: Path, case_id: str) -> Path:
        return root_path / case_id

    def load_case_json(self, root_path: Path, case_id: str, relative_path: str) -> dict | list | None:
        return self.read_json(self.case_dir(root_path, case_id) / relative_path)

    def load_case_payload(self, root_path: Path, case_id: str) -> tuple[dict, dict, dict | None]:
        case_dir = self.case_dir(root_path, case_id)
        case_payload = self.read_json(case_dir / "case.json")
        status_payload = self.read_json(case_dir / "work" / "status.json")
        analysis_payload = self.read_json(case_dir / "work" / "01_expander.json")
        return (
            case_payload if isinstance(case_payload, dict) else {},
            status_payload if isinstance(status_payload, dict) else {},
            analysis_payload if isinstance(analysis_payload, dict) else None,
        )

    def load_source_row_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "source_row.json")
        return payload if isinstance(payload, dict) else {}

    def load_ocr_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/ocr.json")
        return payload if isinstance(payload, dict) else {}

    def load_tnved_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/tnved.json")
        return payload if isinstance(payload, dict) else {}

    def load_verification_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/verification.json")
        return payload if isinstance(payload, dict) else {}

    def load_tnved_vbd_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/tnved_vbd.json")
        return payload if isinstance(payload, dict) else {}

    def load_enrichment_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/enrichment.json")
        return payload if isinstance(payload, dict) else {}

    def load_calculations_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/calculations.json")
        return payload if isinstance(payload, dict) else {}

    def load_questions_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "work/questions.json")
        return payload if isinstance(payload, dict) else {}

    def load_pipeline_result_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "result/pipeline_result.json")
        return payload if isinstance(payload, dict) else {}

    def load_ui_response_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "result/ui_response.json")
        return payload if isinstance(payload, dict) else {}

    def load_export_payload(self, root_path: Path, case_id: str) -> dict:
        payload = self.load_case_json(root_path, case_id, "result/export.json")
        return payload if isinstance(payload, dict) else {}

    def resolve_case_image_path(self, case_id: str, image_name: str) -> Path:
        active_root = self.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")
        image_path = (self.case_dir(active_root, case_id) / "images" / image_name).resolve()
        root_anchor = self.case_dir(active_root, case_id).resolve()
        if root_anchor not in image_path.parents:
            raise PermissionError("Image path is outside the active case directory.")
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_name}")
        return image_path

    def delete_root(self, root_path: str) -> Path:
        target = Path(root_path).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Case root not found: {root_path}")
        if not (target / "review_queue.json").exists():
            raise ValueError(f"Folder is not a case root: {root_path}")
        if not target.name.endswith("__agent_cases"):
            raise ValueError(f"Refuse to delete non-case folder: {root_path}")

        shutil.rmtree(target)
        self.runtime_state_service.remove_workspace_root(str(target))
        return target
