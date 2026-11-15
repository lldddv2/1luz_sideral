"""External model bridge (see .project/model-api.md): the page gets a token, a local model pulls jobs with it."""

import asyncio
import datetime as dt
import json
import logging
import re
import secrets
import time
from pathlib import Path
from typing import Any, Literal

import requests
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.models_api import raster
from app.models_api.store import Job, Session, Store
from app.water import service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])

LONG_POLL_S = 25.0
SSE_PING_S = 10.0


def _store(request: Request) -> Store:
    st = getattr(request.app.state, "models", None)
    if st is None:
        st = request.app.state.models = Store()
    return st


def _dir(request: Request) -> Path:
    return request.app.state.models_dir


def _auth(request: Request) -> Session:
    h = request.headers.get("authorization", "")
    token = h[7:].strip() if h.lower().startswith("bearer ") else None
    s = _store(request).get(token)
    if s is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return s


def _job(request: Request, s: Session, job_id: str) -> Job:
    job = _store(request).jobs.get(job_id)
    if job is None or job.token != s.token:
        raise HTTPException(status_code=404, detail="job not found")
    return job


class Hello(BaseModel):
    name: str
    output: Literal["probability", "continuous", "classes"] | None = None
    kind: str | None = None  # legacy: "water_prob" means output "probability"
    pols: list[str] = ["HH"]
    label: str | None = None
    units: str | None = None


class JobRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="west,south,east,north (EPSG:4326)")
    date: dt.date | None = None


@router.post("/token")
def new_token(request: Request) -> dict[str, Any]:
    s = _store(request).new_token()
    return {"token": s.token, "expires_at": s.expires_at}


@router.post("/hello")
def hello(request: Request, body: Hello, s: Session = Depends(_auth)) -> dict[str, Any]:
    try:
        pols = raster.check_pols(body.pols)
    except raster.UnknownPol as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    s.name, s.pols, s.label, s.units = body.name, pols, body.label, body.units
    s.output = body.output or "probability"
    s.last_seen = None  # force a status event carrying the new name
    _store(request).touch(s)
    return {"ok": True}


@router.get("/status")
def status(s: Session = Depends(_auth)) -> dict[str, Any]:
    return s.status()


@router.post("/jobs")
def create_job(request: Request, body: JobRequest, s: Session = Depends(_auth)) -> dict[str, Any]:
    try:
        raster.check_aoi(tuple(body.bbox))
    except (service.AoiTooLarge, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    st = _store(request)
    job = Job(
        secrets.token_urlsafe(12), s.token, list(body.bbox), body.date.isoformat() if body.date else None,
        pols=list(s.pols), output=s.output, label=s.label, units=s.units,
    )
    st.jobs[job.id] = job
    s.pending.put_nowait(job.id)
    st.push_job(job)
    return {"job_id": job.id}


@router.get("/jobs/next")
async def next_job(request: Request, s: Session = Depends(_auth)) -> Response:
    st = _store(request)
    st.touch(s)
    deadline = time.monotonic() + LONG_POLL_S
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return Response(status_code=204)
        try:
            job_id = await asyncio.wait_for(s.pending.get(), timeout=min(left, 10.0))
        except asyncio.TimeoutError:
            st.touch(s)  # a waiting model counts as connected
            continue
        job = st.jobs.get(job_id)
        if job is None or job.state != "queued":
            continue
        job.state = "running"
        st.touch(s)
        st.push_job(job)
        return Response(
            content=json.dumps({
                "job_id": job.id, "bbox": job.bbox, "date": job.date,
                "pols": job.pols, "input_url": f"/api/models/jobs/{job.id}/input.tif",
            }),
            media_type="application/json",
        )


def _fail(st: Store, job: Job, msg: str) -> None:
    job.state, job.error = "error", msg
    st.push_job(job)


@router.get("/jobs/{job_id}/input.tif")
async def job_input(request: Request, job_id: str, s: Session = Depends(_auth)) -> FileResponse:
    st = _store(request)
    job = _job(request, s, job_id)
    async with job.lock:
        if job.input_path is None:
            date = dt.date.fromisoformat(job.date) if job.date else None
            try:
                path, meta = await run_in_threadpool(raster.build_input, job.bbox, date, _dir(request), job.pols)
            except service.NoScene as error:
                _fail(st, job, str(error))
                raise HTTPException(status_code=404, detail=str(error)) from error
            except requests.exceptions.RequestException as error:
                log.exception("model input: Earthdata error")
                _fail(st, job, "No se pudo leer el dato NISAR desde NASA Earthdata.")
                raise HTTPException(status_code=502, detail=job.error) from error
            except Exception as error:
                log.exception("model input failed")
                _fail(st, job, "Falló la preparación del dato de entrada.")
                raise HTTPException(status_code=502, detail=job.error) from error
            job.input_path = str(path)
            job.scene_id, job.datetime = meta["scene_id"], meta["datetime"]
            st.push_job(job)
    return FileResponse(job.input_path, media_type="image/tiff", filename="input.tif")


@router.post("/jobs/{job_id}/result")
async def job_result(
    request: Request, job_id: str, file: UploadFile = File(...), s: Session = Depends(_auth)
) -> dict[str, Any]:
    st = _store(request)
    job = _job(request, s, job_id)
    st.touch(s)
    if job.input_path is None:
        raise HTTPException(status_code=409, detail="input.tif was never fetched for this job")
    data = await file.read()
    png = _dir(request) / f"{job.id}.png"
    try:
        out = await run_in_threadpool(raster.render_result, Path(job.input_path), data, png, job.output)
    except Exception as error:  # bad raster or grid mismatch: the model sent something wrong
        _fail(st, job, f"Resultado inválido: {error}")
        raise HTTPException(status_code=400, detail=job.error) from error
    job.state, job.error = "done", None
    job.bounds, job.stats, job.legend = out["bounds"], out["stats"], out["legend"]
    job.png_url = f"/api/models/jobs/{job.id}.png"
    st.push_job(job)
    return {"ok": True, "png_url": job.png_url}


@router.get("/jobs/{job_id}.png")
def job_png(request: Request, job_id: str) -> FileResponse:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16}", job_id):
        raise HTTPException(status_code=404, detail="not found")
    path = _dir(request) / f"{job_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/png")


def _status(s: Session) -> dict[str, Any]:
    out = s.status()
    out.pop("last_seen", None)
    return out


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def event_stream(request: Request, s: Session, st: Store):
    yield _sse("status", _status(s))
    was = s.connected()
    while st.get(s.token) is not None:
        if await request.is_disconnected():
            break
        try:
            event, data = await asyncio.wait_for(s.events.get(), timeout=SSE_PING_S)
        except asyncio.TimeoutError:
            now = s.connected()
            yield _sse("status", _status(s)) if now != was else ": ping\n\n"
            was = now
            continue
        if event == "status":
            was = data["connected"]
        yield _sse(event, data)


@router.get("/events")
async def events(request: Request, token: str) -> StreamingResponse:
    st = _store(request)
    s = st.get(token)
    if s is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return StreamingResponse(
        event_stream(request, s, st), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
