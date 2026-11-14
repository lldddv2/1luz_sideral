"""Benchmark 3: processing real extracted GeoTIFFs (stack, change detection, COG, tiles).

Also extrapolates to a full-year stack (N dates) by replicating the real rasters,
to estimate memory/time for the app's worst case.
"""

from __future__ import annotations

import glob
import os
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import rasterio
from rasterio.warp import transform_bounds

from common import OUT, save, timer

PROC = psutil.Process()


def rss_mb() -> float:
    return round(PROC.memory_info().rss / 2**20, 1)


def find_tiffs(pattern: str) -> list[str]:
    return sorted(p for p in glob.glob(str(OUT / pattern), recursive=True) if not p.endswith("_masked.tif"))


def to_db(a: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(np.where(a > 0, a, np.nan))


def main() -> None:
    r: dict = {"python": sys.version.split()[0]}
    hh = find_tiffs("extract_series_10km/*HHHH*.tif")
    hv = find_tiffs("extract_series_10km/*HVHV*.tif")
    if not hh:
        hh = find_tiffs("extract_area_*km/*HHHH*.tif")
    r["n_hh"], r["n_hv"] = len(hh), len(hv)
    if not hh:
        raise SystemExit("no extracted TIFFs found; run bench_extract.py first")

    with rasterio.open(hh[0]) as src:
        r["src_shape"] = [src.height, src.width]
        r["src_dtype"] = src.dtypes[0]
        r["src_crs"] = str(src.crs)
        r["src_res"] = [abs(src.res[0]), abs(src.res[1])]
        r["src_compress"] = str(src.compression)
        r["src_tiled"] = src.profile.get("tiled")
        r["src_bytes"] = os.path.getsize(hh[0])
        profile = src.profile

    # 1) Load stack
    r["rss_before_mb"] = rss_mb()
    with timer(r, "load_stack_s"):
        arrays = []
        for p in hh:
            with rasterio.open(p) as s:
                arrays.append(s.read(1, out_shape=(r["src_shape"][0], r["src_shape"][1])))
        stack = np.stack(arrays).astype("float32")
    r["stack_shape"] = list(stack.shape)
    r["stack_mb"] = round(stack.nbytes / 2**20, 2)

    # 2) Change detection: dB, log-ratio last vs first, per-date stats, temporal std
    with timer(r, "change_detect_s"):
        db = to_db(stack)
        log_ratio = db[-1] - db[0]
        changed = np.abs(log_ratio) > 3.0
        per_date_mean = np.nanmean(db, axis=(1, 2))
        temporal_std = np.nanstd(db, axis=0)
    r["changed_pct"] = round(float(np.nanmean(changed)) * 100, 2)
    r["per_date_mean_db"] = [round(float(x), 2) for x in per_date_mean]
    r["temporal_std_db_median"] = round(float(np.nanmedian(temporal_std)), 2)
    if hv and len(hv) == len(hh):
        with timer(r, "polarization_ratio_s"):
            hv_stack = np.stack([rasterio.open(p).read(1) for p in hv]).astype("float32")
            ratio = to_db(hv_stack) - db  # HV/HH in dB, sensitive to vegetation volume
        r["hv_hh_ratio_median_db"] = round(float(np.nanmedian(ratio)), 2)
    r["rss_after_mb"] = rss_mb()

    # 3) Write change map as COG
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles

    tmp = OUT / "process"
    tmp.mkdir(exist_ok=True)
    plain = tmp / "log_ratio.tif"
    prof = profile.copy()
    prof.update(dtype="float32", count=1, nodata=np.nan, driver="GTiff")
    with rasterio.open(plain, "w", **prof) as dst:
        dst.write(log_ratio.astype("float32"), 1)
    cog = tmp / "log_ratio_cog.tif"
    with timer(r, "cog_translate_s"):
        cog_translate(str(plain), str(cog), cog_profiles.get("deflate"), quiet=True)
    r["cog_bytes"] = os.path.getsize(cog)

    # 4) Tile rendering like TiTiler (rio-tiler), cold vs warm
    try:
        from rio_tiler.io import Reader

        with Reader(str(cog)) as rdr:
            minzoom, maxzoom = rdr.minzoom, rdr.maxzoom
            b = transform_bounds(rdr.crs, "EPSG:4326", *rdr.bounds)
            lon, lat = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            import morecantile

            tms = morecantile.tms.get("WebMercatorQuad")
            times = []
            for z in range(max(minzoom, 8), maxzoom + 1):
                t = tms.tile(lon, lat, z)
                t0 = time.perf_counter()
                img = rdr.tile(t.x, t.y, t.z, tilesize=256)
                img.rescale(in_range=((-6, 6),))
                img.render(img_format="PNG")
                times.append({"z": z, "ms": round((time.perf_counter() - t0) * 1000, 1)})
            r["tile_render_ms"] = times
            r["zoom_range"] = [minzoom, maxzoom]
    except Exception as e:  # noqa: BLE001
        r["tile_error"] = f"{type(e).__name__}: {e}"

    # 5) Extrapolate: full year (32 dates/track) x 2 pols at this AOI, and 4x area
    for n_dates, area_mult in ((32, 1), (32, 4), (64, 4)):
        h, w = r["src_shape"]
        side = int(np.sqrt(area_mult))
        big = np.tile(stack[:1], (1, side, side))  # one date, scaled area
        t0 = time.perf_counter()
        before = rss_mb()
        synth = np.repeat(big, n_dates, axis=0)
        sdb = to_db(synth)
        _ = sdb[-1] - sdb[0]
        _ = np.nanstd(sdb, axis=0)
        key = f"synthetic_{n_dates}dates_x{area_mult}area"
        r[key] = {
            "shape": list(synth.shape),
            "array_mb": round(synth.nbytes / 2**20, 1),
            "compute_s": round(time.perf_counter() - t0, 3),
            "rss_delta_mb": round(rss_mb() - before, 1),
        }
        del synth, sdb, big

    print(r)
    save("bench_process.json", r)


if __name__ == "__main__":
    main()
