from __future__ import annotations


def resolve_effective_workers(
    *,
    requested_workers: int | None,
    task_count: int,
    max_workers_total: int,
    max_workers_per_job: int,
) -> int:
    if task_count <= 0:
        return 0

    desired = requested_workers if requested_workers is not None else task_count
    desired = max(1, desired)
    caps = [
        task_count,
        max(1, max_workers_total),
        max(1, max_workers_per_job),
    ]
    return max(1, min(desired, *caps))
