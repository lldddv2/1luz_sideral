"""Find the latest NISAR L2 GCOV over an AOI, read an HHHH + mask subset over HTTP, run the U-Net.

Earthdata auth comes from ~/.netrc (or NETRC, set from settings in app.main) via requests.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from app.water import model as unet

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
SHORT_NAMES = ("NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_BETA_V1")
GRID = "science/LSAR/GCOV/grids/frequencyA"
RES = 30.0
MAX_SIDE_KM = 250.0
MAX_PNG = 1024


class NoScene(Exception):
    pass


class AoiTooLarge(Exception):
    pass


class RemoteFile(io.RawIOBase):
    """Seekable file over HTTP range requests, cached in 4 MB blocks (for h5py)."""

    BS = 4 * 1024 * 1024

    def __init__(self, url: str):
        self.session = requests.Session()
        r = self.session.get(url, headers={"Range": "bytes=0-0"}, allow_redirects=True, stream=True, timeout=60)
        r.raise_for_status()
        self.url = r.url  # signed URL after the Earthdata redirect
        self.size = int(r.headers["Content-Range"].split("/")[1])
        r.close()
        self.pos = 0
        self.cache: dict[int, bytes] = {}
        self.bytes = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def _get(self, session: requests.Session, i: int) -> bytes:
        a = i * self.BS
        b = min(self.size, a + self.BS) - 1
        r = session.get(self.url, headers={"Range": f"bytes={a}-{b}"}, timeout=120)
        r.raise_for_status()
        return r.content

    def _block(self, i: int) -> bytes:
        if i not in self.cache:
            self.cache[i] = self._get(self.session, i)
            self.bytes += len(self.cache[i])
        return self.cache[i]

    def prefetch(self, blocks: list[int], workers: int = 8) -> None:
        local = threading.local()

        def fetch(i: int):
            if not hasattr(local, "s"):
                local.s = requests.Session()
            return i, self._get(local.s, i)

        with ThreadPoolExecutor(workers) as ex:
            for i, content in ex.map(fetch, [i for i in blocks if i not in self.cache]):
                self.cache[i] = content
                self.bytes += len(content)

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        out = bytearray()
        p = self.pos
        while len(out) < n:
            i, o = divmod(p, self.BS)
            d = self._block(i)[o : o + n - len(out)]
            out += d
            p += len(d)
        buf[:n] = out
        self.pos += n
        return n


def _chunk_blocks(ds, r0: int, r1: int, c0: int, c1: int, bs: int) -> list[int]:
    cs = ds.chunks
    out: set[int] = set()
    if cs is None:
        return []
    for i in range(r0 // cs[0] * cs[0], r1, cs[0]):
        for j in range(c0 // cs[1] * cs[1], c1, cs[1]):
            info = ds.id.get_chunk_info_by_coord((i, j))
            if info.byte_offset is None:
                continue
            out.update(range(info.byte_offset // bs, (info.byte_offset + info.size - 1) // bs + 1))
    return sorted(out)


def search(bbox: tuple[float, float, float, float], on_or_before: date | None) -> list[dict[str, Any]]:
    end = (on_or_before or date.today()) + timedelta(days=1)
    found: list[dict[str, Any]] = []
    for sn in SHORT_NAMES:
        r = requests.get(
            CMR,
            params={
                "short_name": sn,
                "bounding_box": ",".join(f"{v:.6f}" for v in bbox),
                "temporal": f"2024-01-01T00:00:00Z,{end.isoformat()}T00:00:00Z",
                "page_size": 50,
                "sort_key": "-start_date",
            },
            timeout=60,
        )
        r.raise_for_status()
        for g in r.json().get("feed", {}).get("entry", []):
            url = next(
                (
                    link["href"]
                    for link in g.get("links", [])
                    if link.get("href", "").endswith(".h5") and link["href"].startswith("https://")
                    and "s3credentials" not in link["href"]
                ),
                None,
            )
            if url:
                found.append({"id": g["title"], "start": g["time_start"], "url": url})
    found.sort(key=lambda g: g["start"], reverse=True)
    return found


def _read_power(url: str, bbox) -> tuple[np.ndarray, CRS, Affine, float]:
    """HHHH linear power averaged onto a 30 m grid in the granule's projection; NaN = invalid."""
    import h5py

    f = RemoteFile(url)
    with h5py.File(f, "r") as h:
        g = h[GRID]
        crs = CRS.from_epsg(int(g["projection"][()]))
        xs = g["xCoordinates"][:]
        ys = g["yCoordinates"][:]
        left, bottom, right, top = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
        left, bottom = math.floor(left / RES) * RES, math.floor(bottom / RES) * RES
        right, top = math.ceil(right / RES) * RES, math.ceil(top / RES) * RES
        width, height = int(round((right - left) / RES)), int(round((top - bottom) / RES))
        dst_t = from_origin(left, top, RES, RES)
        pad = 300
        ci = np.where((xs >= left - pad) & (xs <= right + pad))[0]
        ri = np.where((ys <= top + pad) & (ys >= bottom - pad))[0]
        if len(ci) < 2 or len(ri) < 2:
            raise NoScene("granule does not cover the AOI")
        r0, r1, c0, c1 = int(ri[0]), int(ri[-1]) + 1, int(ci[0]), int(ci[-1]) + 1
        f.prefetch(_chunk_blocks(g["HHHH"], r0, r1, c0, c1, f.BS) + _chunk_blocks(g["mask"], r0, r1, c0, c1, f.BS))
        hh = g["HHHH"][r0:r1, c0:c1].astype(np.float32)
        mk = g["mask"][r0:r1, c0:c1]
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    src_t = Affine(dx, 0, float(xs[c0]) - dx / 2, 0, dy, float(ys[r0]) - dy / 2)
    ok = (mk >= 1) & (mk <= 254) & np.isfinite(hh) & (hh > 0)
    power = np.full((height, width), np.nan, np.float32)
    reproject(
        source=np.where(ok, hh, np.nan).astype(np.float32), destination=power,
        src_transform=src_t, src_crs=crs, src_nodata=np.nan,
        dst_transform=dst_t, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average,
    )
    return power, crs, dst_t, f.bytes / 1e6


def prob_png(prob: np.ndarray, crs: CRS, transform: Affine) -> tuple[bytes, list[float]]:
    """Blue gradient by water probability in EPSG:3857; transparent at 0 and nodata."""
    h, w = prob.shape
    west, south, east, north = _bounds(h, w, transform)
    b3857 = transform_bounds(crs, "EPSG:3857", west, south, east, north, densify_pts=21)
    scale = max(1.0, max(h, w) / MAX_PNG)
    ow, oh = max(1, round(w / scale)), max(1, round(h / scale))
    dst = np.full((oh, ow), np.nan, np.float32)
    reproject(
        source=prob, destination=dst, src_transform=transform, src_crs=crs, src_nodata=np.nan,
        dst_transform=from_bounds(*b3857, ow, oh), dst_crs="EPSG:3857", dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    p = np.clip(np.nan_to_num(dst, nan=0.0), 0, 1)
    # Light cyan at low probability to deep blue at 1; alpha grows with probability.
    r = (180 * (1 - p) + 10 * p).astype(np.uint8)
    g = (230 * (1 - p) + 60 * p).astype(np.uint8)
    b = (255 * (1 - p) + 200 * p).astype(np.uint8)
    a = np.where(np.isfinite(dst) & (p > 0.05), 60 + 195 * p, 0).astype(np.uint8)
    buf = io.BytesIO()
    with rasterio.open(buf, "w", driver="PNG", width=ow, height=oh, count=4, dtype="uint8") as png:
        png.write(np.stack([r, g, b, a]))
    return buf.getvalue(), list(transform_bounds("EPSG:3857", "EPSG:4326", *b3857))


def _bounds(h: int, w: int, t: Affine) -> tuple[float, float, float, float]:
    west, north = t * (0, 0)
    east, south = t * (w, h)
    return west, south, east, north


def check_aoi(bbox) -> None:
    w, s, e, n = bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("bbox must be west,south,east,north in degrees with west<east, south<north")
    lat = math.radians((s + n) / 2)
    width_km = (e - w) * 111.32 * math.cos(lat)
    height_km = (n - s) * 110.57
    if max(width_km, height_km) > MAX_SIDE_KM:
        raise AoiTooLarge(f"AOI side {max(width_km, height_km):.0f} km exceeds {MAX_SIDE_KM:.0f} km")


def run(bbox, on_or_before: date | None, cache_dir: Path) -> dict[str, Any]:
    check_aoi(bbox)
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    granules = search(bbox, on_or_before)
    timings["search_s"] = time.perf_counter() - t0
    if not granules:
        raise NoScene("no NISAR L2 GCOV scene covers this AOI" + (f" on or before {on_or_before}" if on_or_before else ""))
    _, meta = unet.load()
    best: dict[str, Any] | None = None
    # Frames are cut along track, so the newest one may clip the AOI; keep the best of a few.
    for granule in granules[:3]:
        info = _cached(cache_dir, bbox, granule)
        if info is None:
            try:
                info = _compute(cache_dir, bbox, granule, meta, timings)
            except NoScene:
                continue
        if info is None:
            continue
        if best is None or info["valid_fraction"] > best["valid_fraction"] + 0.05:
            best = info
        if best["valid_fraction"] >= 0.5:
            break
    if best is None:
        raise NoScene("no NISAR L2 GCOV scene with valid HH data covers this AOI")
    best = dict(best)
    best["timings"] = {**best.get("timings", {}), "request_total_s": round(time.perf_counter() - t0, 2)}
    return best


def _key(bbox, granule) -> str:
    return hashlib.sha1(json.dumps([[round(v, 5) for v in bbox], granule["id"]]).encode()).hexdigest()[:16]


def _cached(cache_dir: Path, bbox, granule) -> dict[str, Any] | None:
    key = _key(bbox, granule)
    info_path, png_path = cache_dir / f"{key}.json", cache_dir / f"{key}.png"
    if info_path.exists() and png_path.exists():
        info = json.loads(info_path.read_text())
        info["cached"] = True
        return info
    return None


def _compute(cache_dir: Path, bbox, granule, meta, timings) -> dict[str, Any] | None:
    key = _key(bbox, granule)
    timings = dict(timings)
    t = time.perf_counter()
    power, crs, transform, mb = _read_power(granule["url"], bbox)
    timings["read_s"] = time.perf_counter() - t
    if not np.isfinite(power).any():
        return None
    t = time.perf_counter()
    prob, valid = unet.predict(power)
    timings["inference_s"] = time.perf_counter() - t
    cls = unet.classify(prob, meta["threshold"])
    payload, bounds = prob_png(prob, crs, transform)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.png").write_bytes(payload)
    info = {
        "id": key,
        "scene_id": granule["id"],
        "datetime": granule["start"],
        "bounds": bounds,
        "threshold": meta["threshold"],
        "water_fraction": float((cls[valid] == 1).mean()) if valid.any() else 0.0,
        "valid_fraction": float(valid.mean()),
        "shape": list(prob.shape),
        "crs": crs.to_string(),
        "read_mb": round(mb, 1),
        "polarization": "HH",
        "cached": False,
        "timings": {k: round(v, 2) for k, v in timings.items()},
    }
    (cache_dir / f"{key}.json").write_text(json.dumps(info))
    return info
