from __future__ import annotations

from pathlib import Path

from ...orchestrator.job_store import JobStore
from ...orchestrator.pipelines import CasePipelineService
from ...orchestrator.workers.dispatcher import PipelineTaskDispatcher
from ...orchestrator.workers.runtime import PipelineWorkerRuntime
from ...processing.ocr.service import OcrProcessingService
from ...reporting.ui.workspace.service import WorkspaceReportingService
from ...storage.cases.service import CaseStorageService
from ...storage.runtime_state.service import RuntimeStateService


class WorkspaceService:
    def __init__(
        self,
        *,
        runtime_state_service: RuntimeStateService,
        job_store: JobStore,
        ocr_processing_service: OcrProcessingService,
        case_pipeline_service: CasePipelineService,
        case_storage_service: CaseStorageService,
        worker_runtime: PipelineWorkerRuntime,
        worker_dispatcher: PipelineTaskDispatcher,
        workspace_reporting_service: WorkspaceReportingService,
    ) -> None:
        self.runtime_state_service = runtime_state_service
        self.job_store = job_store
        self.ocr_processing_service = ocr_processing_service
        self.case_pipeline_service = case_pipeline_service
        self.case_storage_service = case_storage_service
        self.worker_runtime = worker_runtime
        self.worker_dispatcher = worker_dispatcher
        self.workspace_reporting_service = workspace_reporting_service

    def _run_tnved_after_ocr(self, *, case_dir: Path, ocr_payload: dict[str, object] | None) -> None:
        result = self.case_pipeline_service.run_case_pipeline(
            case_dir=case_dir,
            ocr_payload=ocr_payload if isinstance(ocr_payload, dict) else None,
        )
        if str(result.get("status", "")).lower() == "error":
            raise RuntimeError(str(result.get("error_text", "")).strip() or "TNVED pipeline failed.")

    def _resolve_current_case_id(self, root_path: Path, queue: list[dict]) -> str:
        stored_case_id = self.runtime_state_service.get_current_case_id(str(root_path))
        queue_case_ids = [str(item.get("case_id", "")).strip() for item in queue if str(item.get("case_id", "")).strip()]
        if stored_case_id and stored_case_id in queue_case_ids:
            return stored_case_id
        if queue_case_ids:
            first_case_id = queue_case_ids[0]
            self.runtime_state_service.set_current_case_id(str(root_path), first_case_id)
            return first_case_id
        return ""

    def _prefetch_status(self, root_path: Path, case_id: str) -> str:
        flags = self.runtime_state_service.get_case_flags(str(root_path), case_id)
        return str(flags.get("prefetch_status", "idle"))

    def _active_batch_case_ids(self, root_path: Path) -> set[str]:
        root_key = str(root_path)
        active_case_ids: set[str] = set()
        for row in self.job_store.list_jobs():
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if row.get("module_id") != "batch_ocr":
                continue
            if str(payload.get("root_path", "")) != root_key:
                continue
            if str(row.get("status", "")) not in {"queued", "running", "cancelling"}:
                continue
            case_ids = payload.get("case_ids") if isinstance(payload.get("case_ids"), list) else []
            active_case_ids.update(str(case_id).strip() for case_id in case_ids if str(case_id).strip())
        return active_case_ids

    def _cleanup_transient_prefetch_flags(self, root_path: Path, queue: list[dict]) -> None:
        root_key = str(root_path)
        active_case_ids = self._active_batch_case_ids(root_path)
        transient_states = {"queued", "running", "cancelling"}
        for item in queue:
            case_id = str(item.get("case_id", "")).strip()
            if not case_id:
                continue
            current_status = self._prefetch_status(root_path, case_id)
            if current_status not in transient_states:
                continue
            if case_id in active_case_ids:
                continue
            self.runtime_state_service.set_case_flag(root_key, case_id, "prefetch_status", "idle")

    def get_workspace(self) -> dict[str, object]:
        roots = self.case_storage_service.discover_roots()
        active_root = self.case_storage_service.resolve_active_root()

        root_views = []
        for root in roots:
            root_views.append(
                {
                    "root_path": str(root),
                    "label": self.case_storage_service.root_label(root),
                    "is_active": bool(active_root and root.resolve() == active_root.resolve()),
                }
            )

        if active_root is None:
            return {
                "roots": root_views,
                "active_root_path": "",
                "current_case_id": "",
                "counters": {
                    "total": 0,
                    "pending": 0,
                    "saved": 0,
                    "skipped": 0,
                },
                "cases": [],
                "current_case": None,
            }

        queue = self.case_storage_service.load_review_queue(active_root)
        self._cleanup_transient_prefetch_flags(active_root, queue)
        current_case_id = self._resolve_current_case_id(active_root, queue)
        cases = self.workspace_reporting_service.build_case_list(active_root, queue, current_case_id)
        current_case = self.workspace_reporting_service.build_current_case(active_root, current_case_id)

        return {
            "roots": root_views,
            "active_root_path": str(active_root),
            "current_case_id": current_case_id,
            "counters": self.workspace_reporting_service.build_counters(cases),
            "cases": cases,
            "current_case": current_case,
        }

    def set_active_root(self, root_path: str) -> dict[str, object]:
        resolved_root = Path(root_path).expanduser().resolve()
        if not resolved_root.exists() or not (resolved_root / "review_queue.json").exists():
            raise FileNotFoundError(f"Case root not found or invalid: {root_path}")
        self.runtime_state_service.set_active_case_root_path(str(resolved_root))
        self.runtime_state_service.ensure_workspace_root(str(resolved_root))
        return self.get_workspace()

    def delete_root(self, root_path: str) -> dict[str, object]:
        self.case_storage_service.delete_root(root_path)
        return self.get_workspace()

    def set_current_case(self, case_id: str) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")
        queue = self.case_storage_service.load_review_queue(active_root)
        queue_case_ids = {str(item.get("case_id", "")).strip() for item in queue}
        if case_id not in queue_case_ids:
            raise ValueError(f"Unknown case: {case_id}")
        self.runtime_state_service.set_current_case_id(str(active_root), case_id)
        return self.get_workspace()

    def run_ocr(self, case_id: str | None = None) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")
        root_key = str(active_root)
        self.worker_runtime.clear_root_stop(root_key)

        queue = self.case_storage_service.load_review_queue(active_root)
        resolved_case_id = case_id.strip() if isinstance(case_id, str) and case_id.strip() else self._resolve_current_case_id(active_root, queue)
        if not resolved_case_id:
            raise ValueError("No current case selected.")

        case_dir = self.case_storage_service.case_dir(active_root, resolved_case_id)
        case_payload, _, _ = self.case_storage_service.load_case_payload(active_root, resolved_case_id)
        if not case_payload:
            raise FileNotFoundError(f"Case not found: {resolved_case_id}")

        source_row_payload = self.case_storage_service.load_source_row_payload(active_root, resolved_case_id)
        existing_ocr_payload = self.case_storage_service.load_ocr_payload(active_root, resolved_case_id)
        ocr_result = self.ocr_processing_service.run_case_ocr(
            case_dir=case_dir,
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            existing_payload=existing_ocr_payload,
            should_stop=lambda: self.worker_runtime.is_root_stop_requested(root_key),
        )
        status = str(ocr_result.get("status", "")).lower()
        if status == "completed":
            self._run_tnved_after_ocr(case_dir=case_dir, ocr_payload=ocr_result)
        return self.get_workspace()

    def _advance_to_next_case(self, active_root: Path, queue: list[dict], current_case_id: str) -> str:
        queue_case_ids = [str(item.get("case_id", "")).strip() for item in queue if str(item.get("case_id", "")).strip()]
        if not queue_case_ids:
            return ""
        if current_case_id not in queue_case_ids:
            next_case_id = queue_case_ids[0]
            self.runtime_state_service.set_current_case_id(str(active_root), next_case_id)
            return next_case_id
        current_index = queue_case_ids.index(current_case_id)
        next_index = min(current_index + 1, len(queue_case_ids) - 1)
        next_case_id = queue_case_ids[next_index]
        self.runtime_state_service.set_current_case_id(str(active_root), next_case_id)
        return next_case_id

    def save_to_excel(self) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")
        queue = self.case_storage_service.load_review_queue(active_root)
        current_case_id = self._resolve_current_case_id(active_root, queue)
        if not current_case_id:
            raise ValueError("No current case selected.")
        self.runtime_state_service.set_case_flag(str(active_root), current_case_id, "review_status", "saved")
        self._advance_to_next_case(active_root, queue, current_case_id)
        return self.get_workspace()

    def skip_current_case(self) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")
        queue = self.case_storage_service.load_review_queue(active_root)
        current_case_id = self._resolve_current_case_id(active_root, queue)
        if not current_case_id:
            raise ValueError("No current case selected.")
        self.runtime_state_service.set_case_flag(str(active_root), current_case_id, "review_status", "skipped")
        self._advance_to_next_case(active_root, queue, current_case_id)
        return self.get_workspace()

    def prefetch_next_cases(self, *, count: int) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")
        root_key = str(active_root)
        self.worker_runtime.clear_root_stop(root_key)
        queue = self.case_storage_service.load_review_queue(active_root)
        queue_case_ids = [str(item.get("case_id", "")).strip() for item in queue if str(item.get("case_id", "")).strip()]
        current_case_id = self._resolve_current_case_id(active_root, queue)
        if current_case_id not in queue_case_ids:
            target_case_ids = queue_case_ids[:count]
        else:
            current_index = queue_case_ids.index(current_case_id)
            target_case_ids = queue_case_ids[current_index : current_index + count]
        if not target_case_ids:
            return self.get_workspace()

        self.worker_dispatcher.dispatch_ocr_batch(
            root_path=root_key,
            case_ids=target_case_ids,
            requested_workers=count,
        )
        return self.get_workspace()

    def stop_ocr(self) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")

        root_key = str(active_root)
        self.worker_runtime.request_root_stop(root_key)
        queue = self.case_storage_service.load_review_queue(active_root)

        for item in queue:
            case_id = str(item.get("case_id", "")).strip()
            if not case_id:
                continue
            flags = self.runtime_state_service.get_case_flags(root_key, case_id)
            if str(flags.get("prefetch_status", "")) == "queued":
                self.runtime_state_service.set_case_flag(root_key, case_id, "prefetch_status", "cancelled")

        self.worker_dispatcher.cancel_ocr_jobs(root_path=root_key)

        return self.get_workspace()

    def resolve_case_image_path(self, case_id: str, image_name: str) -> Path:
        return self.case_storage_service.resolve_case_image_path(case_id, image_name)

    def resolve_case_runtime_context(self, case_id: str | None = None) -> dict[str, object]:
        active_root = self.case_storage_service.resolve_active_root()
        if active_root is None:
            raise FileNotFoundError("No active case root.")

        queue = self.case_storage_service.load_review_queue(active_root)
        queue_case_ids = {str(item.get("case_id", "")).strip() for item in queue if str(item.get("case_id", "")).strip()}
        resolved_case_id = case_id.strip() if isinstance(case_id, str) and case_id.strip() else self._resolve_current_case_id(active_root, queue)
        if not resolved_case_id:
            raise ValueError("No current case selected.")
        if resolved_case_id not in queue_case_ids:
            raise ValueError(f"Unknown case: {resolved_case_id}")

        case_dir = self.case_storage_service.case_dir(active_root, resolved_case_id)
        case_payload, status_payload, analysis_payload = self.case_storage_service.load_case_payload(active_root, resolved_case_id)
        source_row_payload = self.case_storage_service.load_source_row_payload(active_root, resolved_case_id)
        ocr_payload = self.case_storage_service.load_ocr_payload(active_root, resolved_case_id)
        tnved_payload = self.case_storage_service.load_tnved_payload(active_root, resolved_case_id)
        verification_payload = self.case_storage_service.load_verification_payload(active_root, resolved_case_id)
        tnved_vbd_payload = self.case_storage_service.load_tnved_vbd_payload(active_root, resolved_case_id)
        enrichment_payload = self.case_storage_service.load_enrichment_payload(active_root, resolved_case_id)
        calculations_payload = self.case_storage_service.load_calculations_payload(active_root, resolved_case_id)
        questions_payload = self.case_storage_service.load_questions_payload(active_root, resolved_case_id)
        pipeline_result_payload = self.case_storage_service.load_pipeline_result_payload(active_root, resolved_case_id)
        ui_response_payload = self.case_storage_service.load_ui_response_payload(active_root, resolved_case_id)
        export_payload = self.case_storage_service.load_export_payload(active_root, resolved_case_id)
        current_case = self.workspace_reporting_service.build_current_case(active_root, resolved_case_id)
        work_dir = case_dir / "work"
        work_files: list[str] = []
        if work_dir.exists():
            work_files = sorted(path.name for path in work_dir.glob("*.json"))
        result_dir = case_dir / "result"
        result_files: list[str] = []
        if result_dir.exists():
            result_files = sorted(path.name for path in result_dir.glob("*.json"))

        return {
            "root_path": str(active_root),
            "case_id": resolved_case_id,
            "case_dir": str(case_dir),
            "case_payload": case_payload,
            "source_row_payload": source_row_payload,
            "status_payload": status_payload,
            "expander_payload": analysis_payload if isinstance(analysis_payload, dict) else None,
            "ocr_payload": ocr_payload,
            "tnved_payload": tnved_payload,
            "verification_payload": verification_payload,
            "tnved_vbd_payload": tnved_vbd_payload,
            "enrichment_payload": enrichment_payload,
            "calculations_payload": calculations_payload,
            "questions_payload": questions_payload,
            "pipeline_result_payload": pipeline_result_payload,
            "ui_response_payload": ui_response_payload,
            "export_payload": export_payload,
            "current_case": current_case,
            "work_files": work_files,
            "result_files": result_files,
        }
