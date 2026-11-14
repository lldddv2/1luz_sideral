"""Shared helpers for NISAR performance benchmarks (uses jose's extractor read-only)."""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANTIAGO = HERE.parent
JOSE = SANTIAGO.parent / "jose"
sys.path.insert(0, str(JOSE))

OUT = SANTIAGO / "bench_output"
OUT.mkdir(exist_ok=True)

# Area of interest centred on jose's PoC point (Boulder/Denver, CO) at growing sizes.
CENTER = (-105.0, 40.0)


def square_bbox(side_km: float, center=CENTER) -> list[float]:
    """Approximate square bbox of side_km around center (lon, lat)."""
    import math

    lon, lat = center
    dlat = (side_km / 2) / 111.32
    dlon = (side_km / 2) / (111.32 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


@contextmanager
def timer(results: dict, key: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        results[key] = round(time.perf_counter() - t0, 3)


def save(name: str, data) -> Path:
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return path
