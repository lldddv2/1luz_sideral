"""NISAR GCOV scenes cropped in AWS (backend/cloud/nisar_crop.py) and stored as COGs in S3.

The bucket holds nisar/gcov/index.json plus <granule_id>/{HH,HV}.tif. Reads use
GDAL /vsis3/ so only the needed COG blocks travel; credentials come from the
default AWS chain.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from typing import Any

from shapely.geometry import mapping, shape

from app.services import samples

INDEX_KEY = "nisar/gcov/index.json"
_CACHE_SECONDS = 60
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def bucket() -> str | None:
    return os.environ.get("NISAR_BUCKET")


def region_name() -> str:
    return os.environ.get("AWS_REGION", "us-west-2")


def fetch_index(name: str) -> dict[str, Any]:
    import boto3

    body = boto3.client("s3", region_name=region_name()).get_object(Bucket=name, Key=INDEX_KEY)["Body"].read()
    return json.loads(body)


def load_index(name: str) -> dict[str, Any]:
    hit = _cache.get(name)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    index = fetch_index(name)
    _cache[name] = (time.time(), index)
    return index


def find(index: dict[str, Any], scene_id: str) -> dict[str, Any] | None:
    return next((s for s in index.get("scenes", []) if s["granule_id"] == scene_id), None)


def vsis3_path(name: str, scene: dict[str, Any], polarization: str) -> str | None:
    asset = scene.get("assets", {}).get(polarization)
    return f"/vsis3/{name}/{asset['key']}" if asset else None


def query(
    index: dict[str, Any],
    regions: list[tuple[str, Any]],
    date: datetime | None = None,
    window_days: int = 15,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    if date is not None:
        date = samples._aware(date)
        start, end = date - timedelta(days=window_days), date + timedelta(days=window_days)
    start = samples._aware(start) if start else None
    end = samples._aware(end) if end else None
    features = []
    for scene in index.get("scenes", []):
        acquired = samples.parse_datetime(scene["acquired_start"])
        if (start and acquired < start) or (end and acquired > end):
            continue
        # The stored COG covers only the AOI crop, so coverage is measured against it.
        crop = shape(scene["aoi"]["geometry"]).intersection(shape(scene["footprint"]))
        hits = []
        for rid, geom in regions:
            inter = geom.intersection(crop).area
            if inter > 0:
                hits.append({"id": rid, "coverage_pct": round(100 * inter / geom.area, 2)})
        if not hits:
            continue
        sid = scene["granule_id"]
        props = {
            "scene_id": sid,
            "source": "nisar",
            "acquired_at": scene["acquired_start"],
            "time_source": "granule",
            "regions": hits,
            "native_res_m": scene.get("pixel_size_m"),
            "crs": scene.get("crs"),
            "count": 1,
            "dtype": "float32",
            "track": scene.get("track"),
            "frame": scene.get("frame"),
            "direction": scene.get("direction"),
            "polarizations": scene.get("polarizations", []),
            "units": scene.get("units"),
            "assets": {"data": f"/api/scenes/{sid}/data"},
        }
        if date is not None:
            props["days_from_date"] = round((acquired - date).total_seconds() / 86400, 3)
        features.append({"type": "Feature", "geometry": mapping(crop.envelope), "properties": props})
    if date is not None:
        features.sort(key=lambda f: abs(f["properties"]["days_from_date"]))
    else:
        features.sort(key=lambda f: f["properties"]["acquired_at"])
    return {"type": "FeatureCollection", "features": features}
