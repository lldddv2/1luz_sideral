import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas import Job, JobCreate


class JobRegistry:
    """In-memory table of API jobs. Lost on restart; downloads persist via the extractor ledger."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, request: JobCreate) -> Job:
        now = self._now()
        job = Job(id=uuid.uuid4().hex, state="queued", request=request, created_at=now, updated_at=now)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def update(self, job_id: str, **changes: Any) -> Job:
        with self._lock:
            updated = self._jobs[job_id].model_copy(update={**changes, "updated_at": self._now()})
            self._jobs[job_id] = updated
            return updated
