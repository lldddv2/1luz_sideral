import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services import nisar_s3, samples, scenes as svc

router = APIRouter(prefix="/scenes", tags=["scenes"])


class SceneQuery(BaseModel):
    regions: dict[str, Any] = Field(description="GeoJSON FeatureCollection, Feature or Polygon/MultiPolygon in WGS84")
    date: str | None = Field(default=None, description="ISO date; keeps scenes within window_days")
    window_days: int = Field(default=15, ge=0, le=365)
    start: str | None = None
    end: str | None = None
    source: Literal["samples", "nisar"] = "samples"


class SceneDataRequest(BaseModel):
    geometry: dict[str, Any] = Field(description="Polygon/MultiPolygon or Feature in WGS84")
    format: Literal["geotiff", "png", "json"] = "png"
    width: int | None = Field(default=None, ge=16, le=2048)
    height: int | None = Field(default=None, ge=16, le=2048)
    fit: Literal["pad", "stretch"] = "pad"
    resampling: Literal["average", "bilinear", "nearest"] = "average"
    mask: bool = True
    source: Literal["samples", "nisar"] = "samples"
    polarization: Literal["HH", "HV"] = Field(default="HH", description="NISAR only")


def _dt(value: str | None, name: str):
    if not value:
        return None
    dt = samples.parse_datetime(value)
    if dt is None:
        raise HTTPException(status_code=422, detail=f"{name} is not a valid date")
    return dt


def _nisar_index() -> dict[str, Any]:
    name = nisar_s3.bucket()
    if not name:
        raise HTTPException(status_code=501, detail="source 'nisar' needs NISAR_BUCKET")
    try:
        return nisar_s3.load_index(name)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"NISAR index unavailable: {type(error).__name__}") from error


@router.post("/query")
def query(request: Request, body: SceneQuery) -> dict[str, Any]:
    if body.date and (body.start or body.end):
        raise HTTPException(status_code=422, detail="use date or start/end, not both")
    try:
        regions = svc.parse_regions(body.regions)
    except svc.SceneError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if body.source == "nisar":
        return nisar_s3.query(
            _nisar_index(), regions, _dt(body.date, "date"), body.window_days,
            _dt(body.start, "start"), _dt(body.end, "end"),
        )
    return svc.query(
        request.app.state.samples_dir, regions, _dt(body.date, "date"), body.window_days,
        _dt(body.start, "start"), _dt(body.end, "end"),
    )


@router.post("/{scene_id}/data")
def data(request: Request, scene_id: str, body: SceneDataRequest) -> Response:
    if body.source == "nisar":
        scene = nisar_s3.find(_nisar_index(), scene_id)
        path = nisar_s3.vsis3_path(nisar_s3.bucket(), scene, body.polarization) if scene else None
        if path is None:
            raise HTTPException(status_code=404, detail=f"scene {scene_id!r} ({body.polarization}) not found")
    else:
        found = samples.scan(request.app.state.samples_dir).get(scene_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"scene {scene_id!r} not found")
        path = found[0]
    try:
        r = svc.read_region(path, body.geometry, body.width, body.height, body.fit, body.resampling, body.mask)
    except svc.SceneError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    headers = {
        "X-Bounds-WGS84": ",".join(f"{v:.6f}" for v in r["bounds_wgs84"]),
        "X-Pixel-Size-M": str(r["pixel_size_m"]),
        "X-Out-Size": f"{r['width']}x{r['height']}",
        "X-CRS": r["crs"].to_string(),
        "X-Corners-WGS84": json.dumps(svc.corners_wgs84(r), separators=(",", ":")),
        "Access-Control-Expose-Headers": "X-Bounds-WGS84, X-Pixel-Size-M, X-Out-Size, X-CRS, X-Corners-WGS84",
    }
    if body.format == "json":
        return Response(json.dumps(svc.to_stats(r)), media_type="application/json", headers=headers)
    if body.format == "geotiff":
        return Response(svc.to_geotiff(r), media_type="image/tiff", headers=headers)
    # PNG stays in the scene's native CRS (no reprojection); see X-CRS.
    headers["X-Note"] = "png in native scene CRS, not reprojected"
    return Response(svc.to_png(r), media_type="image/png", headers=headers)
