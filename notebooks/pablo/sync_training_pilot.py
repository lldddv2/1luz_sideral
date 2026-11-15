#!/usr/bin/env python3
"""Build one bounded, aligned NISAR–OPERA training sample."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import urllib3.util.connection

urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

import earthaccess
import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.windows import Window


ROOT = Path(__file__).resolve().parent
NISAR_EXTRACTOR_ROOT = ROOT.parent / "jose"
sys.path.insert(0, str(NISAR_EXTRACTOR_ROOT))

from nisar_extractor.models import ExtractionConfig  # noqa: E402
from nisar_extractor.service import NisarExtractor  # noqa: E402


NISAR_VARIABLES = {
    "frequencyA/HHHH": "/science/LSAR/GCOV/grids/frequencyA/HHHH",
    "frequencyA/HVHV": "/science/LSAR/GCOV/grids/frequencyA/HVHV",
}
OPERA_LAYERS = ("VEG-DIST-STATUS", "VEG-DIST-DATE")
MAX_OPERA_ASSET_BYTES = 8 * 1024 * 1024
MAX_NISAR_OUTPUT_BYTES = 32 * 1024 * 1024
NISAR_QUERY_PADDING = timedelta(minutes=2)
DATE_EPOCH = date(2020, 12, 31)
TEMPORAL_NODATA = -32768


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_catalog_run() -> Path:
    runs = [
        path
        for path in (ROOT / "catalog").iterdir()
        if path.is_dir() and (path / "candidate_positive_aois.json").exists()
    ]
    if not runs:
        raise FileNotFoundError("No hay candidatos positivos en notebooks/pablo/catalog")
    return max(runs, key=lambda path: path.name)


def load_inputs(run_dir: Path, candidate_index: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidates = json.loads((run_dir / "candidate_positive_aois.json").read_text())
    if candidates.get("status") != "positive_windows_found":
        raise ValueError("El catálogo no contiene ventanas positivas")
    choices = candidates.get("candidates", [])
    if not 0 <= candidate_index < len(choices):
        raise IndexError(f"candidate-index debe estar entre 0 y {len(choices) - 1}")
    candidate = dict(choices[candidate_index])
    candidate["sample_size_pixels"] = candidates["aoi_size_pixels"]

    audit = json.loads((run_dir / "pair_audit.json").read_text())
    pair_info = audit["pair"]
    pair = None
    for line in (run_dir / "pairs.jsonl").read_text().splitlines():
        item = json.loads(line)
        if (
            item["nisar_granule_id"] == pair_info["nisar_granule_id"]
            and item["opera_granule_id"] == pair_info["opera_granule_id"]
            and item["opera_product"] == "opera_dist_alert"
        ):
            pair = item
            break
    if pair is None:
        raise ValueError("No se halló el par NISAR–DIST-ALERT de la auditoría")
    if candidates.get("nisar_granule_id") != pair["nisar_granule_id"]:
        raise ValueError("Candidatos y par NISAR no coinciden")
    if candidates.get("opera_granule_id") != pair["opera_granule_id"]:
        raise ValueError("Candidatos y par OPERA no coinciden")
    return candidate, pair, audit


def fetch_umm(concept_id: str) -> dict[str, Any]:
    response = requests.get(
        "https://cmr.earthdata.nasa.gov/search/granules.umm_json",
        params={"concept_id": concept_id},
        timeout=(10, 40),
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if len(items) != 1:
        raise RuntimeError(f"CMR devolvió {len(items)} granules para {concept_id}")
    return items[0]["umm"]


def opera_layer_url(umm: dict[str, Any], granule_id: str, layer: str) -> str:
    expected_name = f"{granule_id}_{layer}.tif"
    matches = [
        item["URL"]
        for item in umm.get("RelatedUrls", [])
        if item.get("Type") == "GET DATA"
        and Path(item.get("URL", "")).name == expected_name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"CMR no devolvió un enlace único para {expected_name}")
    return matches[0]


def download_asset(session: requests.Session, url: str, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        size = path.stat().st_size
        if size > MAX_OPERA_ASSET_BYTES:
            raise RuntimeError(f"Asset local excede el límite: {path}")
        return {"path": str(path), "url": url, "bytes": size, "sha256": sha256(path), "reused": True}

    response = session.get(url, stream=True, timeout=(30, 60))
    response.raise_for_status()
    declared = response.headers.get("Content-Length")
    if declared and int(declared) > MAX_OPERA_ASSET_BYTES:
        response.close()
        raise RuntimeError(f"Asset excede el límite de {MAX_OPERA_ASSET_BYTES} bytes")
    received = 0
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as stream:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > MAX_OPERA_ASSET_BYTES:
                    raise RuntimeError(f"Asset excede el límite de {MAX_OPERA_ASSET_BYTES} bytes")
                stream.write(chunk)
        if declared and received != int(declared):
            raise IOError(f"Descarga incompleta: esperado {declared}, recibido {received}")
        os.replace(temporary_name, path)
    finally:
        response.close()
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return {"path": str(path), "url": url, "bytes": received, "sha256": sha256(path), "reused": False}


def crop_opera_layer(
    source_path: Path,
    destination_path: Path,
    candidate: dict[str, Any],
    reference: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row, col = int(candidate["row"]), int(candidate["col"])
    height, width = (int(value) for value in candidate["sample_size_pixels"])
    window = Window(col, row, width, height)
    with rasterio.open(source_path) as src:
        if row + height > src.height or col + width > src.width:
            raise RuntimeError(f"AOI excede dimensiones de {source_path.name}")
        if reference is not None:
            if src.crs != reference["crs"] or src.width != reference["width"] or src.height != reference["height"]:
                raise RuntimeError("Capas OPERA tienen CRS o dimensiones diferentes")
            if not np.allclose(tuple(src.transform), reference["transform"], rtol=0, atol=1e-9):
                raise RuntimeError("Capas OPERA no comparten la misma transformación")
        data = src.read(window=window)
        profile = src.profile.copy()
        profile.update(
            width=width,
            height=height,
            transform=src.window_transform(window),
            compress="deflate",
        )
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(destination_path, "w", **profile) as dst:
            dst.write(data)
            dst.update_tags(**src.tags())
            for band in range(1, src.count + 1):
                dst.update_tags(band, **src.tags(band))
                if src.descriptions[band - 1]:
                    dst.set_band_description(band, src.descriptions[band - 1])
        metadata = {
            "path": str(destination_path),
            "width": width,
            "height": height,
            "crs": src.crs.to_string() if src.crs else None,
            "transform": list(src.window_transform(window))[:6],
            "pixel_size": [src.transform.a, src.transform.e],
            "dtype": list(src.dtypes),
            "nodata": src.nodata,
            "tags": src.tags(),
        }
        info = {
            "crs": src.crs,
            "width": src.width,
            "height": src.height,
            "transform": tuple(src.transform),
            "crop_transform": src.window_transform(window),
        }
        return metadata, info


def run_nisar_extraction(
    sample_dir: Path,
    candidate: dict[str, Any],
    pair: dict[str, Any],
    nisar_variables: dict[str, str],
    output_mib: float,
) -> dict[str, Path]:
    granule_id = pair["nisar_granule_id"]
    bbox = [float(value) for value in candidate["bbox_wsen"]]
    nisar_time = datetime.fromisoformat(pair["nisar_time_utc"].replace("Z", "+00:00"))
    query_start = (nisar_time - NISAR_QUERY_PADDING).isoformat().replace("+00:00", "Z")
    query_stop = (nisar_time + NISAR_QUERY_PADDING).isoformat().replace("+00:00", "Z")
    nisar_dir = sample_dir / "sources" / "nisar"
    nisar_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = nisar_dir / "inventory.json"
    config = ExtractionConfig(
        output_dir=str(nisar_dir),
        max_area_km2=2.0,
        max_products=10,
        max_output_bytes=int(output_mib * 1024 * 1024),
        max_concurrent=1,
        max_attempts=2,
    )
    with NisarExtractor(config) as extractor:
        inventory = extractor.discover(
            extractor.bbox(bbox),
            start=query_start,
            stop=query_stop,
            product_type="GCOV",
            production_configuration="PR",
            max_results=10,
            inventory_path=inventory_path,
        )
        matches = [product.product_id for product in inventory.products if product.product_id == granule_id]
        if len(matches) != 1:
            found = [product.product_id for product in inventory.products]
            raise RuntimeError(f"No se confirmó granule NISAR esperado; resultados: {found}")
        results = extractor.extract(
            inventory,
            product_ids=[granule_id],
            variables=list(nisar_variables.values()),
        )
    if len(results) != 1 or results[0].get("state") != "downloaded":
        raise RuntimeError(f"Extracción NISAR falló: {results}")
    output_paths = {
        item["variable"]: Path(item["path"])
        for item in results[0]["outputs"]
    }
    missing = set(nisar_variables.values()) - set(output_paths)
    if missing:
        raise RuntimeError(f"Harmony no devolvió variables pedidas: {sorted(missing)}")
    return output_paths


def align_feature(
    source_path: Path,
    destination: np.ndarray,
    target_transform: rasterio.Affine,
    target_crs: rasterio.crs.CRS,
) -> dict[str, float | int]:
    with rasterio.open(source_path) as src:
        if src.count != 1:
            raise RuntimeError(f"Canal NISAR debe tener una banda: {source_path}")
        source = src.read(1, masked=True).filled(-9999.0).astype(np.float32, copy=False)
        reproject(
            source=source,
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata if src.nodata is not None else -9999.0,
            dst_transform=target_transform,
            dst_crs=target_crs,
            dst_nodata=-9999.0,
            resampling=Resampling.average,
            init_dest_nodata=True,
        )
    valid = destination[np.isfinite(destination) & (destination != -9999.0)]
    if not valid.size:
        raise RuntimeError(f"Canal NISAR no cubre AOI: {source_path.name}")
    return {
        "valid_pixels": int(valid.size),
        "valid_percent": round(valid.size / destination.size * 100, 2),
        "p02": float(np.percentile(valid, 2)),
        "median": float(np.median(valid)),
        "p98": float(np.percentile(valid, 98)),
    }


def pixel_size_m(path: Path) -> list[float]:
    with rasterio.open(path) as src:
        return [abs(float(src.transform.a)), abs(float(src.transform.e))]


def write_raster(
    path: Path,
    data: np.ndarray,
    *,
    crs: rasterio.crs.CRS,
    transform: rasterio.Affine,
    descriptions: list[str],
    dtype: str,
    nodata: int | float,
    tags: dict[str, str],
) -> None:
    count, height, width = data.shape
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": count,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "tiled": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype, copy=False))
        dst.update_tags(**tags)
        for index, description in enumerate(descriptions, start=1):
            dst.set_band_description(index, description)


def run(args, nisar_variables: dict[str, str]) -> dict[str, Any]:
    run_dir = Path(args.catalog_run).resolve() if args.catalog_run else latest_catalog_run()
    candidate, pair, _audit = load_inputs(run_dir, args.candidate_index)
    sample_day = pair["nisar_time_utc"][:10].replace("-", "")
    sample_id = f"cv_{sample_day}_row{candidate['row']}_col{candidate['col']}"
    sample_dir = Path(args.output_dir).resolve() if args.output_dir else (
        ROOT / "data" / "datasets" / run_dir.name / "samples" / sample_id
    )
    sources_dir = sample_dir / "sources" / "opera"
    aligned_dir = sample_dir / "aligned"
    sample_dir.mkdir(parents=True, exist_ok=True)

    opera_umm = fetch_umm(pair["opera_cmr_concept_id"])
    granule_id = pair["opera_granule_id"]
    earthaccess.login(strategy="netrc")
    opera_session = earthaccess.get_requests_https_session()
    opera_sources: dict[str, Path] = {}
    opera_downloads: dict[str, Any] = {}
    for layer in OPERA_LAYERS:
        url = opera_layer_url(opera_umm, granule_id, layer)
        path = sources_dir / f"{layer}.source.tif"
        opera_downloads[layer] = download_asset(opera_session, url, path)
        opera_sources[layer] = path

    status_source = opera_sources["VEG-DIST-STATUS"]
    date_source = opera_sources["VEG-DIST-DATE"]
    status_crop_path = sources_dir / "VEG-DIST-STATUS.tif"
    date_crop_path = sources_dir / "VEG-DIST-DATE.tif"
    status_crop, reference = crop_opera_layer(
        status_source, status_crop_path, candidate, None
    )
    date_crop, _ = crop_opera_layer(
        date_source, date_crop_path, candidate, reference
    )
    for asset in opera_downloads.values():
        asset["path"] = Path(asset["path"]).relative_to(sample_dir).as_posix()
    status_crop["path"] = Path(status_crop["path"]).relative_to(sample_dir).as_posix()
    date_crop["path"] = Path(date_crop["path"]).relative_to(sample_dir).as_posix()

    native_features = run_nisar_extraction(
        sample_dir, candidate, pair, nisar_variables, args.max_nisar_output_mib
    )
    variable_to_key = {value: key for key, value in nisar_variables.items()}
    feature_paths = {
        variable_to_key[variable]: path for variable, path in native_features.items()
    }

    with rasterio.open(status_crop_path) as status_ds, rasterio.open(date_crop_path) as date_ds:
        if status_ds.shape != date_ds.shape or status_ds.crs != date_ds.crs:
            raise RuntimeError("Recortes de etiqueta no comparten grilla")
        target_height, target_width = status_ds.height, status_ds.width
        target_transform = status_ds.transform
        target_crs = status_ds.crs
        status_data = status_ds.read(1)
        event_days_data = date_ds.read(1).astype(np.int16, copy=False)
        status_nodata = status_ds.nodata
        event_nodata = date_ds.nodata

    feature_stack = np.full(
        (len(nisar_variables), target_height, target_width),
        -9999.0,
        dtype=np.float32,
    )
    feature_stats = {}
    for channel_index, (channel_key, _) in enumerate(nisar_variables.items()):
        feature_stats[channel_key] = align_feature(
            feature_paths[channel_key],
            feature_stack[channel_index],
            target_transform,
            target_crs,
        )
    if any(value["valid_percent"] < 95 for value in feature_stats.values()):
        raise RuntimeError(f"Cobertura NISAR menor de 95%: {feature_stats}")
    valid_features = np.all(feature_stack != -9999.0, axis=0)

    nisar_date = datetime.fromisoformat(
        pair["nisar_time_utc"].replace("Z", "+00:00")
    ).date()
    has_event_date = event_days_data > 0
    event_delta = np.full(event_days_data.shape, TEMPORAL_NODATA, dtype=np.int16)
    event_delta[has_event_date] = (
        event_days_data[has_event_date] + (DATE_EPOCH - nisar_date).days
    )

    feature_path = aligned_dir / "features_frequencyA.tif"
    write_raster(
        feature_path,
        feature_stack,
        crs=target_crs,
        transform=target_transform,
        descriptions=list(nisar_variables),
        dtype="float32",
        nodata=-9999.0,
        tags={
            "product": "NISAR_L2_GCOV",
            "frequency": "A",
            "radiometry": "gamma0 power; source values preserved",
            "resampling": "area average from native NISAR grid to OPERA 30 m grid",
            "source_granule": pair["nisar_granule_id"],
        },
    )
    write_raster(
        aligned_dir / "labels_status.tif",
        status_data[np.newaxis, ...],
        crs=target_crs,
        transform=target_transform,
        descriptions=["VEG-DIST-STATUS"],
        dtype="uint8",
        nodata=255 if status_nodata is None else int(status_nodata),
        tags={"label_source": "OPERA DIST-ALERT-HLS", "resampling": "native categorical grid"},
    )
    write_raster(
        aligned_dir / "labels_event_day.tif",
        event_days_data[np.newaxis, ...],
        crs=target_crs,
        transform=target_transform,
        descriptions=["VEG-DIST-DATE: days since 2020-12-31"],
        dtype="int16",
        nodata=-1 if event_nodata is None else int(event_nodata),
        tags={
            "label_source": "OPERA DIST-ALERT-HLS",
            "date_epoch": "2020-12-31",
            "zero_value": "no vegetation anomaly",
        },
    )
    write_raster(
        aligned_dir / "labels_event_delta_days_from_nisar.tif",
        event_delta[np.newaxis, ...],
        crs=target_crs,
        transform=target_transform,
        descriptions=["OPERA first-anomaly date minus NISAR acquisition date, days"],
        dtype="int16",
        nodata=TEMPORAL_NODATA,
        tags={
            "sign": "positive means OPERA anomaly date is after NISAR acquisition date",
            "resolution": "one calendar day; source date layer has daily precision",
            "no_event_value": str(TEMPORAL_NODATA),
        },
    )
    status_valid = status_data != (255 if status_nodata is None else status_nodata)
    valid_sample_mask = valid_features & status_valid
    write_raster(
        aligned_dir / "valid_sample_mask.tif",
        valid_sample_mask[np.newaxis, ...].astype(np.uint8),
        crs=target_crs,
        transform=target_transform,
        descriptions=["1=features and status label valid; 0=exclude"],
        dtype="uint8",
        nodata=255,
        tags={"valid_value": "1", "excluded_value": "0"},
    )

    valid_status = status_data
    if status_nodata is not None:
        valid_status = status_data[status_data != status_nodata]
    status_values, status_counts = np.unique(valid_status, return_counts=True)
    date_valid_values, date_valid_counts = np.unique(event_days_data, return_counts=True)
    scene_delta = float(pair["signed_delta_seconds_opera_minus_nisar"])
    event_delta_valid = event_delta != TEMPORAL_NODATA
    event_delta_values = event_delta[event_delta_valid]
    channel_metadata = []
    for key, variable in nisar_variables.items():
        channel_metadata.append({
            "name": key,
            "variable": variable,
            "source_granule": pair["nisar_granule_id"],
            "frequency": "A",
            "polarization_term": key.rsplit("/", 1)[-1],
            "source_pixel_size_m": pixel_size_m(feature_paths[key]),
            "target_resampling": "average",
            "statistics": feature_stats[key],
        })
    sample = {
        "schema_version": 1,
        "sample_id": sample_id,
        "status": "pilot_aligned",
        "source_products": {
            "nisar_granule_id": pair["nisar_granule_id"],
            "nisar_cmr_concept_id": pair["nisar_cmr_concept_id"],
            "opera_granule_id": pair["opera_granule_id"],
            "opera_cmr_concept_id": pair["opera_cmr_concept_id"],
            "catalog_run_id": run_dir.name,
        },
        "sample_size_pixels": [target_height, target_width],
        "grid": {
            "crs": target_crs.to_string(),
            "transform": list(target_transform)[:6],
            "pixel_size_m": [target_transform.a, target_transform.e],
            "target_grid": "OPERA DIST-HLS native 30 m",
        },
        "features": {
            "path": str(feature_path.relative_to(sample_dir)),
            "shape": [len(nisar_variables), target_height, target_width],
            "axis_order": ["channel", "y", "x"],
            "channels": channel_metadata,
            "nodata": -9999.0,
        },
        "labels": {
            "status": "aligned/labels_status.tif",
            "date_days_since_2020_12_31": "aligned/labels_event_day.tif",
            "event_delta_days_from_nisar": "aligned/labels_event_delta_days_from_nisar.tif",
            "valid_sample_mask": "aligned/valid_sample_mask.tif",
            "valid_sample_pixels": int(valid_sample_mask.sum()),
            "event_delta_valid_pixels": int(event_delta_valid.sum()),
            "event_delta_days_min": int(event_delta_values.min()) if event_delta_values.size else None,
            "event_delta_days_median": float(np.median(event_delta_values)) if event_delta_values.size else None,
            "event_delta_days_max": int(event_delta_values.max()) if event_delta_values.size else None,
            "event_delta_after_nisar_pixels": int(np.count_nonzero(event_delta_values > 0)),
            "status_value_counts": {
                str(int(value)): int(count)
                for value, count in zip(status_values, status_counts, strict=True)
            },
            "event_day_value_counts": {
                str(int(value)): int(count)
                for value, count in zip(date_valid_values, date_valid_counts, strict=True)
            },
            "temporal_offset_meaning": "per-pixel anomaly first-detection date minus NISAR acquisition date; daily precision",
        },
        "temporal": {
            "nisar_acquisition_start_utc": pair["nisar_time_utc"],
            "opera_hls_sensing_time_utc": pair["opera_time_utc"],
            "opera_minus_nisar_sensing_shift_seconds": scene_delta,
            "opera_minus_nisar_sensing_shift_hours": pair["signed_delta_hours_opera_minus_nisar"],
            "pair_time_basis": "CMR start times; this is not event onset",
            "opera_layer_update_time_utc": status_crop["tags"].get("Update_Date"),
            "opera_input_dist_alert_granule": status_crop["tags"].get("Input_DIST-ALERT_granule"),
            "event_delta_raster_nodata": TEMPORAL_NODATA,
        },
        "source_assets": {
            "opera_downloads": opera_downloads,
            "opera_status_crop": status_crop,
            "opera_event_date_crop": date_crop,
            "nisar_source_variables": {
                key: {
                    "path": str(path.relative_to(sample_dir)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for key, path in feature_paths.items()
            },
            "nisar_inventory": "sources/nisar/inventory.json",
        },
        "aoi": {
            "bbox_wsen": candidate["bbox_wsen"],
            "opera_window_row_col_height_width": [
                candidate["row"],
                candidate["col"],
                target_height,
                target_width,
            ],
            "opera_status_counts_from_candidate_scan": candidate["status_counts"],
        },
        "limitations": [
            "One AOI and one NISAR–OPERA pair; not a training dataset yet.",
            "OPERA event date is day-level first anomaly detection, not a causal label.",
            "Frequency B and additional polarizations are not included in this pilot.",
        ],
    }
    metadata_path = sample_dir / "sample.json"
    metadata_path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n")
    manifest_path = sample_dir.parent / "manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"sample_id": sample_id, "sample_metadata": str(metadata_path.relative_to(manifest_path.parent))}
    existing = []
    if manifest_path.exists():
        existing = [
            json.loads(line)
            for line in manifest_path.read_text().splitlines()
            if line.strip() and json.loads(line).get("sample_id") != sample_id
        ]
    existing.append(row)
    manifest_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in existing))
    return {
        "sample_id": sample_id,
        "sample_dir": str(sample_dir),
        "sample_metadata": str(metadata_path),
        "manifest": str(manifest_path),
        "shape": [target_height, target_width],
        "crs": target_crs.to_string(),
        "channels": list(nisar_variables),
        "feature_statistics": feature_stats,
        "status_value_counts": sample["labels"]["status_value_counts"],
        "event_day_value_counts": sample["labels"]["event_day_value_counts"],
        "scene_shift_seconds": scene_delta,
        "bytes": sum(path.stat().st_size for path in sample_dir.rglob("*") if path.is_file()),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-run", help="Carpeta de catálogo; usa la más reciente por defecto")
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--output-dir", help="Destino alternativo dentro de data/")
    parser.add_argument("--max-nisar-output-mib", type=float, default=32.0)
    parser.add_argument(
        "--nisar-variable",
        action="append",
        help="Variable GCOV exacta; repetir por canal. Por defecto: HH y HV de frecuencia A.",
    )
    args = parser.parse_args()
    if args.max_nisar_output_mib <= 0:
        parser.error("--max-nisar-output-mib debe ser positivo")
    selected_variables = args.nisar_variable or list(NISAR_VARIABLES.values())
    nisar_variables: dict[str, str] = {}
    for value in selected_variables:
        variable = value if value.startswith("/") else f"/science/LSAR/GCOV/grids/{value}"
        key = "/".join(variable.rstrip("/").split("/")[-2:])
        if key in nisar_variables:
            parser.error(f"Canal NISAR repetido: {key}")
        nisar_variables[key] = variable
    print(json.dumps(run(args, nisar_variables), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
