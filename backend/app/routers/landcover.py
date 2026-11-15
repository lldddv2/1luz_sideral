from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException

from app.schemas import (
    LandcoverClass,
    LandcoverMask,
    LandcoverMaskRequest,
    LandcoverRequest,
    LandcoverStats,
)
from app.services import landcover as landcover_service

router = APIRouter(prefix="/landcover", tags=["landcover"])

T = TypeVar("T")


def _run(call: Callable[..., T], *args: Any) -> T:
    # Bad geometry, too large an AOI and unknown class keys are ValueError: 422.
    # A tile that exists but cannot be read is a remote failure: 502.
    try:
        return call(*args)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except landcover_service.LandcoverUnavailableError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


# Sync like /search: remote COG reads block, so FastAPI runs this in a threadpool.
@router.get("/classes", response_model=list[LandcoverClass])
def classes() -> list[dict[str, Any]]:
    return [asdict(cls) for cls in landcover_service.CLASSES]


@router.post("/stats", response_model=LandcoverStats)
def stats(body: LandcoverRequest) -> dict[str, Any]:
    return _run(landcover_service.stats, body.geometry)


@router.post("/mask", response_model=LandcoverMask)
def mask(body: LandcoverMaskRequest) -> dict[str, Any]:
    return _run(landcover_service.mask, body.geometry, body.classes, body.max_px)
