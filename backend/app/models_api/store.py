"""In-memory sessions (one per web token), jobs and per-token SSE queues."""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

TOKEN_TTL_S = 2 * 3600
CONNECTED_S = 30.0


@dataclass
class Job:
    id: str
    token: str
    bbox: list[float]
    date: str | None
    pols: list[str] = field(default_factory=lambda: ["HH"])
    output: str = "probability"
    label: str | None = None
    units: str | None = None
    state: str = "queued"
    scene_id: str | None = None
    datetime: str | None = None
    bounds: list[float] | None = None
    stats: dict[str, Any] | None = None
    legend: dict[str, Any] | None = None
    png_url: str | None = None
    error: str | None = None
    input_path: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def event(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.id, "state": self.state, "output": self.output,
            "label": self.label, "units": self.units, "pols": self.pols,
        }
        for k in ("scene_id", "datetime", "bounds", "stats", "legend", "png_url", "error"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out


@dataclass
class Session:
    token: str
    expires_at: float
    name: str | None = None
    output: str = "probability"
    label: str | None = None
    units: str | None = None
    pols: list[str] = field(default_factory=lambda: ["HH"])
    last_seen: float | None = None
    pending: asyncio.Queue = field(default_factory=asyncio.Queue)  # job ids for the model
    events: asyncio.Queue = field(default_factory=asyncio.Queue)  # SSE (event, data) for the page

    def connected(self) -> bool:
        return self.last_seen is not None and time.time() - self.last_seen <= CONNECTED_S

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected(), "name": self.name, "output": self.output,
            "label": self.label, "units": self.units, "pols": self.pols, "last_seen": self.last_seen,
        }


class Store:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.jobs: dict[str, Job] = {}

    def new_token(self) -> Session:
        self._purge()
        s = Session(secrets.token_urlsafe(24), time.time() + TOKEN_TTL_S)
        self.sessions[s.token] = s
        return s

    def get(self, token: str | None) -> Session | None:
        s = self.sessions.get(token or "")
        if s is None or s.expires_at < time.time():
            return None
        return s

    def touch(self, s: Session) -> None:
        was = s.connected()
        s.last_seen = time.time()
        if not was:
            self.push(s, "status", s.status())

    def push(self, s: Session, event: str, data: dict[str, Any]) -> None:
        s.events.put_nowait((event, data))

    def push_job(self, job: Job) -> None:
        s = self.sessions.get(job.token)
        if s is not None:
            self.push(s, "job", job.event())

    def _purge(self) -> None:
        now = time.time()
        for t in [t for t, s in self.sessions.items() if s.expires_at < now]:
            del self.sessions[t]
            for j in [j for j, job in self.jobs.items() if job.token == t]:
                del self.jobs[j]
