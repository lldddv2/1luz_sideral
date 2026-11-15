"""Local sample GeoTIFFs dropped in data/samples/.

Each file is indexed by its space (bounds reprojected to EPSG:4326) and time.
Time source order: sidecar <stem>.json, TIFF tags, filename date, else none.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

EXTENSIONS = (".tif", ".tiff")
MAX_PREVIEW = 1024

_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_DATE_TAG_HINTS = ("DATETIME", "DATE_TIME", "ACQUISITION", "DATE", "TIME", "START")
_FILENAME_PATTERNS = (
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"),
)


def slug(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-").lower() or "sample"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _valid(dt: datetime | None) -> bool:
    return dt is not None and 1900 <= dt.year <= 2100


def date_from_tags(tags: dict[str, dict[str, str]]) -> tuple[datetime, str] | None:
    # Exact well-known keys first, then anything that looks like a date tag.
    for wanted in ("TIFFTAG_DATETIME", "ACQUISITION_DATE", "DATE_TIME"):
        for ns, values in tags.items():
            if wanted in values and _valid(dt := parse_datetime(values[wanted])):
                return dt, f"tag:{ns}:{wanted}" if ns else f"tag:{wanted}"
    for ns, values in tags.items():
        for key, raw in values.items():
            if any(h in key.upper() for h in _DATE_TAG_HINTS) and _valid(dt := parse_datetime(str(raw))):
                return dt, f"tag:{ns}:{key}" if ns else f"tag:{key}"
    return None


def date_from_name(name: str) -> datetime | None:
    for pattern in _FILENAME_PATTERNS:
        if m := pattern.search(name):
            try:
                dt = datetime(*(int(g) for g in m.groups()))
            except ValueError:
                continue
            if _valid(dt):
                return dt
    return None


def _all_tags(src) -> dict[str, dict[str, str]]:
    tags = {"": dict(src.tags())}
    for ns in src.tag_namespaces() or []:
        try:
            tags[ns] = dict(src.tags(ns=ns))
        except Exception:
            pass
    tags = {k: v for k, v in tags.items() if v}
    return tags


def _sidecar(path: Path) -> dict[str, Any]:
    side = path.with_suffix(".json")
    if not side.exists():
        return {}
    try:
        data = json.loads(side.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def describe(path: Path) -> dict[str, Any]:
    side = _sidecar(path)
    with rasterio.open(path) as src:
        tags = _all_tags(src)
        crs = src.crs.to_string() if src.crs else None
        bounds = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds)) if src.crs else None
        info = {
            "crs": crs,
            "bounds_native": list(src.bounds),
            "bounds_wgs84": bounds,
            "res": list(src.res),
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
        }
    dt, source = None, "none"
    if side.get("datetime") and _valid(parsed := parse_datetime(str(side["datetime"]))):
        dt, source = parsed, "sidecar"
    elif found := date_from_tags(tags):
        dt, source = found
    elif parsed := date_from_name(path.stem):
        dt, source = parsed, "filename"
    item = {
        "id": slug(path.stem),
        "filename": path.name,
        "datetime": _iso(dt) if dt else None,
        "time_source": source,
        **info,
        "size_bytes": path.stat().st_size,
        "tags": tags,
    }
    for key in ("label", "sensor", "polarization", "notes"):
        if side.get(key):
            item[key] = side[key]
    return item


def scan(directory: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    out: dict[str, tuple[Path, dict[str, Any]]] = {}
    if not directory.exists():
        return out
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in EXTENSIONS or not path.is_file():
            continue
        side = path.with_suffix(".json")
        mtime = max(path.stat().st_mtime, side.stat().st_mtime if side.exists() else 0)
        key = str(path.resolve())
        cached = _cache.get(key)
        if cached is None or cached[0] != mtime:
            try:
                cached = (mtime, describe(path))
            except Exception:
                continue  # unreadable file: skip, do not break the listing
            _cache[key] = cached
        meta = cached[1]
        out.setdefault(meta["id"], (path, meta))
    return out


def _overlaps(a: list[float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def list_items(
    directory: Path,
    bbox: tuple[float, float, float, float] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    items = []
    for _, meta in scan(directory).values():
        if bbox and (meta["bounds_wgs84"] is None or not _overlaps(meta["bounds_wgs84"], bbox)):
            continue
        if start or end:
            if meta["datetime"] is None:
                continue
            dt = parse_datetime(meta["datetime"])
            if start and dt < _aware(start):
                continue
            if end and dt > _aware(end):
                continue
        items.append({k: v for k, v in meta.items() if k != "tags"})
    items.sort(key=lambda m: (m["datetime"] is None, m["datetime"] or "", m["id"]))
    return items


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _stretch(band: np.ndarray, valid: np.ndarray) -> np.ndarray:
    data = band.astype("float64")
    if not valid.any():
        return np.zeros(band.shape, dtype="uint8")
    lo, hi = np.percentile(data[valid], (2, 98))
    if hi <= lo:
        hi = lo + 1
    return (np.clip((data - lo) / (hi - lo), 0, 1) * 255).astype("uint8")


def preview_png(path: Path) -> tuple[bytes, list[float]]:
    """Render to EPSG:3857 (MapLibre image sources stretch linearly in Web Mercator)."""
    with rasterio.open(path) as src:
        dst_crs = "EPSG:3857"
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        scale = max(width, height) / MAX_PREVIEW
        if scale > 1:
            width, height = max(1, round(width / scale)), max(1, round(height / scale))
        bounds3857 = transform_bounds(src.crs, dst_crs, *src.bounds)
        transform = rasterio.transform.from_bounds(*bounds3857, width, height)
        bands = [1, 2, 3] if src.count >= 3 else [1]
        dst = np.zeros((len(bands), height, width), dtype="float64")
        nodata = src.nodata
        fill = nodata if nodata is not None else np.nan
        for i, b in enumerate(bands):
            reproject(
                rasterio.band(src, b),
                dst[i],
                dst_transform=transform,
                dst_crs=dst_crs,
                dst_nodata=fill,
                resampling=Resampling.bilinear if src.count < 3 else Resampling.nearest,
            )
    valid = np.isfinite(dst).all(axis=0)
    if nodata is not None and not np.isnan(nodata):
        valid &= ~(dst == nodata).any(axis=0)
    if len(bands) == 3:
        # Treat all-zero pixels as nodata too (outside-swath fill in typical RGB samples).
        valid &= dst.sum(axis=0) > 0
    rgb = [_stretch(dst[i], valid) for i in range(len(bands))]
    if len(rgb) == 1:
        rgb = rgb * 3
    alpha = np.where(valid, 255, 0).astype("uint8")
    image = np.stack(rgb + [alpha])
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="PNG", width=width, height=height, count=4, dtype="uint8"
    ) as png:
        png.write(image)
    bounds_wgs84 = list(transform_bounds(dst_crs, "EPSG:4326", *bounds3857))
    return buf.getvalue(), bounds_wgs84


def validate_geotiff(path: Path) -> None:
    with rasterio.open(path) as src:
        if src.driver != "GTiff":
            raise ValueError(f"not a GeoTIFF (driver {src.driver})")
        if src.crs is None:
            raise ValueError("GeoTIFF has no CRS")
