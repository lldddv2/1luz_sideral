"""Model input (multi-polarization dB GeoTIFF) and result (1-band GeoTIFF -> PNG) for the external model bridge.

Preprocessing mirrors app.water.service (scene choice, HTTP read, mask, 30 m average) but reads any of
HH/HV/VV/VH; app.water.service itself is untouched.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from app.water import service

MAX_SIDE_KM = 60.0
POLS = {"HH": "HHHH", "HV": "HVHV", "VV": "VVVV", "VH": "VHVH"}
OUTPUTS = ("probability", "continuous", "classes")
# Categorical palette (Tableau 10 + 2), assigned in ascending class order.
PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948",
    "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac", "#17becf", "#bcbd22",
]
# viridis anchors at 0, .25, .5, .75, 1.
VIRIDIS = np.array([[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]], np.float32)


class UnknownPol(ValueError):
    pass


def check_aoi(bbox) -> None:
    service.check_aoi(bbox)
    w, s, e, n = bbox
    lat = math.radians((s + n) / 2)
    side = max((e - w) * 111.32 * math.cos(lat), (n - s) * 110.57)
    if side > MAX_SIDE_KM:
        raise service.AoiTooLarge(f"AOI side {side:.0f} km exceeds {MAX_SIDE_KM:.0f} km")


def check_pols(pols: list[str] | None) -> list[str]:
    out = [p.upper() for p in (pols or [])] or ["HH"]
    bad = [p for p in out if p not in POLS]
    if bad:
        raise UnknownPol(f"unsupported polarization(s) {bad}; use {list(POLS)}")
    return out


def _key(bbox, on_or_before: date | None, pols: list[str]) -> str:
    raw = json.dumps([[round(v, 5) for v in bbox], on_or_before.isoformat() if on_or_before else None, pols])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _read_pols(url: str, bbox, pols: list[str]) -> tuple[list[np.ndarray], CRS, Affine]:
    """Linear power per polarization on a 30 m grid in the granule projection; NaN = invalid."""
    import h5py

    res = service.RES
    f = service.RemoteFile(url)
    with h5py.File(f, "r") as h:
        g = h[service.GRID]
        missing = [p for p in pols if POLS[p] not in g]
        if missing:
            have = [p for p, d in POLS.items() if d in g]
            raise service.NoScene(f"scene lacks polarization(s) {missing}; available: {have}")
        crs = CRS.from_epsg(int(g["projection"][()]))
        xs, ys = g["xCoordinates"][:], g["yCoordinates"][:]
        left, bottom, right, top = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
        left, bottom = math.floor(left / res) * res, math.floor(bottom / res) * res
        right, top = math.ceil(right / res) * res, math.ceil(top / res) * res
        width, height = int(round((right - left) / res)), int(round((top - bottom) / res))
        dst_t = from_origin(left, top, res, res)
        pad = 300
        ci = np.where((xs >= left - pad) & (xs <= right + pad))[0]
        ri = np.where((ys <= top + pad) & (ys >= bottom - pad))[0]
        if len(ci) < 2 or len(ri) < 2:
            raise service.NoScene("granule does not cover the AOI")
        r0, r1, c0, c1 = int(ri[0]), int(ri[-1]) + 1, int(ci[0]), int(ci[-1]) + 1
        names = [POLS[p] for p in pols] + ["mask"]
        f.prefetch(sum((service._chunk_blocks(g[n], r0, r1, c0, c1, f.BS) for n in names), []))
        raw = [g[POLS[p]][r0:r1, c0:c1].astype(np.float32) for p in pols]
        mk = g["mask"][r0:r1, c0:c1]
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    src_t = Affine(dx, 0, float(xs[c0]) - dx / 2, 0, dy, float(ys[r0]) - dy / 2)
    out = []
    for a in raw:
        ok = (mk >= 1) & (mk <= 254) & np.isfinite(a) & (a > 0)
        power = np.full((height, width), np.nan, np.float32)
        reproject(
            source=np.where(ok, a, np.nan).astype(np.float32), destination=power,
            src_transform=src_t, src_crs=crs, src_nodata=np.nan,
            dst_transform=dst_t, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average,
        )
        out.append(power)
    return out, crs, dst_t


def build_input(bbox, on_or_before: date | None, cache_dir: Path, pols: list[str] | None = None) -> tuple[Path, dict[str, Any]]:
    """Write (or reuse) a float32 dB GeoTIFF, one band per polarization in `pols` order. Blocking."""
    pols = check_pols(pols)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _key(bbox, on_or_before, pols)
    tif, meta_path = cache_dir / f"{key}.tif", cache_dir / f"{key}.json"
    if tif.exists() and meta_path.exists():
        return tif, json.loads(meta_path.read_text())
    granules = service.search(tuple(bbox), on_or_before)
    if not granules:
        raise service.NoScene("no NISAR L2 GCOV scene covers this AOI" + (f" on or before {on_or_before}" if on_or_before else ""))
    best, pol_err = None, None
    # Same rule as /api/water: newest of the first three with >=50% valid coverage, else the best one.
    for g in granules[:3]:
        try:
            bands, crs, transform = _read_pols(g["url"], bbox, pols)
        except service.NoScene as e:
            if "polarization" in str(e):
                pol_err = e
            continue
        valid = float(np.mean([np.isfinite(b).mean() for b in bands]))
        if valid == 0:
            continue
        if best is None or valid > best[0] + 0.05:
            best = (valid, bands, crs, transform, g)
        if best[0] >= 0.5:
            break
    if best is None:
        raise pol_err or service.NoScene(f"no NISAR L2 GCOV scene with valid {'/'.join(pols)} data covers this AOI")
    _, bands, crs, transform, g = best
    tmp = tif.with_suffix(".part")
    h, w = bands[0].shape
    with rasterio.open(
        tmp, "w", driver="GTiff", width=w, height=h, count=len(bands), dtype="float32",
        crs=crs, transform=transform, nodata=float("nan"), compress="deflate",
    ) as dst:
        for i, (p, power) in enumerate(zip(pols, bands), 1):
            db = np.full(power.shape, np.nan, np.float32)
            ok = np.isfinite(power) & (power > 0)
            db[ok] = 10 * np.log10(power[ok])
            dst.write(db, i)
            dst.set_band_description(i, p)
        dst.update_tags(scene_id=g["id"], datetime=g["start"], pols=",".join(pols), units="dB")
    tmp.replace(tif)
    meta = {"scene_id": g["id"], "datetime": g["start"], "pols": pols}
    meta_path.write_text(json.dumps(meta))
    return tif, meta


def _to_3857(arr: np.ndarray, crs, transform, nearest: bool) -> tuple[np.ndarray, list[float]]:
    h, w = arr.shape
    west, south, east, north = service._bounds(h, w, transform)
    b3857 = transform_bounds(crs, "EPSG:3857", west, south, east, north, densify_pts=21)
    scale = max(1.0, max(h, w) / service.MAX_PNG)
    ow, oh = max(1, round(w / scale)), max(1, round(h / scale))
    dst = np.full((oh, ow), np.nan, np.float32)
    reproject(
        source=arr, destination=dst, src_transform=transform, src_crs=crs, src_nodata=np.nan,
        dst_transform=from_bounds(*b3857, ow, oh), dst_crs="EPSG:3857", dst_nodata=np.nan,
        resampling=Resampling.nearest if nearest else Resampling.bilinear,
    )
    return dst, list(transform_bounds("EPSG:3857", "EPSG:4326", *b3857))


def _png(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with rasterio.open(buf, "w", driver="PNG", width=rgba.shape[2], height=rgba.shape[1], count=4, dtype="uint8") as png:
        png.write(rgba)
    return buf.getvalue()


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def render_continuous(arr, crs, transform) -> tuple[bytes, list[float], dict[str, Any]]:
    """viridis over the p2-p98 stretch; NaN transparent."""
    v = arr[np.isfinite(arr)]
    lo, hi = (float(np.percentile(v, 2)), float(np.percentile(v, 98))) if v.size else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1e-6
    dst, bounds = _to_3857(arr, crs, transform, nearest=False)
    t = np.clip((np.nan_to_num(dst, nan=lo) - lo) / (hi - lo), 0, 1) * (len(VIRIDIS) - 1)
    i = np.minimum(t.astype(int), len(VIRIDIS) - 2)
    f = (t - i)[..., None]
    rgb = (VIRIDIS[i] * (1 - f) + VIRIDIS[i + 1] * f).astype(np.uint8)
    a = np.where(np.isfinite(dst), 220, 0).astype(np.uint8)
    rgba = np.concatenate([rgb.transpose(2, 0, 1), a[None]])
    return _png(rgba), bounds, {"min": lo, "max": hi}


def render_classes(arr, crs, transform) -> tuple[bytes, list[float], dict[str, Any]]:
    """Integer classes, categorical palette (<=12 non-zero classes); 0 and NaN transparent."""
    vals = [int(x) for x in np.unique(np.rint(arr[np.isfinite(arr)]).astype(np.int64)) if x != 0]
    if len(vals) > len(PALETTE):
        raise ValueError(f"{len(vals)} classes exceed the {len(PALETTE)}-color palette")
    dst, bounds = _to_3857(arr, crs, transform, nearest=True)
    rgba = np.zeros((4, *dst.shape), np.uint8)
    cls = np.where(np.isfinite(dst), np.rint(np.nan_to_num(dst)), 0).astype(np.int64)
    legend = []
    for k, v in enumerate(vals):
        c = PALETTE[k]
        m = cls == v
        for ch, x in enumerate(_hex(c)):
            rgba[ch][m] = x
        rgba[3][m] = 220
        legend.append({"value": v, "color": c})
    return _png(rgba), bounds, {"classes": legend}


def render_result(input_tif: Path, result: bytes, png_path: Path, output: str = "probability") -> dict[str, Any]:
    """Validate a 1-band GeoTIFF against the input grid, write the PNG, return bounds, stats, legend."""
    with rasterio.open(input_tif) as src:
        shape, crs, transform = (src.height, src.width), src.crs, src.transform
    from rasterio.io import MemoryFile

    with MemoryFile(result) as mem, mem.open() as r:
        if (r.height, r.width) != shape:
            raise ValueError(f"result shape {(r.height, r.width)} != input {shape}")
        if r.crs is not None and CRS.from_user_input(r.crs) != crs:
            raise ValueError(f"result CRS {r.crs} != input {crs}")
        if r.crs is not None and not r.transform.almost_equals(transform):
            raise ValueError("result transform differs from input")
        arr = r.read(1).astype(np.float32)
        if r.nodata is not None and not math.isnan(r.nodata):
            arr[arr == r.nodata] = np.nan
    valid = np.isfinite(arr)
    if output == "probability":
        arr = np.where(valid, np.clip(arr, 0, 1), np.nan).astype(np.float32)
        payload, bounds = service.prob_png(arr, crs, transform)
        legend: dict[str, Any] = {"min": 0.0, "max": 1.0}
    elif output == "continuous":
        payload, bounds, legend = render_continuous(arr, crs, transform)
    elif output == "classes":
        payload, bounds, legend = render_classes(arr, crs, transform)
    else:
        raise ValueError(f"unknown output {output!r}")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(payload)
    v = arr[valid]
    stats: dict[str, Any] = (
        {"min": float(v.min()), "max": float(v.max()), "mean": float(v.mean())} if v.size
        else {"min": None, "max": None, "mean": None}
    )
    if output == "probability":
        stats["fraction"] = float((v >= 0.5).mean()) if v.size else 0.0
    return {"bounds": bounds, "stats": stats, "legend": legend}
