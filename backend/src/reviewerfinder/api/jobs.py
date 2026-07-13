from __future__ import annotations

import threading
import uuid
from typing import Callable

from reviewerfinder.api.schemas import SearchJobStatus, SearchResponse

# In-memory only -- fine for a local single-user tool. Jobs vanish on
# server restart, and this doesn't scale past one process; a real queue
# (Celery/RQ) would be the next step if this ever needs to run for real
# multi-user/multi-process deployment.
_jobs: dict[str, SearchJobStatus] = {}
_lock = threading.Lock()


def create_job() -> SearchJobStatus:
    job = SearchJobStatus(
        job_id=str(uuid.uuid4()), status="running", stage="starting", done=0, total=0
    )
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> SearchJobStatus | None:
    with _lock:
        return _jobs.get(job_id)


def _update(job_id: str, **changes) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        for key, value in changes.items():
            setattr(job, key, value)


def progress_callback(job_id: str) -> Callable[[str, int, int], None]:
    """Builds the on_progress callback pipeline.run_search() expects,
    bound to one job so the search thread doesn't need to know about the
    job store's internals.
    """

    def _callback(stage: str, done: int, total: int) -> None:
        _update(job_id, stage=stage, done=done, total=total)

    return _callback


def mark_done(job_id: str, result: SearchResponse) -> None:
    _update(job_id, status="done", result=result)


def mark_error(job_id: str, error: str) -> None:
    _update(job_id, status="error", error=error)
