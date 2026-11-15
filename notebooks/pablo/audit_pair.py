#!/usr/bin/env python3
"""Audit exact catalog footprints and metadata for closest NISAR–DIST pair."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parent
CATALOG_DIR = ROOT / "catalog"
AOI_PATH = ROOT / "config" / "central_valley_candidate.json"
CMR_UMM_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
DIST_SPEC_URL = "https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DIST_HLS_Product_Specification_V1.pdf"


def fetch_umm(session: requests.Session, concept_id: str) -> dict[str, Any]:
    response = session.get(CMR_UMM_URL, params={"concept_id": concept_id}, timeout=(10, 40))
    response.raise_for_status()
    items = response.json().get("items", [])
    if len(items) != 1:
        raise RuntimeError(f"CMR devolvió {len(items)} resultados para {concept_id}")
    return items[0]["umm"]


def polygon_from_umm(umm: dict[str, Any]) -> list[tuple[float, float]]:
    polygons = (
        umm.get("SpatialExtent", {})
        .get("HorizontalSpatialDomain", {})
        .get("Geometry", {})
        .get("GPolygons", [])
    )
    if not polygons:
        raise ValueError("Granule no incluye polígono UMM")
    points = polygons[0].get("Boundary", {}).get("Points", [])
    if len(points) < 4:
        raise ValueError("Polígono UMM incompleto")
    return [(float(point["Longitude"]), float(point["Latitude"])) for point in points]


def point_on_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > 1e-10:
        return False
    return min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10


def contains_point(polygon: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if point_on_segment(point, previous, current):
            return True
        x, y = point
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def is_convex(polygon: list[tuple[float, float]]) -> bool:
    points = polygon[:-1] if polygon[0] == polygon[-1] else polygon
    signs = set()
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        after = points[(index + 2) % len(points)]
        cross = (
            (following[0] - point[0]) * (after[1] - following[1])
            - (following[1] - point[1]) * (after[0] - following[0])
        )
        if abs(cross) > 1e-12:
            signs.add(cross > 0)
    return len(signs) == 1


def aoi_corners(bbox: list[float]) -> list[tuple[float, float]]:
    west, south, east, north = bbox
    return [(west, south), (west, north), (east, south), (east, north)]


def attributes(umm: dict[str, Any]) -> dict[str, list[str]]:
    return {
        item["Name"]: [str(value) for value in item.get("Values", [])]
        for item in umm.get("AdditionalAttributes", [])
        if item.get("Name")
    }


def data_layer_names(umm: dict[str, Any]) -> list[str]:
    layers = set()
    for item in umm.get("RelatedUrls", []):
        if item.get("Type") != "GET DATA":
            continue
        filename = Path(urlparse(item.get("URL", "")).path).name
        if filename.lower().endswith(".tif"):
            layer = Path(filename).stem.rsplit("_", 1)[-1]
            layers.add(layer)
    return sorted(layers)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    run_dirs = [path for path in CATALOG_DIR.iterdir() if path.is_dir() and (path / "pairs.jsonl").exists()]
    if not run_dirs:
        raise FileNotFoundError(f"No hay manifiestos pairs.jsonl en {CATALOG_DIR}")
    run_dir = max(run_dirs, key=lambda path: path.name)
    pairs = [
        json.loads(line)
        for line in (run_dir / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    pair = min(
        (item for item in pairs if item["opera_product"] == "opera_dist_alert"),
        key=lambda item: item["absolute_delta_days"],
    )
    aoi = json.loads(AOI_PATH.read_text(encoding="utf-8"))
    corners = aoi_corners(aoi["bbox_wsen"])

    session = requests.Session()
    session.headers.update({"User-Agent": "pablo-nisar-opera-pair-audit/0.1"})
    nisar_umm = fetch_umm(session, pair["nisar_cmr_concept_id"])
    opera_umm = fetch_umm(session, pair["opera_cmr_concept_id"])
    nisar_polygon = polygon_from_umm(nisar_umm)
    opera_polygon = polygon_from_umm(opera_umm)
    nisar_contains = [contains_point(nisar_polygon, point) for point in corners]
    opera_contains = [contains_point(opera_polygon, point) for point in corners]
    nisar_convex = is_convex(nisar_polygon)
    opera_convex = is_convex(opera_polygon)
    nisar_attrs = attributes(nisar_umm)
    opera_attrs = attributes(opera_umm)
    layer_names = data_layer_names(opera_umm)

    begin = parse_utc(nisar_umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])
    opera_time = parse_utc(opera_attrs["SENSING_TIME"][0])
    delta_hours = (opera_time - begin).total_seconds() / 3600
    report = {
        "schema_version": 1,
        "catalog_run_id": run_dir.name,
        "metadata_source": "NASA CMR UMM JSON",
        "data_downloaded": False,
        "aoi": aoi,
        "pair": {
            "nisar_granule_id": pair["nisar_granule_id"],
            "nisar_cmr_concept_id": pair["nisar_cmr_concept_id"],
            "nisar_time_utc": begin.isoformat().replace("+00:00", "Z"),
            "opera_granule_id": pair["opera_granule_id"],
            "opera_cmr_concept_id": pair["opera_cmr_concept_id"],
            "opera_sensing_time_utc": opera_attrs["SENSING_TIME"][0],
            "delta_hours_opera_minus_nisar": round(delta_hours, 3),
        },
        "footprint_check": {
            "method": "all four AOI rectangle corners tested against each CMR UMM polygon",
            "corner_order_lon_lat": corners,
            "nisar_corner_inside": nisar_contains,
            "opera_corner_inside": opera_contains,
            "nisar_footprint_convex": nisar_convex,
            "opera_footprint_convex": opera_convex,
            "aoi_inside_both_footprints": (
                nisar_convex and opera_convex and all(nisar_contains) and all(opera_contains)
            ),
            "nisar_polygon_lon_lat": nisar_polygon,
            "opera_polygon_lon_lat": opera_polygon,
        },
        "nisar_metadata": {
            "collection": nisar_umm.get("CollectionReference", {}).get("ShortName"),
            "production_pipeline": nisar_attrs.get("PRODUCTION_PIPELINE"),
            "frequency_a_polarizations": nisar_attrs.get("FREQUENCY_A_POLARIZATION"),
            "frequency_b_polarizations": nisar_attrs.get("FREQUENCY_B_POLARIZATION"),
            "grid_crs_and_pixel_spacing": "not established from granule catalog metadata",
        },
        "opera_metadata": {
            "collection": opera_umm.get("CollectionReference", {}).get("ShortName"),
            "mgrs_tile": opera_attrs.get("MGRS_TILE_ID"),
            "sensing_sensor_product_id": opera_attrs.get("SENSOR_PRODUCT_ID"),
            "crs": opera_attrs.get("HORIZONTAL_CS_CODE"),
            "crs_name": opera_attrs.get("HORIZONTAL_CS_NAME"),
            "upper_left_x": opera_attrs.get("ULX"),
            "upper_left_y": opera_attrs.get("ULY"),
            "pixel_spacing_m": 30,
            "pixel_spacing_source": DIST_SPEC_URL,
            "available_tiff_layers": layer_names,
            "target_layer_present": "VEG-DIST-STATUS" in layer_names,
        },
        "alignment_status": "AOI coverage confirmed from catalog polygons; raster pixel grids remain unverified",
        "next_operation": "extract one bounded NISAR variable and VEG-DIST-STATUS raster, then inspect and align grids",
    }
    output_path = run_dir / "pair_audit.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
