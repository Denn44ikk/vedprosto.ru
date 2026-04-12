from __future__ import annotations

from pydantic import BaseModel


class JobView(BaseModel):
    job_id: str
    job_type: str
    module_id: str
    status: str
    created_at: str
    updated_at: str
    summary: str
    command: list[str]
    output: str
    error: str
    payload: dict


class JobListResponse(BaseModel):
    jobs: list[JobView]
