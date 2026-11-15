#!/usr/bin/env python3
"""Find small positive OPERA disturbance windows inside a NISAR footprint."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from shapely import transform as transform_geometry
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from shapely.geometry import Polygon, mapping


ROOT = Path(__file__).resolve().parent
RUN = ROOT / "catalog/20261114T231448Z"
OPERA_TIF = ROOT / "data/samples/central_valley_20261026/opera/source_VEG-DIST-STATUS.tif"
AOI_HEIGHT = 39
AOI_WIDTH = 32
WINDOW_STRIDE = 8
MAX_CANDIDATES = 5


def summed_area(mask: np.ndarray) -> np.ndarray:
    cumulative = np.cumsum(mask, axis=0, dtype=np.int32)
    cumulative = np.cumsum(cumulative, axis=1, dtype=np.int32)
    return np.pad(cumulative, ((1, 0), (1, 0)), mode="constant")


def window_counts(integral: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    return (
        integral[np.ix_(rows + AOI_HEIGHT, cols + AOI_WIDTH)]
        - integral[np.ix_(rows, cols + AOI_WIDTH)]
        - integral[np.ix_(rows + AOI_HEIGHT, cols)]
        + integral[np.ix_(rows, cols)]
    )


def main() -> None:
    audit = json.loads((RUN / "pair_audit.json").read_text(encoding="utf-8"))
    footprint_lon_lat = audit["footprint_check"]["nisar_polygon_lon_lat"]
    with rasterio.open(OPERA_TIF) as src:
        footprint_wgs84 = Polygon(footprint_lon_lat)
        project = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform
        footprint = transform_geometry(footprint_wgs84, project, interleaved=False)
        inside = geometry_mask(
            [mapping(footprint)],
            out_shape=(src.height, src.width),
            transform=src.transform,
            invert=True,
            all_touched=False,
        )
        data = src.read(1)
        nodata = src.nodata
        valid = np.ones(data.shape, dtype=bool) if nodata is None else data != nodata
        valid &= inside
        positive = valid & (data > 0) & (data <= 8)
        active = valid & (data >= 1) & (data <= 6)
        confirmed_active = valid & np.isin(data, [3, 6])

        row_positions = np.arange(0, src.height - AOI_HEIGHT + 1, WINDOW_STRIDE)
        col_positions = np.arange(0, src.width - AOI_WIDTH + 1, WINDOW_STRIDE)
        inside_counts = window_counts(summed_area(inside), row_positions, col_positions)
        valid_counts = window_counts(summed_area(valid), row_positions, col_positions)
        positive_counts = window_counts(summed_area(positive), row_positions, col_positions)
        active_counts = window_counts(summed_area(active), row_positions, col_positions)
        confirmed_counts = window_counts(summed_area(confirmed_active), row_positions, col_positions)

        full_window = AOI_HEIGHT * AOI_WIDTH
        eligible = (
            (inside_counts >= full_window * 0.99)
            & (valid_counts >= full_window * 0.95)
            & (positive_counts > 0)
        )
        if not np.any(eligible):
            eligible = (
                (inside_counts >= full_window * 0.90)
                & (valid_counts >= full_window * 0.80)
                & (positive_counts > 0)
            )
        if not np.any(eligible):
            result = {
                "status": "no_positive_window_inside_nisar_footprint",
                "aoi_pixels": [AOI_HEIGHT, AOI_WIDTH],
                "footprint_positive_pixel_count": int(positive.sum()),
            }
            (RUN / "candidate_positive_aois.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(result, indent=2))
            return

        candidates = []
        for index in np.flatnonzero(eligible):
            row_index, col_index = np.unravel_index(index, eligible.shape)
            row = int(row_positions[row_index])
            col = int(col_positions[col_index])
            candidates.append((
                int(active_counts[row_index, col_index]),
                int(confirmed_counts[row_index, col_index]),
                int(positive_counts[row_index, col_index]),
                row,
                col,
                int(inside_counts[row_index, col_index]),
                int(valid_counts[row_index, col_index]),
            ))
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

        selected = []
        for active_count, confirmed_count, positive_count, row, col, inside_count, valid_count in candidates:
            overlaps = any(
                row < prior["row"] + AOI_HEIGHT
                and row + AOI_HEIGHT > prior["row"]
                and col < prior["col"] + AOI_WIDTH
                and col + AOI_WIDTH > prior["col"]
                for prior in selected
            )
            if overlaps:
                continue
            window = Window(col, row, AOI_WIDTH, AOI_HEIGHT)
            block = data[row:row + AOI_HEIGHT, col:col + AOI_WIDTH]
            classes, counts = np.unique(block[inside[row:row + AOI_HEIGHT, col:col + AOI_WIDTH]], return_counts=True)
            bounds = src.window_bounds(window)
            bbox_wsen = transform_bounds(src.crs, "EPSG:4326", *bounds, densify_pts=21)
            selected.append({
                "row": row,
                "col": col,
                "bbox_wsen": [round(value, 7) for value in bbox_wsen],
                "utm_bounds_m": [round(value, 2) for value in bounds],
                "footprint_coverage_percent": round(inside_count / full_window * 100, 2),
                "valid_data_percent": round(valid_count / full_window * 100, 2),
                "positive_pixels": positive_count,
                "active_pixels_classes_1_to_6": active_count,
                "confirmed_active_pixels_classes_3_and_6": confirmed_count,
                "status_counts": {str(int(value)): int(count) for value, count in zip(classes, counts, strict=True)},
            })
            if len(selected) == MAX_CANDIDATES:
                break

        tags = src.tags()
        report = {
            "status": "positive_windows_found",
            "nisar_granule_id": audit["pair"]["nisar_granule_id"],
            "opera_granule_id": audit["pair"]["opera_granule_id"],
            "aoi_size_pixels": [AOI_HEIGHT, AOI_WIDTH],
            "aoi_stride_pixels": WINDOW_STRIDE,
            "nisar_footprint_positive_pixels_in_opera_tile": int(positive.sum()),
            "opera_layer": "VEG-DIST-STATUS",
            "opera_update_date": tags.get("Update_Date"),
            "opera_input_dist_alert_granule": tags.get("Input_DIST-ALERT_granule"),
            "class_meanings": tags.get("flag_meanings"),
            "time_caveat": "OPERA granule time identifies HLS scene; VEG-DIST-DATE carries first anomaly date. Input_DIST-ALERT_granule is provenance, not event onset.",
            "candidates": selected,
        }
    output = RUN / "candidate_positive_aois.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"report: {output}")


if __name__ == "__main__":
    main()
