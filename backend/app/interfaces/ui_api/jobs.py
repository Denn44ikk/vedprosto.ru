from __future__ import annotations

from fastapi import APIRouter, Depends

from ...dependencies import get_container
from .contracts.job import JobListResponse, JobView


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def list_jobs(container=Depends(get_container)) -> JobListResponse:
    rows = container.job_store.list_jobs()
    return JobListResponse(jobs=[JobView(**row) for row in rows])
