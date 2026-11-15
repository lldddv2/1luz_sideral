"""Scene search and region-clipped reads over local sample GeoTIFFs.

A scene is one acquisition (today: one file in data/samples). Regions arrive as
GeoJSON in WGS84; reads reproject the region to the scene CRS and never warp pixels.
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_bounds as transform_from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds as window_from_bounds
from shapely.geometry import box, mapping, shape

from app.services import samples

MAX_REGIONS = 10
MAX_VERTICES = 5000
MAX_SIDE = 2048
MAX_PIXELS = 4_194_304
RESAMPLING = {"average": Resampling.average, "bilinear": Resampling.bilinear, "nearest": Resampling.nearest}


class SceneError(ValueError):
    """Bad request (422)."""


def _geom_of(obj: dict[str, Any]) -> dict[str, Any]:
    geom = obj.get("geometry") if obj.get("type") == "Feature" else obj
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise SceneError("geometry must be a Polygon or MultiPolygon")
    return geom


def parse_regions(obj: dict[str, Any]) -> list[tuple[str, Any]]:
    """FeatureCollection, Feature or bare geometry into [(id, shapely geometry)]."""
    if obj.get("type") == "FeatureCollection":
        feats = obj.get("features") or []
    else:
        feats = [obj]
    if not feats:
        raise SceneError("no regions given")
    if len(feats) > MAX_REGIONS:
        raise SceneError(f"at most {MAX_REGIONS} regions")
    out, vertices = [], 0
    for i, feat in enumerate(feats, 1):
        props = (feat.get("properties") or {}) if feat.get("type") == "Feature" else {}
        rid = str(props.get("id") or feat.get("id") or f"r{i}")
        try:
            geom = shape(_geom_of(feat))
        except SceneError:
            raise
        except Exception as error:
            raise SceneError(f"region {rid}: invalid geometry ({error})") from error
        vertices += len(geom.exterior.coords) if geom.geom_type == "Polygon" else sum(
            len(p.exterior.coords) for p in geom.geoms
        )
        if not geom.is_valid:
            geom = geom.buffer(0)
        out.append((rid, geom))
    if vertices > MAX_VERTICES:
        raise SceneError(f"at most {MAX_VERTICES} vertices in total")
    return out


def _to_m(res: float, crs, lat: float) -> float:
    if crs is not None and crs.is_geographic:
        return res * 111_320 * math.cos(math.radians(lat))
    return res


def query(
    directory: Path,
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
    for sid, (_, meta) in samples.scan(directory).items():
        if meta["bounds_wgs84"] is None:
            continue
        acquired = samples.parse_datetime(meta["datetime"]) if meta["datetime"] else None
        if start or end:
            if acquired is None or (start and acquired < start) or (end and acquired > end):
                continue
        foot = box(*meta["bounds_wgs84"])
        hits = []
        for rid, geom in regions:
            inter = geom.intersection(foot).area
            if inter > 0:
                hits.append({"id": rid, "coverage_pct": round(100 * inter / geom.area, 2)})
        if not hits:
            continue
        lat = (meta["bounds_wgs84"][1] + meta["bounds_wgs84"][3]) / 2
        crs = rasterio.crs.CRS.from_user_input(meta["crs"])
        props = {
            "scene_id": sid,
            "source": "samples",
            "acquired_at": meta["datetime"],
            "time_source": meta["time_source"],
            "regions": hits,
            "native_res_m": round(_to_m(abs(meta["res"][0]), crs, lat), 3),
            "crs": meta["crs"],
            "count": meta["count"],
            "dtype": meta["dtype"],
            "assets": {"data": f"/api/scenes/{sid}/data"},
        }
        if date is not None:
            props["days_from_date"] = round((acquired - date).total_seconds() / 86400, 3) if acquired else None
        features.append({"type": "Feature", "geometry": mapping(foot), "properties": props})
    if date is not None:
        features.sort(key=lambda f: abs(f["properties"]["days_from_date"]))
    else:
        features.sort(key=lambda f: (f["properties"]["acquired_at"] is None, f["properties"]["acquired_at"] or ""))
    return {"type": "FeatureCollection", "features": features}


def _out_size(aspect: float, native: tuple[int, int], width: int | None, height: int | None) -> tuple[int, int]:
    if width and height:
        return width, height
    if width:
        return width, max(1, round(width / aspect))
    if height:
        return max(1, round(height * aspect)), height
    w, h = native
    scale = max(w, h) / MAX_SIDE
    if scale > 1:
        w, h = max(1, round(w / scale)), max(1, round(h / scale))
    return w, h


def read_region(
    path: Path,
    geometry: dict[str, Any],
    width: int | None = None,
    height: int | None = None,
    fit: str = "pad",
    resampling: str = "average",
    mask: bool = True,
) -> dict[str, Any]:
    """Clip the scene to the region bbox and resample to the requested size.

    SAR note: "average" should run on linear power (not dB) for radar backscatter;
    the current samples are not SAR so values are averaged as stored.
    """
    geom_wgs = _geom_of(geometry)
    with rasterio.open(path) as src:
        geom = shape(transform_geom("EPSG:4326", src.crs, geom_wgs))
        inter = box(*geom.bounds).intersection(box(*src.bounds))
        if inter.is_empty or inter.area == 0 or not geom.intersects(box(*src.bounds)):
            raise SceneError("region does not intersect this scene")
        x0, y0, x1, y1 = inter.bounds
        win = window_from_bounds(x0, y0, x1, y1, src.transform)
        native = (max(1, round(win.width)), max(1, round(win.height)))
        aspect = (x1 - x0) / (y1 - y0)
        W, H = _out_size(aspect, native, width, height)
        if W * H > MAX_PIXELS:
            raise SceneError(f"width*height must be <= {MAX_PIXELS}")
        if fit == "pad" and width and height:
            if W / H > aspect:
                cw, ch = max(1, round(H * aspect)), H
            else:
                cw, ch = W, max(1, round(W / aspect))
        else:
            cw, ch = W, H
        float_dtype = np.issubdtype(np.dtype(src.dtypes[0]), np.floating)
        nodata = src.nodata if src.nodata is not None else (float("nan") if float_dtype else 0)
        data = src.read(out_shape=(src.count, ch, cw), window=win, resampling=RESAMPLING[resampling], masked=True)
        content_t = transform_from_bounds(x0, y0, x1, y1, cw, ch)
        ox, oy = (W - cw) // 2, (H - ch) // 2
        canvas_t = content_t @ Affine.translation(-ox, -oy)
        valid = np.zeros((H, W), dtype=bool)
        arr = np.full((src.count, H, W), nodata, dtype=src.dtypes[0])
        arr[:, oy:oy + ch, ox:ox + cw] = data.filled(nodata)
        content_valid = ~np.ma.getmaskarray(data).any(axis=0)
        if float_dtype:
            content_valid &= np.isfinite(data.filled(np.nan)).all(axis=0)
        valid[oy:oy + ch, ox:ox + cw] = content_valid
        if mask:
            valid &= geometry_mask([mapping(geom)], out_shape=(H, W), transform=canvas_t, invert=True)
            arr[:, ~valid] = nodata
        bounds_wgs84 = list(transform_bounds(src.crs, "EPSG:4326", x0, y0, x1, y1))
        lat = (bounds_wgs84[1] + bounds_wgs84[3]) / 2
        return {
            "array": arr,
            "valid": valid,
            "transform": canvas_t,
            "crs": src.crs,
            "nodata": nodata,
            "dtype": src.dtypes[0],
            "bounds_wgs84": bounds_wgs84,
            "pixel_size_m": round(_to_m(abs(canvas_t.a), src.crs, lat), 3),
            "width": W,
            "height": H,
        }


def to_geotiff(r: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    count = r["array"].shape[0]
    with rasterio.open(
        buf, "w", driver="GTiff", width=r["width"], height=r["height"], count=count, dtype=r["dtype"],
        crs=r["crs"], transform=r["transform"], nodata=r["nodata"], compress="deflate",
    ) as dst:
        dst.write(r["array"])
    return buf.getvalue()


def to_png(r: dict[str, Any]) -> bytes:
    arr, valid = r["array"], r["valid"]
    bands = 3 if arr.shape[0] >= 3 else 1
    rgb = [samples._stretch(arr[i], valid) for i in range(bands)]
    if bands == 1:
        rgb = rgb * 3
    image = np.stack(rgb + [np.where(valid, 255, 0).astype("uint8")])
    buf = io.BytesIO()
    with rasterio.open(buf, "w", driver="PNG", width=r["width"], height=r["height"], count=4, dtype="uint8") as png:
        png.write(image)
    return buf.getvalue()


def to_stats(r: dict[str, Any]) -> dict[str, Any]:
    arr, valid = r["array"], r["valid"]
    total = valid.size
    bands = []
    for b in arr:
        v = b[valid].astype("float64")
        if v.size:
            bands.append({"min": float(v.min()), "max": float(v.max()), "mean": float(v.mean()),
                          "std": float(v.std()), "valid_pct": round(100 * v.size / total, 2)})
        else:
            bands.append({"min": None, "max": None, "mean": None, "std": None, "valid_pct": 0.0})
    return {"width": r["width"], "height": r["height"], "bands": bands, "bounds_wgs84": r["bounds_wgs84"],
            "pixel_size_m": r["pixel_size_m"], "crs": r["crs"].to_string()}


def corners_wgs84(r: dict[str, Any]) -> list[list[float]]:
    """Output image corners [tl, tr, br, bl] as [lon, lat], for MapLibre image sources."""
    from rasterio.warp import transform as warp_transform

    t, w, h = r["transform"], r["width"], r["height"]
    pts = [t * (0, 0), t * (w, 0), t * (w, h), t * (0, h)]
    lons, lats = warp_transform(r["crs"], "EPSG:4326", [p[0] for p in pts], [p[1] for p in pts])
    return [[round(x, 7), round(y, 7)] for x, y in zip(lons, lats)]
