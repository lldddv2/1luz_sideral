#!/usr/bin/env python3
"""Audit retrospective OPERA label windows against one aligned NISAR sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio


ROOT = Path(__file__).resolve().parent
DEFAULT_WINDOWS_DAYS = (7, 14, 30, 45, 60, 90, 120)
CONFIRMED_STATUS_CODES = {3, 6, 7, 8}


def latest_sample_json() -> Path:
    candidates = sorted((ROOT / "data" / "datasets").glob("*/samples/*/sample.json"))
    if not candidates:
        raise FileNotFoundError("No hay muestras en notebooks/pablo/data/datasets")
    return candidates[-1]


def read_band(sample_dir: Path, relative_path: str) -> tuple[np.ndarray, dict[str, Any]]:
    path = sample_dir / relative_path
    with rasterio.open(path) as dataset:
        if dataset.count != 1:
            raise ValueError(f"Se esperaba una banda en {path}")
        return dataset.read(1), {
            "path": str(path),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "transform": list(dataset.transform)[:6],
            "nodata": dataset.nodata,
        }


def audit(sample_json: Path, windows_days: tuple[int, ...]) -> dict[str, Any]:
    sample_json = sample_json.resolve()
    sample_dir = sample_json.parent
    sample = json.loads(sample_json.read_text())
    try:
        sample_ref = sample_json.relative_to(ROOT).as_posix()
    except ValueError:
        sample_ref = str(sample_json)
    label_info = sample["labels"]

    status, status_grid = read_band(sample_dir, label_info["status"])
    event_delta, delta_grid = read_band(
        sample_dir, label_info["event_delta_days_from_nisar"]
    )
    valid_mask, valid_grid = read_band(sample_dir, label_info["valid_sample_mask"])
    grids = (status_grid, delta_grid, valid_grid)
    if status.shape != event_delta.shape or status.shape != valid_mask.shape:
        raise ValueError("Las etiquetas y la máscara no comparten dimensiones")
    if any(
        grid["crs"] != status_grid["crs"]
        or grid["transform"] != status_grid["transform"]
        for grid in grids[1:]
    ):
        raise ValueError("Las etiquetas y la máscara no comparten grilla")

    mask = valid_mask == 1
    status_valid = np.ones(status.shape, dtype=bool)
    if status_grid["nodata"] is not None:
        status_valid &= status != status_grid["nodata"]
    label_valid = mask & status_valid
    positive = label_valid & (status > 0)
    negative = label_valid & (status == 0)
    delta_valid = event_delta != delta_grid["nodata"]
    dated_positive = positive & delta_valid
    confirmed_positive = positive & np.isin(status, tuple(CONFIRMED_STATUS_CODES))

    future_positive = dated_positive & (event_delta > 0)
    same_day_positive = dated_positive & (event_delta == 0)
    past_positive = dated_positive & (event_delta < 0)

    window_rows = []
    for days in windows_days:
        # Daily labels cannot establish within-day ordering; keep only dates before NISAR.
        in_window = dated_positive & (event_delta >= -days) & (event_delta < 0)
        confirmed_in_window = in_window & np.isin(
            status, tuple(CONFIRMED_STATUS_CODES)
        )
        count = int(in_window.sum())
        window_rows.append(
            {
                "lookback_days": days,
                "delta_days_inclusive": [-days, -1],
                "positive_pixels": count,
                "confirmed_positive_pixels": int(confirmed_in_window.sum()),
                "first_detection_or_provisional_pixels": int(
                    count - confirmed_in_window.sum()
                ),
                "retained_percent_of_dated_positive": round(
                    100 * count / int(dated_positive.sum()), 2
                )
                if dated_positive.any()
                else 0.0,
                "negative_pixels_retained": int(negative.sum()),
            }
        )

    return {
        "schema_version": 1,
        "audit": "retrospective_temporal_window_sensitivity",
        "sample_id": sample["sample_id"],
        "sample_metadata": sample_ref,
        "source_products": sample["source_products"],
        "grid": {
            "crs": status_grid["crs"],
            "shape_yx": list(status.shape),
            "pixel_size_m": sample["grid"]["pixel_size_m"],
        },
        "population": {
            "valid_feature_and_status_pixels": int(label_valid.sum()),
            "positive_status_pixels": int(positive.sum()),
            "dated_positive_pixels": int(dated_positive.sum()),
            "confirmed_positive_pixels": int(confirmed_positive.sum()),
            "negative_status_pixels": int(negative.sum()),
            "positive_without_event_date_pixels": int((positive & ~delta_valid).sum()),
            "positive_event_after_nisar_pixels_excluded": int(future_positive.sum()),
            "same_calendar_day_positive_pixels_excluded_as_order_ambiguous": int(
                same_day_positive.sum()
            ),
            "past_positive_pixels": int(past_positive.sum()),
        },
        "window_rule": (
            "Keep positive OPERA labels with event_delta_days_from_nisar in [-N,-1]. "
            "Positive values are future detections and excluded. Zero-day labels are "
            "excluded because daily precision cannot establish acquisition order. "
            "Status 0 negatives are retained independently of window."
        ),
        "confirmed_status_codes": sorted(CONFIRMED_STATUS_CODES),
        "windows": window_rows,
        "limitations": [
            "One positive hotspot AOI and one NISAR–OPERA pair; window counts are sensitivity results, not a selected threshold.",
            "Only a few status-0 pixels occur in this positive hotspot; negative sampling needs separate background AOIs.",
            "VEG-DIST-DATE is first anomaly detection at daily precision, not event onset or causal attribution.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-json", type=Path, default=None, help="sample.json; default: newest sample"
    )
    parser.add_argument(
        "--window-days",
        type=int,
        nargs="+",
        default=list(DEFAULT_WINDOWS_DAYS),
        help="Lookback windows to compare; defaults to 7 14 30 45 60 90 120",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="Report path; default: catalog run directory"
    )
    args = parser.parse_args()
    if any(days <= 0 for days in args.window_days):
        parser.error("Todas las ventanas deben ser mayores que cero")

    sample_json = args.sample_json or latest_sample_json()
    report = audit(sample_json, tuple(sorted(set(args.window_days))))
    output = args.output
    if output is None:
        run_id = report["source_products"]["catalog_run_id"]
        output = ROOT / "catalog" / run_id / "temporal_filter_audit.json"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"report": str(output), "population": report["population"], "windows": report["windows"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
