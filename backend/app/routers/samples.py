import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from app.services import samples as svc

router = APIRouter(prefix="/samples", tags=["samples"])
MAX_UPLOAD = 200 * 1024 * 1024


def _dir(request: Request) -> Path:
    return request.app.state.samples_dir


def _lookup(request: Request, sample_id: str) -> tuple[Path, dict[str, Any]]:
    # Only ids produced by the scan resolve to files: no path is built from user input.
    found = svc.scan(_dir(request)).get(sample_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"sample {sample_id!r} not found")
    return found


def _parse_dt(value: str | None, name: str) -> datetime | None:
    if not value:
        return None
    dt = svc.parse_datetime(value)
    if dt is None:
        raise HTTPException(status_code=422, detail=f"{name} is not a valid date")
    return dt


@router.get("")
def list_samples(
    request: Request,
    bbox: str | None = Query(None, description="minx,miny,maxx,maxy in EPSG:4326"),
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    box = None
    if bbox:
        try:
            box = tuple(float(v) for v in bbox.split(","))
            assert len(box) == 4
        except (ValueError, AssertionError):
            raise HTTPException(status_code=422, detail="bbox needs 4 comma-separated numbers") from None
    items = svc.list_items(_dir(request), box, _parse_dt(start, "start"), _parse_dt(end, "end"))  # type: ignore[arg-type]
    return {"items": items}


@router.get("/{sample_id}")
def get_sample(request: Request, sample_id: str) -> dict[str, Any]:
    return _lookup(request, sample_id)[1]


@router.get("/{sample_id}/file")
def get_file(request: Request, sample_id: str) -> FileResponse:
    path, _ = _lookup(request, sample_id)
    return FileResponse(path, media_type="image/tiff", filename=path.name)


@router.get("/{sample_id}/preview.png")
def get_preview(request: Request, sample_id: str) -> Response:
    path, _ = _lookup(request, sample_id)
    try:
        payload, bounds = svc.preview_png(path)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"preview failed: {error}") from error
    return Response(
        payload,
        media_type="image/png",
        headers={"X-Bounds-WGS84": ",".join(f"{v:.6f}" for v in bounds), "Access-Control-Expose-Headers": "X-Bounds-WGS84"},
    )


@router.post("", status_code=201)
def upload(
    request: Request,
    file: UploadFile = File(...),
    datetime_value: str | None = Form(None, alias="datetime"),
    label: str | None = Form(None),
) -> dict[str, Any]:
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in svc.EXTENSIONS:
        raise HTTPException(status_code=422, detail="only .tif/.tiff files are accepted")
    if datetime_value and svc.parse_datetime(datetime_value) is None:
        raise HTTPException(status_code=422, detail="datetime is not a valid ISO 8601 date")
    directory = _dir(request)
    directory.mkdir(parents=True, exist_ok=True)
    stem = svc.slug(Path(name).stem)
    target = directory / f"{stem}{Path(name).suffix.lower()}"
    if svc.slug(stem) in svc.scan(directory) or target.exists():
        raise HTTPException(status_code=409, detail=f"sample {stem!r} already exists")
    tmp = directory / f".upload-{stem}.part"
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(status_code=413, detail="file exceeds 200 MB")
                out.write(chunk)
        try:
            svc.validate_geotiff(tmp)
        except Exception as error:
            raise HTTPException(status_code=422, detail=f"not a readable GeoTIFF: {error}") from error
        shutil.move(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    side = {k: v for k, v in {"datetime": datetime_value, "label": label}.items() if v}
    if side:
        target.with_suffix(".json").write_text(json.dumps(side, ensure_ascii=False, indent=2))
    return svc.scan(directory)[stem][1]
