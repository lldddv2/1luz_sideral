from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.services import dem as dem_service

router = APIRouter(prefix="/dem", tags=["dem"])


def _disposition(name: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


def _errors(error: Exception) -> HTTPException:
    if isinstance(error, dem_service.DemTileMissingError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=502, detail=f"DEM read failed: {error}")


# Sync handlers: remote reads block, FastAPI runs them in a threadpool.
@router.get("/metadata")
def metadata(lat: float = Query(...), lon: float = Query(...)) -> dict[str, Any]:
    try:
        return dem_service.metadata(lat, lon)
    except Exception as error:
        raise _errors(error) from error


@router.get("/file")
def file(lat: float = Query(...), lon: float = Query(...)) -> StreamingResponse:
    try:
        name, chunks = dem_service.stream_file(lat, lon)
    except Exception as error:
        raise _errors(error) from error
    return StreamingResponse(chunks, media_type="image/tiff", headers=_disposition(name))


@router.get("/crop")
def crop(bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:4326")) -> Response:
    try:
        parts = tuple(float(v) for v in bbox.split(","))
        if len(parts) != 4:
            raise ValueError("bbox needs 4 comma-separated numbers")
        name, payload = dem_service.crop(parts)  # type: ignore[arg-type]
    except Exception as error:
        raise _errors(error) from error
    return Response(payload, media_type="image/tiff", headers=_disposition(name))
