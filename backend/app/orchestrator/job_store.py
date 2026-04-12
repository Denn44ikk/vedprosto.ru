from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    module_id: str
    status: str
    created_at: str
    updated_at: str
    summary: str
    command: list[str] = field(default_factory=list)
    output: str = ""
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class JobStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._cancel_requests: set[str] = set()

    def create_job(
        self,
        *,
        job_type: str,
        module_id: str,
        summary: str,
        command: list[str],
        payload: dict[str, Any],
    ) -> JobRecord:
        job = JobRecord(
            job_id=str(uuid4()),
            job_type=job_type,
            module_id=module_id,
            status="queued",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            summary=summary,
            command=command,
            payload=payload,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def update_status(self, job_id: str, *, status: str, output: str | None = None, error: str | None = None) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.updated_at = utc_now_iso()
            if output is not None:
                job.output = output
            if error is not None:
                job.error = error
            if status in {"completed", "failed", "cancelled"}:
                self._cancel_requests.discard(job_id)
            return job

    def request_cancel(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id]
            self._cancel_requests.add(job_id)
            if job.status in {"queued", "running"}:
                job.status = "cancelling"
                job.updated_at = utc_now_iso()
            return job

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel_requests

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            return self._jobs[job_id]

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return [asdict(row) for row in rows]
