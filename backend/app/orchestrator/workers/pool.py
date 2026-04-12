from __future__ import annotations

from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Event
from threading import Lock
from threading import Semaphore
from threading import Thread

from ...config import AppSettings
from ...orchestrator.job_store import JobStore
from ...orchestrator.pipelines import CasePipelineService
from ...processing.ocr.service import OcrProcessingService
from ...storage.cases.service import CaseStorageService
from ...storage.runtime_state.service import RuntimeStateService
from .models import PipelineBatchRequest
from .models import PipelineCaseResult
from .models import PipelineCaseTask
from .runtime import PipelineWorkerRuntime


class PipelineWorkerPool:
    def __init__(
        self,
        *,
        settings: AppSettings,
        job_store: JobStore,
        runtime_state_service: RuntimeStateService,
        case_storage_service: CaseStorageService,
        ocr_processing_service: OcrProcessingService,
        case_pipeline_service: CasePipelineService,
        worker_runtime: PipelineWorkerRuntime,
    ) -> None:
        self.settings = settings
        self.job_store = job_store
        self.runtime_state_service = runtime_state_service
        self.case_storage_service = case_storage_service
        self.ocr_processing_service = ocr_processing_service
        self.case_pipeline_service = case_pipeline_service
        self.worker_runtime = worker_runtime
        self._global_slots = Semaphore(max(1, settings.pipeline_max_workers_total))
        self._lines_lock = Lock()

    def start_ocr_batch(self, job_id: str, request: PipelineBatchRequest) -> None:
        thread = Thread(
            target=self._run_ocr_batch,
            args=(job_id, request),
            daemon=True,
            name=f"ocr-batch-{job_id[:8]}",
        )
        thread.start()

    def _run_ocr_batch(self, job_id: str, request: PipelineBatchRequest) -> None:
        self.job_store.update_status(job_id, status="running")
        task_queue: Queue[PipelineCaseTask] = Queue()
        result_queue: Queue[PipelineCaseResult] = Queue()
        batch_stop_event = Event()
        tasks = [
            PipelineCaseTask(case_id=case_id, position=index, total=len(request.case_ids))
            for index, case_id in enumerate(request.case_ids, start=1)
        ]
        for task in tasks:
            task_queue.put(task)

        workers = [
            Thread(
                target=self._ocr_worker_loop,
                args=(job_id, request, task_queue, result_queue, batch_stop_event),
                daemon=True,
                name=f"ocr-worker-{job_id[:8]}-{index + 1}",
            )
            for index in range(request.effective_workers)
        ]
        for worker in workers:
            worker.start()

        lines: list[str] = []
        processed_count = 0
        first_error_text = ""
        while processed_count < len(tasks):
            result = result_queue.get()
            processed_count += 1
            with self._lines_lock:
                lines.append(result.line)
                output = "\n".join(lines)
            stop_requested = self._should_stop(job_id, request.root_path, batch_stop_event)
            if result.status == "error" and not first_error_text and not stop_requested:
                first_error_text = result.error_text or f"GPT failed for {result.case_id}"
                batch_stop_event.set()
            elif result.status == "cancelled":
                batch_stop_event.set()
            self.job_store.update_status(
                job_id,
                status="running",
                output=output,
                error=first_error_text or None,
            )

        for worker in workers:
            worker.join()

        output = "\n".join(lines)
        if self._should_stop(job_id, request.root_path, batch_stop_event):
            self.job_store.update_status(
                job_id,
                status="cancelled",
                output=output,
                error="Подбор остановлен оператором.",
            )
            return

        if first_error_text:
            self.job_store.update_status(job_id, status="failed", output=output, error=first_error_text)
            return

        self.job_store.update_status(job_id, status="completed", output=output)

    def _ocr_worker_loop(
        self,
        job_id: str,
        request: PipelineBatchRequest,
        task_queue: Queue[PipelineCaseTask],
        result_queue: Queue[PipelineCaseResult],
        batch_stop_event: Event,
    ) -> None:
        while True:
            try:
                task = task_queue.get_nowait()
            except Empty:
                return

            if self._should_stop(job_id, request.root_path, batch_stop_event):
                self.runtime_state_service.set_case_flag(request.root_path, task.case_id, "prefetch_status", "cancelled")
                result_queue.put(
                    PipelineCaseResult(
                        case_id=task.case_id,
                        position=task.position,
                        total=task.total,
                        status="cancelled",
                        line=f"{task.position}/{task.total} {task.case_id}: STOP",
                        error_text="Подбор остановлен оператором.",
                    )
                )
                task_queue.task_done()
                continue

            result = self._run_ocr_case(job_id=job_id, request=request, task=task, batch_stop_event=batch_stop_event)
            result_queue.put(result)
            if result.status in {"error", "cancelled"}:
                batch_stop_event.set()
            task_queue.task_done()

    def _run_ocr_case(
        self,
        *,
        job_id: str,
        request: PipelineBatchRequest,
        task: PipelineCaseTask,
        batch_stop_event: Event,
    ) -> PipelineCaseResult:
        root_path = request.root_path
        if self._should_stop(job_id, root_path, batch_stop_event):
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "cancelled")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="cancelled",
                line=f"{task.position}/{task.total} {task.case_id}: STOP",
                error_text="Подбор остановлен оператором.",
            )

        self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "running")
        active_root = Path(root_path)
        self._global_slots.acquire()
        try:
            if self._should_stop(job_id, root_path, batch_stop_event):
                self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "cancelled")
                return PipelineCaseResult(
                    case_id=task.case_id,
                    position=task.position,
                    total=task.total,
                    status="cancelled",
                    line=f"{task.position}/{task.total} {task.case_id}: STOP",
                    error_text="Подбор остановлен оператором.",
                )

            case_dir = self.case_storage_service.case_dir(active_root, task.case_id)
            case_payload, _, _ = self.case_storage_service.load_case_payload(active_root, task.case_id)
            source_row_payload = self.case_storage_service.load_source_row_payload(active_root, task.case_id)
            existing_ocr_payload = self.case_storage_service.load_ocr_payload(active_root, task.case_id)
            if not case_payload:
                self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "error")
                return PipelineCaseResult(
                    case_id=task.case_id,
                    position=task.position,
                    total=task.total,
                    status="error",
                    line=f"{task.position}/{task.total} {task.case_id}: ERROR",
                    error_text=f"Case not found: {task.case_id}",
                )

            result = self.ocr_processing_service.run_case_ocr(
                case_dir=case_dir,
                case_payload=case_payload,
                source_row_payload=source_row_payload,
                existing_payload=existing_ocr_payload,
                should_stop=lambda: self._should_stop(job_id, root_path, batch_stop_event),
            )
        finally:
            self._global_slots.release()

        status = str(result.get("status", "")).lower()
        if status == "cancelled":
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "cancelled")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="cancelled",
                line=f"{task.position}/{task.total} {task.case_id}: STOP",
                error_text=str(result.get("error_text", "")).strip() or "Подбор остановлен оператором.",
            )
        if status == "error":
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "error")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="error",
                line=f"{task.position}/{task.total} {task.case_id}: ERROR",
                error_text=str(result.get("error_text", "")).strip() or f"GPT failed for {task.case_id}",
            )

        if self._should_stop(job_id, root_path, batch_stop_event):
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "cancelled")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="cancelled",
                line=f"{task.position}/{task.total} {task.case_id}: STOP",
                error_text="Подбор остановлен оператором.",
            )

        tnved_result = self.case_pipeline_service.run_case_pipeline(
            case_dir=case_dir,
            ocr_payload=result,
            should_stop=lambda: self._should_stop(job_id, root_path, batch_stop_event),
        )
        if self._should_stop(job_id, root_path, batch_stop_event):
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "cancelled")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="cancelled",
                line=f"{task.position}/{task.total} {task.case_id}: STOP",
                error_text="Подбор остановлен оператором.",
            )
        if str(tnved_result.get("status", "")).lower() == "cancelled":
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "cancelled")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="cancelled",
                line=f"{task.position}/{task.total} {task.case_id}: STOP",
                error_text=str(tnved_result.get("error_text", "")).strip() or "Подбор остановлен оператором.",
            )
        if str(tnved_result.get("status", "")).lower() == "error":
            self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "error")
            return PipelineCaseResult(
                case_id=task.case_id,
                position=task.position,
                total=task.total,
                status="error",
                line=f"{task.position}/{task.total} {task.case_id}: TNVED ERROR",
                error_text=str(tnved_result.get("error_text", "")).strip() or f"TNVED failed for {task.case_id}",
            )

        self.runtime_state_service.set_case_flag(root_path, task.case_id, "prefetch_status", "completed")
        return PipelineCaseResult(
            case_id=task.case_id,
            position=task.position,
            total=task.total,
            status="completed",
            line=f"{task.position}/{task.total} {task.case_id}: OCR+TNVED OK",
        )

    def _should_stop(self, job_id: str, root_path: str, batch_stop_event: Event) -> bool:
        return (
            batch_stop_event.is_set()
            or self.worker_runtime.is_root_stop_requested(root_path)
            or self.job_store.is_cancel_requested(job_id)
        )
