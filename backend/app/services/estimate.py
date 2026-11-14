from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.errors import ShapelyError

from app.nisar_extractor import Inventory, NisarExtractor

# Fitted to one stored subset (35820 B against 33600 B of float32 pixels), not a measured TIFF header.
TIFF_OVERHEAD_BYTES = 2048


@lru_cache(maxsize=8)
def _utm_transformer(epsg: int) -> Transformer:
    return Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)


def utm_epsg(lon: float, lat: float) -> int:
    zone = min(60, max(1, math.floor((lon + 180.0) / 6.0) + 1))
    return (32600 if lat >= 0 else 32700) + zone


def bbox_extent_m(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    """Width and height in metres of a lon/lat box, measured in the UTM zone of its centre."""
    west, south, east, north = bounds
    transformer = _utm_transformer(utm_epsg((west + east) / 2, (south + north) / 2))
    steps = np.linspace(0.0, 1.0, 101)
    xs = west + (east - west) * steps
    ys = south + (north - south) * steps
    lon = np.concatenate([xs, xs, np.full_like(ys, west), np.full_like(ys, east)])
    lat = np.concatenate([np.full_like(xs, south), np.full_like(xs, north), ys, ys])
    x, y = transformer.transform(lon, lat)
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError("AOI cannot be projected to UTM")
    return float(x.max() - x.min()), float(y.max() - y.min())


def human_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    size = value / 1024
    for unit in ("KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def estimate(
    geometry: dict[str, Any],
    *,
    variables: int,
    products: int,
    spacing_m: float,
    bytes_per_pixel: int,
    inventory: Inventory | None = None,
) -> dict[str, Any]:
    """Size of the GeoTIFF subsets Harmony would return for the AOI. Arithmetic only, no network."""
    try:
        region = NisarExtractor.geojson(geometry)
    except (ValueError, KeyError, TypeError, ShapelyError) as error:
        raise ValueError(f"Invalid GeoJSON geometry ({type(error).__name__}): {error}") from error

    width_m, height_m = bbox_extent_m(region.bounds)
    width_px = math.ceil(round(width_m / spacing_m, 6))
    height_px = math.ceil(round(height_m / spacing_m, 6))
    per_file = width_px * height_px * bytes_per_pixel + TIFF_OVERHEAD_BYTES

    full_granules_bytes = None
    unsized = 0
    if inventory is not None:
        products = len(inventory.products)
        sizes = [p.estimated_size_bytes for p in inventory.products if p.estimated_size_bytes is not None]
        full_granules_bytes = sum(sizes)
        unsized = len(inventory.products) - len(sizes)

    total = per_file * variables * products
    notes = [
        f"{spacing_m:g} m pixels, {bytes_per_pixel} bytes per pixel"
        + (" (float32)" if bytes_per_pixel == 4 else ""),
        "subset is the AOI bounding box in UTM, not the polygon",
        "pixels = ceil(extent / spacing) per axis; grid-aligned Harmony windows can be up to 2 px smaller per axis",
        f"per file = pixels x bytes + {TIFF_OVERHEAD_BYTES} B overhead (fitted to one sample)",
        "no compression credited (the measured subset is LZW)",
        f"total = per file x {variables} variable(s) x {products} product(s)",
        "metadata JSON and masked copy not counted",
    ]
    if inventory is not None:
        note = f"full_granules_bytes sums CMR estimated_size_bytes of {len(inventory.products)} products"
        notes.append(note + (f"; {unsized} without a size excluded" if unsized else ""))

    return {
        "area_km2": round(region.area_km2, 6),
        "bbox_km": {"width": round(width_m / 1000, 4), "height": round(height_m / 1000, 4)},
        "pixels": {
            "width": width_px,
            "height": height_px,
            "total": width_px * height_px * variables * products,
        },
        "per_file_bytes": per_file,
        "total_bytes": total,
        "human": human_bytes(total),
        "assumptions": "; ".join(notes) + ".",
        "full_granules_bytes": full_granules_bytes,
    }
