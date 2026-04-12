from __future__ import annotations

from ...config import AppSettings
from ...orchestrator.job_store import JobRecord
from ...orchestrator.job_store import JobStore
from ...storage.runtime_state.service import RuntimeStateService
from .limits import resolve_effective_workers
from .models import PipelineBatchRequest
from .pool import PipelineWorkerPool
from .runtime import PipelineWorkerRuntime


class PipelineTaskDispatcher:
    def __init__(
        self,
        *,
        settings: AppSettings,
        job_store: JobStore,
        runtime_state_service: RuntimeStateService,
        worker_runtime: PipelineWorkerRuntime,
        worker_pool: PipelineWorkerPool,
    ) -> None:
        self.settings = settings
        self.job_store = job_store
        self.runtime_state_service = runtime_state_service
        self.worker_runtime = worker_runtime
        self.worker_pool = worker_pool

    def dispatch_ocr_batch(self, *, root_path: str, case_ids: list[str], requested_workers: int | None = None) -> JobRecord:
        normalized_case_ids = tuple(case_id.strip() for case_id in case_ids if isinstance(case_id, str) and case_id.strip())
        if not normalized_case_ids:
            raise ValueError("No case ids provided for OCR batch.")

        self.worker_runtime.clear_root_stop(root_path)
        effective_workers = resolve_effective_workers(
            requested_workers=requested_workers,
            task_count=len(normalized_case_ids),
            max_workers_total=self.settings.pipeline_max_workers_total,
            max_workers_per_job=self.settings.pipeline_max_workers_per_job,
        )
        request = PipelineBatchRequest(
            root_path=root_path,
            case_ids=normalized_case_ids,
            requested_workers=requested_workers if requested_workers is not None else len(normalized_case_ids),
            effective_workers=effective_workers,
            summary=f"GPT batch for {len(normalized_case_ids)} case(s)",
        )

        for case_id in normalized_case_ids:
            self.runtime_state_service.set_case_flag(root_path, case_id, "prefetch_status", "queued")

        job = self.job_store.create_job(
            job_type=request.job_type,
            module_id=request.module_id,
            summary=request.summary,
            command=[],
            payload=request.build_job_payload(),
        )
        self.worker_pool.start_ocr_batch(job.job_id, request)
        return job

    def cancel_ocr_jobs(self, *, root_path: str) -> list[str]:
        self.worker_runtime.request_root_stop(root_path)
        cancelled_job_ids: list[str] = []
        for row in self.job_store.list_jobs():
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if row.get("module_id") != "batch_ocr":
                continue
            if str(payload.get("root_path", "")) != root_path:
                continue
            if str(row.get("status", "")) not in {"queued", "running", "cancelling"}:
                continue
            self.job_store.request_cancel(str(row.get("job_id")))
            cancelled_job_ids.append(str(row.get("job_id")))
        return cancelled_job_ids
