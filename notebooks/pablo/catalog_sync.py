#!/usr/bin/env python3
"""Search CMR metadata and write NISAR–OPERA temporal candidate pairs.

This script only requests catalog metadata. It never opens granule data links.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
DEFAULT_AOI = ROOT / "config" / "central_valley_candidate.json"
DEFAULT_OUTPUT = ROOT / "catalog"
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
PAGE_SIZE = 2000
TIMEOUT = (10, 40)
COLLECTIONS = {
    "nisar_gcov": ("NISAR_L2_GCOV_V1", "ASF"),
    "opera_dist_alert": ("OPERA_L3_DIST-ALERT-HLS_V1", "LPCLOUD"),
    "opera_dswx": ("OPERA_L3_DSWx-HLS_V1", "POCLOUD"),
}


def parse_date(value: str, *, is_stop: bool = False) -> datetime:
    parsed = date.fromisoformat(value)
    at = time.max if is_stop else time.min
    return datetime.combine(parsed, at, tzinfo=timezone.utc)


def cmr_time(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def geometry_bounds(entry: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Return west,south,east,north from CMR ECHO boxes or lat/lon polygons."""
    boxes = entry.get("boxes") or []
    if boxes:
        values = [float(item) for item in boxes[0].split()]
        if len(values) >= 4:
            south, west, north, east = values[:4]
            return west, south, east, north

    bounds: list[tuple[float, float]] = []
    polygons = entry.get("polygons") or []
    polygon_texts = []
    for polygon in polygons:
        if isinstance(polygon, str):
            polygon_texts.append(polygon)
        elif isinstance(polygon, list):
            polygon_texts.extend(item for item in polygon if isinstance(item, str))
    for polygon in polygon_texts:
        values = [float(item) for item in polygon.split()]
        if len(values) < 6 or len(values) % 2:
            continue
        # CMR ECHO polygons encode coordinate pairs as latitude, longitude.
        bounds.extend((values[index + 1], values[index]) for index in range(0, len(values), 2))
    if not bounds:
        return None
    longitudes, latitudes = zip(*bounds)
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def bounds_intersection(
    left: tuple[float, float, float, float] | None,
    right: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float] | None:
    if left is None or right is None:
        return None
    west = max(left[0], right[0])
    south = max(left[1], right[1])
    east = min(left[2], right[2])
    north = min(left[3], right[3])
    if west >= east or south >= north:
        return None
    return west, south, east, north


def query_collection(
    session: requests.Session,
    *,
    short_name: str,
    provider: str,
    bbox: list[float],
    start: datetime,
    stop: datetime,
) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    params = {
        "short_name": short_name,
        "provider": provider,
        "bounding_box": f"{west},{south},{east},{north}",
        "temporal": f"{cmr_time(start)},{cmr_time(stop)}",
        "page_size": PAGE_SIZE,
        "page_num": 1,
    }
    entries: list[dict[str, Any]] = []
    while True:
        response = session.get(CMR_URL, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        page = response.json().get("feed", {}).get("entry", [])
        entries.extend(page)
        hits_header = response.headers.get("CMR-Hits")
        total_hits = int(hits_header) if hits_header and hits_header.isdigit() else None
        if not page:
            return entries
        if total_hits is not None and len(entries) >= total_hits:
            return entries
        if total_hits is None and len(page) < PAGE_SIZE:
            return entries
        params["page_num"] += 1


def granule_record(entry: dict[str, Any], dataset: str) -> dict[str, Any]:
    granule_id = entry.get("producer_granule_id") or entry.get("title") or entry.get("id")
    return {
        "dataset": dataset,
        "granule_id": granule_id,
        "cmr_concept_id": entry.get("id"),
        "time_start": entry.get("time_start"),
        "time_end": entry.get("time_end"),
        "granule_size_mb_cmr": _float_or_none(entry.get("granule_size")),
        "footprint_bounds_wsen": geometry_bounds(entry),
    }


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def make_pairs(
    nisar: list[dict[str, Any]],
    opera: list[dict[str, Any]],
    aoi: tuple[float, float, float, float],
    tolerance_days: float,
) -> list[dict[str, Any]]:
    pairs = []
    for nisar_granule in nisar:
        nisar_time = iso_datetime(nisar_granule.get("time_start"))
        if nisar_time is None:
            continue
        nisar_aoi_intersection = bounds_intersection(
            nisar_granule.get("footprint_bounds_wsen"), aoi
        )
        if nisar_aoi_intersection is None:
            continue
        for opera_granule in opera:
            opera_time = iso_datetime(opera_granule.get("time_start"))
            if opera_time is None:
                continue
            opera_aoi_intersection = bounds_intersection(
                opera_granule.get("footprint_bounds_wsen"), aoi
            )
            if opera_aoi_intersection is None:
                continue
            common_envelope = bounds_intersection(
                nisar_granule.get("footprint_bounds_wsen"),
                opera_granule.get("footprint_bounds_wsen"),
            )
            if common_envelope is None:
                continue

            signed_hours = (opera_time - nisar_time).total_seconds() / 3600
            signed_seconds = (opera_time - nisar_time).total_seconds()
            abs_days = abs(signed_hours) / 24
            if abs_days > tolerance_days:
                continue
            pair = {
                "nisar_granule_id": nisar_granule["granule_id"],
                "nisar_cmr_concept_id": nisar_granule["cmr_concept_id"],
                "nisar_time_utc": nisar_granule["time_start"],
                "opera_product": opera_granule["dataset"],
                "opera_granule_id": opera_granule["granule_id"],
                "opera_cmr_concept_id": opera_granule["cmr_concept_id"],
                "opera_time_utc": opera_granule["time_start"],
                "signed_delta_seconds_opera_minus_nisar": round(signed_seconds, 3),
                "signed_delta_hours_opera_minus_nisar": round(signed_hours, 6),
                "absolute_delta_seconds": round(abs(signed_seconds), 3),
                "absolute_delta_days": round(abs_days, 6),
                "temporal_match": (
                    "near_coincident_24h" if abs_days <= 1 else "close_72h" if abs_days <= 3 else "candidate"
                ),
                "spatial_screen": "each CMR AOI filter passes; footprint bounding envelopes overlap",
                "common_envelope_bounds_wsen": common_envelope,
                "nisar_aoi_intersection_bounds_wsen": nisar_aoi_intersection,
                "opera_aoi_intersection_bounds_wsen": opera_aoi_intersection,
            }
            pairs.append(pair)
    return sorted(pairs, key=lambda row: (row["absolute_delta_seconds"], row["opera_product"], row["opera_granule_id"]))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI, help="JSON con bbox oeste,sur,este,norte")
    parser.add_argument("--start", default="2026-10-21", help="Fecha UTC inicial YYYY-MM-DD")
    parser.add_argument("--stop", default=datetime.now(timezone.utc).date().isoformat(), help="Fecha UTC final YYYY-MM-DD")
    parser.add_argument("--tolerance-days", type=float, default=6.0, help="Diferencia temporal maxima para candidatos")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directorio de salida bajo notebooks/pablo")
    args = parser.parse_args()

    aoi_doc = json.loads(args.aoi.read_text(encoding="utf-8"))
    bbox = [float(value) for value in aoi_doc["bbox_wsen"]]
    if (
        len(bbox) != 4
        or bbox[0] >= bbox[2]
        or bbox[1] >= bbox[3]
        or not (-180 <= bbox[0] <= 180 and -180 <= bbox[2] <= 180)
        or not (-90 <= bbox[1] <= 90 and -90 <= bbox[3] <= 90)
    ):
        parser.error("bbox_wsen debe ser [oeste, sur, este, norte], sin cruce del antimeridiano")
    start = parse_date(args.start)
    stop = parse_date(args.stop, is_stop=True)
    if start > stop:
        parser.error("--start debe ser anterior o igual a --stop")
    if args.tolerance_days < 0 or not math.isfinite(args.tolerance_days):
        parser.error("--tolerance-days debe ser finito y no negativo")

    session = requests.Session()
    session.headers.update({"User-Agent": "pablo-nisar-opera-catalog-sync/0.1"})
    raw: dict[str, list[dict[str, Any]]] = {}
    for dataset, (short_name, provider) in COLLECTIONS.items():
        entries = query_collection(
            session,
            short_name=short_name,
            provider=provider,
            bbox=bbox,
            start=start,
            stop=stop,
        )
        if dataset == "nisar_gcov":
            # Restrict probe to validated production configuration.
            entries = [
                item for item in entries
                if "_PR_GCOV_" in (item.get("producer_granule_id") or item.get("title") or "")
            ]
        raw[dataset] = entries

    records = {
        name: [granule_record(entry, name) for entry in entries]
        for name, entries in raw.items()
    }
    nisar = records["nisar_gcov"]
    pairs_by_product = {
        name: make_pairs(nisar, records[name], tuple(bbox), args.tolerance_days)
        for name in ("opera_dist_alert", "opera_dswx")
    }
    pairs = sorted(
        [pair for product_pairs in pairs_by_product.values() for pair in product_pairs],
        key=lambda row: (row["absolute_delta_days"], row["opera_product"], row["opera_granule_id"]),
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output / run_id
    save_json(output_dir / "catalogs.json", records)
    with (output_dir / "pairs.jsonl").open("w", encoding="utf-8") as stream:
        for pair in pairs:
            stream.write(json.dumps(pair, ensure_ascii=False) + "\n")

    counts = {name: len(items) for name, items in records.items()}
    pair_counts = {name: len(items) for name, items in pairs_by_product.items()}
    temporal_counts: dict[str, int] = {}
    for pair in pairs:
        label = pair["temporal_match"]
        temporal_counts[label] = temporal_counts.get(label, 0) + 1
    summary = {
        "schema_version": 1,
        "run_id_utc": run_id,
        "source": "NASA CMR metadata API",
        "data_downloaded": False,
        "aoi": aoi_doc,
        "bbox_wsen": bbox,
        "date_range_utc": {"start": cmr_time(start), "stop": cmr_time(stop)},
        "nisar_collection": COLLECTIONS["nisar_gcov"][0],
        "opera_collections": {
            name: COLLECTIONS[name][0] for name in ("opera_dist_alert", "opera_dswx")
        },
        "temporal_tolerance_days": args.tolerance_days,
        "catalog_granule_counts": counts,
        "candidate_pair_counts": pair_counts,
        "total_candidate_pairs": len(pairs),
        "temporal_match_counts": temporal_counts,
        "candidate_delta_days_range": {
            "min": min((pair["absolute_delta_days"] for pair in pairs), default=None),
            "max": max((pair["absolute_delta_days"] for pair in pairs), default=None),
        },
        "closest_pair_per_opera_product": {
            name: pairs_by_product[name][0] if pairs_by_product[name] else None
            for name in pairs_by_product
        },
        "caveat": "Spatial screen uses CMR AOI filters and footprint bounding envelopes; exact polygon intersection and pixel-grid alignment are not checked.",
    }
    save_json(output_dir / "summary.json", summary)
    print(json.dumps({"output_dir": str(output_dir), **summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
