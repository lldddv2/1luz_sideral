import re
import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.water import service

router = APIRouter(prefix="/water", tags=["water"])


class WaterRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="west,south,east,north (EPSG:4326)")
    date: dt.date | None = Field(None, description="Use the latest scene on or before this day")


def _cache(request: Request) -> Path:
    return request.app.state.water_dir


@router.post("")
def detect_water(request: Request, body: WaterRequest) -> dict[str, Any]:
    try:
        info = service.run(tuple(body.bbox), body.date, _cache(request))
    except service.AoiTooLarge as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except service.NoScene as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"water detection failed: {error}") from error
    info["png_url"] = f"/api/water/{info['id']}.png"
    return info


@router.get("/{key}.png")
def water_png(request: Request, key: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{16}", key):
        raise HTTPException(status_code=404, detail="not found")
    path = _cache(request) / f"{key}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/png")
