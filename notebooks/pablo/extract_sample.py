#!/usr/bin/env python3
"""Download one bounded OPERA layer, crop it, and inspect sample raster grids."""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import tempfile
from pathlib import Path

# Force IPv4 before requests/earthaccess initialize their connection pools.
import urllib3.util.connection

urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

import earthaccess
import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds


ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data/samples/central_valley_20261026"
RUN = ROOT / "catalog/20261114T231448Z"
BBOX_WGS84 = (-119.555, 36.075, -119.545, 36.085)
MAX_SOURCE_BYTES = 8 * 1024 * 1024
OPERA_URL = (
    "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/"
    "OPERA_L3_DIST-ALERT-HLS_V1/"
    "OPERA_L3_DIST-ALERT-HLS_T11SKA_20261027T184451Z_20261031T115149Z_S2C_30_v1/"
    "OPERA_L3_DIST-ALERT-HLS_T11SKA_20261027T184451Z_20261031T115149Z_S2C_30_v1_VEG-DIST-STATUS.tif"
)
NISAR_TIF = next((SAMPLE / "nisar").glob("*_subsetted.tif"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_opera(path: Path) -> dict:
    earthaccess.login(strategy="netrc")
    session = earthaccess.get_requests_https_session()
    response = session.get(OPERA_URL, stream=True, timeout=(30, 60))
    response.raise_for_status()
    length_header = response.headers.get("Content-Length")
    expected_bytes = int(length_header) if length_header else None
    if expected_bytes is not None and expected_bytes > MAX_SOURCE_BYTES:
        raise RuntimeError(f"OPERA TIFF exceeds {MAX_SOURCE_BYTES} byte cap")

    received = 0
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as stream:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > MAX_SOURCE_BYTES:
                    raise RuntimeError(f"OPERA TIFF exceeds {MAX_SOURCE_BYTES} byte cap")
                stream.write(chunk)
        if expected_bytes is not None and received != expected_bytes:
            raise RuntimeError(f"incomplete download: expected {expected_bytes}, got {received}")
        os.replace(temporary_name, path)
    finally:
        response.close()
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return {"bytes": received, "sha256": sha256(path), "url": OPERA_URL}


def crop_opera(source_path: Path, crop_path: Path) -> dict:
    with rasterio.open(source_path) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *BBOX_WGS84, densify_pts=21)
        float_window = from_bounds(*bounds, transform=src.transform)
        col0 = max(0, math.floor(float_window.col_off))
        row0 = max(0, math.floor(float_window.row_off))
        col1 = min(src.width, math.ceil(float_window.col_off + float_window.width))
        row1 = min(src.height, math.ceil(float_window.row_off + float_window.height))
        if col0 >= col1 or row0 >= row1:
            raise RuntimeError("AOI does not overlap OPERA raster")
        window = rasterio.windows.Window(col0, row0, col1 - col0, row1 - row0)
        data = src.read(window=window)
        profile = src.profile.copy()
        profile.update(
            width=window.width,
            height=window.height,
            transform=src.window_transform(window),
        )
        with rasterio.open(crop_path, "w", **profile) as dst:
            dst.write(data)
            dst.update_tags(**src.tags())
            for index in range(1, src.count + 1):
                dst.update_tags(index, **src.tags(index))
        return inspect_raster(crop_path)


def inspect_raster(path: Path) -> dict:
    with rasterio.open(path) as src:
        info = {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "dtype": list(src.dtypes),
            "crs": src.crs.to_string() if src.crs else None,
            "transform": list(src.transform)[:6],
            "bounds": list(src.bounds),
            "pixel_size": [src.transform.a, src.transform.e],
            "nodata": src.nodata,
            "tags": src.tags(),
            "band_tags": [src.tags(i) for i in range(1, src.count + 1)],
        }
        values = src.read(1, masked=True)
        valid = values.compressed()
        if valid.size:
            info["valid_pixel_count"] = int(valid.size)
            if np.issubdtype(valid.dtype, np.integer):
                classes, counts = np.unique(valid, return_counts=True)
                info["value_counts"] = {
                    str(int(value)): int(count)
                    for value, count in zip(classes, counts, strict=True)
                }
            else:
                info["value_summary"] = {
                    "min": float(np.min(valid)),
                    "p02": float(np.percentile(valid, 2)),
                    "median": float(np.median(valid)),
                    "p98": float(np.percentile(valid, 98)),
                    "max": float(np.max(valid)),
                }
        else:
            info["valid_pixel_count"] = 0
        return info


def load_temporal_pair() -> dict:
    audit = json.loads((RUN / "pair_audit.json").read_text(encoding="utf-8"))
    pair_ids = audit["pair"]
    for line in (RUN / "pairs.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (
            row["nisar_granule_id"] == pair_ids["nisar_granule_id"]
            and row["opera_granule_id"] == pair_ids["opera_granule_id"]
        ):
            return {
                "nisar_time_utc": row["nisar_time_utc"],
                "opera_time_utc": row["opera_time_utc"],
                "signed_delta_seconds_opera_minus_nisar": row[
                    "signed_delta_seconds_opera_minus_nisar"
                ],
                "signed_delta_hours_opera_minus_nisar": row[
                    "signed_delta_hours_opera_minus_nisar"
                ],
                "absolute_delta_seconds": row["absolute_delta_seconds"],
                "absolute_delta_days": row["absolute_delta_days"],
                "temporal_match": row["temporal_match"],
                "time_basis": "CMR granule start timestamps; not event onset time",
            }
    raise RuntimeError("sample granules have no matching temporal pair record")


def main() -> None:
    opera_dir = SAMPLE / "opera"
    opera_dir.mkdir(parents=True, exist_ok=True)
    source_path = opera_dir / "source_VEG-DIST-STATUS.tif"
    crop_path = opera_dir / "VEG-DIST-STATUS_aoi.tif"
    download_info = download_opera(source_path) if not source_path.exists() else {
        "bytes": source_path.stat().st_size,
        "sha256": sha256(source_path),
        "reused_existing": True,
    }
    if download_info["bytes"] > MAX_SOURCE_BYTES:
        raise RuntimeError(f"OPERA TIFF exceeds {MAX_SOURCE_BYTES} byte cap")
    with rasterio.open(source_path) as src:
        if src.width * src.height > 200_000_000:
            raise RuntimeError("unexpectedly large OPERA raster dimensions")
    opera_crop_info = crop_opera(source_path, crop_path)
    nisar_info = inspect_raster(NISAR_TIF)
    same_crs = opera_crop_info["crs"] == nisar_info["crs"]
    opera_transform = opera_crop_info["transform"]
    nisar_transform = nisar_info["transform"]
    origin_offset = [
        opera_transform[2] - nisar_transform[2],
        opera_transform[5] - nisar_transform[5],
    ]
    same_pixel_size = opera_crop_info["pixel_size"] == nisar_info["pixel_size"]
    if same_crs:
        fine_x = min(abs(opera_transform[0]), abs(nisar_transform[0]))
        fine_y = min(abs(opera_transform[4]), abs(nisar_transform[4]))
        origin_offset_in_nisar_pixels = [
            origin_offset[0] / fine_x,
            origin_offset[1] / fine_y,
        ]
    else:
        origin_offset_in_nisar_pixels = None
    same_pixel_grid = bool(
        same_crs
        and same_pixel_size
        and all(abs(value) < 1e-9 for value in origin_offset_in_nisar_pixels)
    )
    pixel_ratios = [
        max(abs(opera_transform[0]), abs(nisar_transform[0]))
        / min(abs(opera_transform[0]), abs(nisar_transform[0])),
        max(abs(opera_transform[4]), abs(nisar_transform[4]))
        / min(abs(opera_transform[4]), abs(nisar_transform[4])),
    ]
    nested_grid_alignment = bool(
        same_crs
        and all(abs(ratio - round(ratio)) < 1e-9 for ratio in pixel_ratios)
        and all(abs(value - round(value)) < 1e-9 for value in origin_offset_in_nisar_pixels)
    )
    report = {
        "aoi_bbox_wgs84": BBOX_WGS84,
        "temporal_pair": load_temporal_pair(),
        "opera_download": download_info,
        "opera_source": inspect_raster(source_path),
        "opera_crop": opera_crop_info,
        "nisar_crop": nisar_info,
        "same_crs": same_crs,
        "same_pixel_size": same_pixel_size,
        "origin_offset_opera_minus_nisar_m": origin_offset,
        "origin_offset_in_fine_grid_pixels": origin_offset_in_nisar_pixels,
        "pixel_size_ratios_coarse_to_fine": pixel_ratios,
        "same_pixel_grid": same_pixel_grid,
        "nested_grid_alignment": nested_grid_alignment,
        "alignment_note": "Inspection only; no reprojection or resampling performed.",
    }
    report_path = RUN / "sample_alignment.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "opera_source_bytes": download_info["bytes"],
        "opera_crop_shape": [opera_crop_info["height"], opera_crop_info["width"]],
        "opera_crop_classes": opera_crop_info.get("value_counts", {}),
        "nisar_crop_shape": [nisar_info["height"], nisar_info["width"]],
        "crs": nisar_info["crs"],
        "opera_pixel_size_m": opera_crop_info["pixel_size"],
        "nisar_pixel_size_m": nisar_info["pixel_size"],
        "temporal_shift_seconds_opera_minus_nisar": report["temporal_pair"][
            "signed_delta_seconds_opera_minus_nisar"
        ],
        "origin_offset_opera_minus_nisar_m": origin_offset,
        "nested_grid_alignment": nested_grid_alignment,
        "report": str(report_path),
    }, indent=2))


if __name__ == "__main__":
    main()
