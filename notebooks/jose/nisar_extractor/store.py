from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JobConflict(RuntimeError):
    pass


class JobStore:
    """SQLite-backed job ledger with an atomic idempotency-key reservation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.Lock()
        with self._schema_lock:
            con = self._connect()
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    job_id TEXT,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    output_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            con.close()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA synchronous=FULL")
        return con

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result["outputs"] = json.loads(result.pop("output_json") or "[]")
        return result

    def get(self, key: str) -> dict[str, Any] | None:
        con = self._connect()
        try:
            return self._decode(con.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone())
        finally:
            con.close()

    def reserve(self, key: str, request: dict[str, Any], *, max_attempts: int) -> tuple[dict[str, Any], bool]:
        now = self._now()
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO jobs VALUES (?, ?, NULL, 'submitting', 1, NULL, NULL, ?, ?)",
                    (key, json.dumps(request, sort_keys=True), now, now),
                )
                result = self._decode(con.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone())
                con.commit()
                return result, True

            item = self._decode(row)
            if item["state"] in {"submitting", "submission_unknown"} and not item["job_id"]:
                raise JobConflict(
                    "A previous Harmony submission has no recorded job ID; refusing to risk a duplicate job"
                )
            if item["state"] in {"submitted", "running", "successful", "downloaded", "poll_error"} and item["job_id"]:
                con.commit()
                return item, False
            if item["attempts"] >= max_attempts:
                raise JobConflict(
                    f"Request previously failed after {item['attempts']} controlled attempts; inspect the job ledger"
                )
            con.execute(
                """UPDATE jobs SET request_json=?, job_id=NULL, state='submitting',
                    attempts=attempts+1, output_json=NULL, error=NULL, updated_at=?
                    WHERE idempotency_key=?""",
                (json.dumps(request, sort_keys=True), now, key),
            )
            result = self._decode(con.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone())
            con.commit()
            return result, True
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def update(
        self,
        key: str,
        *,
        state: str,
        job_id: str | None = None,
        outputs: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        con = self._connect()
        try:
            con.execute(
                """UPDATE jobs SET state=?, job_id=COALESCE(?, job_id),
                    output_json=COALESCE(?, output_json), error=?, updated_at=?
                    WHERE idempotency_key=?""",
                (
                    state,
                    job_id,
                    json.dumps(outputs, sort_keys=True) if outputs is not None else None,
                    error,
                    self._now(),
                    key,
                ),
            )
        finally:
            con.close()

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            rows = con.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._decode(row) for row in rows]
        finally:
            con.close()
