#!/usr/bin/env python3
"""Inspect local OPERA categorical GeoTIFFs and create reports and maps."""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds
from rasterio.windows import Window


DIST_SPEC_URL = (
    "https://lpdaac.usgs.gov/documents/1766/"
    "OPERA_DIST_HLS_Product_Specification_V1.pdf"
)
DSWX_SPEC_URL = (
    "https://d2pn8kiwq2w21t.cloudfront.net/documents/"
    "OPERA_DSWx-HLS_ProductSpec_v1.0.0_D-107395_RevB.pdf"
)
DSWX_VISUALIZATION_URL = (
    "https://d2pn8kiwq2w21t.cloudfront.net/documents/DSWx_visualization_guide.pdf"
)

# Status values are from the official DIST-ALERT v1 specification, Table 4-1.
DIST_CATEGORIES: dict[int, dict[str, str]] = {
    0: {"label": "Sin perturbación", "color": "#e5e7eb", "group": "valid"},
    1: {"label": "Primera detección, <50%", "color": "#fdd49e", "group": "valid"},
    2: {"label": "Provisional, <50%", "color": "#fc8d59", "group": "valid"},
    3: {"label": "Confirmada, <50%", "color": "#d73027", "group": "valid"},
    4: {"label": "Primera detección, ≥50%", "color": "#fee08b", "group": "valid"},
    5: {"label": "Provisional, ≥50%", "color": "#f46d43", "group": "valid"},
    6: {"label": "Confirmada, ≥50%", "color": "#a50026", "group": "valid"},
    7: {"label": "Confirmada, <50%, finalizada", "color": "#b2182b", "group": "valid"},
    8: {"label": "Confirmada, ≥50%, finalizada", "color": "#67001f", "group": "valid"},
    255: {"label": "Sin datos", "color": "#ffffff", "group": "nodata"},
}

# B01_WTR v1.1 uses the final class scheme described by the official product
# specification and visualization guide; legacy code 9 is not assigned a class.
DSWX_CATEGORIES: dict[int, dict[str, str]] = {
    0: {"label": "No es agua", "color": "#ffffff", "group": "valid"},
    1: {"label": "Agua abierta", "color": "#2676b8", "group": "valid"},
    2: {"label": "Agua superficial parcial", "color": "#a6dba0", "group": "valid"},
    252: {"label": "Nieve/hielo (enmascarado)", "color": "#36d5e8", "group": "masked"},
    253: {"label": "Nube/sombra o adyacencia (enmascarado)", "color": "#999999", "group": "masked"},
    254: {"label": "Océano enmascarado", "color": "#073b6d", "group": "masked"},
    255: {"label": "Sin datos", "color": "#ffffff", "group": "nodata"},
}

PRODUCT_SPECS = {
    "VEG-DIST-STATUS": {
        "product": "OPERA DIST-ALERT-HLS",
        "categories": DIST_CATEGORIES,
        "specification": DIST_SPEC_URL,
        "color_source": "Paleta de visualización elegida por este script; la especificación define los códigos, no estos colores.",
    },
    "B01_WTR": {
        "product": "OPERA DSWx-HLS",
        "categories": DSWX_CATEGORIES,
        "specification": DSWX_SPEC_URL,
        "color_source": DSWX_VISUALIZATION_URL,
    },
}

TIMESTAMP_RE = re.compile(
    r"(?<!\d)(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?|"
    r"\d{8}T\d{6}Z?)(?!\d)"
)
MAX_MAP_DIMENSION = 1800
BLOCK_SIZE = 512


def _parse_timestamp(value: str) -> str | None:
    value = value.strip()
    try:
        if re.fullmatch(r"\d{8}T\d{6}Z?", value):
            parsed = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _timestamps_in(value: str) -> list[str]:
    found: list[str] = []
    for match in TIMESTAMP_RE.findall(value):
        parsed = _parse_timestamp(match)
        if parsed and parsed not in found:
            found.append(parsed)
    return found


def _identify_variable(path: Path, tags: dict[str, str], band_tags: dict[str, str]) -> str:
    search_text = " ".join(
        [path.as_posix(), *tags.keys(), *tags.values(), *band_tags.keys(), *band_tags.values()]
    ).upper()
    for variable in PRODUCT_SPECS:
        if variable in search_text:
            return variable
    return "desconocida"


def _identify_product(variable: str, path: Path, tags: dict[str, str]) -> str:
    if variable in PRODUCT_SPECS:
        return PRODUCT_SPECS[variable]["product"]
    search_text = " ".join([path.as_posix(), *tags.keys(), *tags.values()]).upper()
    if "DIST-ALERT" in search_text:
        return "OPERA DIST-ALERT-HLS"
    if "DSWX-HLS" in search_text or "DSWX_HLS" in search_text:
        return "OPERA DSWx-HLS"
    return "Producto no identificado"


def _acquisition_times(path: Path, tags: dict[str, str]) -> dict[str, Any]:
    priorities = ("SENSING_TIME", "ACQUISITION", "DATE_ACQUIRED", "SCENE_CENTER_TIME")
    for wanted in priorities:
        for key, value in tags.items():
            if wanted in key.upper():
                times = _timestamps_in(value)
                if times:
                    return {"timestamps_utc": times, "source": f"GeoTIFF tag: {key}"}

    # OPERA filenames encode the acquisition timestamp before the production
    # timestamp. This is a fallback only when metadata contains no sensing time.
    times = _timestamps_in(path.stem)
    if times:
        return {"timestamps_utc": times[:1], "source": "product filename convention (fallback)"}
    return {"timestamps_utc": [], "source": None}


def _is_nodata(values: np.ndarray, dataset_mask: np.ndarray, nodata: float | int | None,
               spec_nodata: set[int]) -> np.ndarray:
    mask = dataset_mask == 0
    if nodata is not None:
        try:
            if math.isnan(float(nodata)):
                mask |= np.isnan(values)
            else:
                mask |= values == nodata
        except (TypeError, ValueError):
            mask |= values == nodata
    if spec_nodata:
        mask |= np.isin(values, list(spec_nodata))
    return mask


def _count_values(dataset: rasterio.io.DatasetReader, categories: dict[int, dict[str, str]]) -> dict[str, Any]:
    histogram: Counter[int] = Counter()
    total = int(dataset.width * dataset.height)
    masked_pixels = 0
    spec_nodata = {code for code, row in categories.items() if row["group"] == "nodata"}
    masked_codes = {code for code, row in categories.items() if row["group"] == "masked"}
    valid_codes = {code for code, row in categories.items() if row["group"] == "valid"}

    for row in range(0, dataset.height, BLOCK_SIZE):
        height = min(BLOCK_SIZE, dataset.height - row)
        for col in range(0, dataset.width, BLOCK_SIZE):
            width = min(BLOCK_SIZE, dataset.width - col)
            window = Window(col, row, width, height)
            values = dataset.read(1, window=window, masked=False)
            mask = dataset.read_masks(1, window=window)
            no_data = _is_nodata(values, mask, dataset.nodata, spec_nodata)
            masked_pixels += int(np.count_nonzero(mask == 0))
            observed = values[~no_data]
            if observed.size:
                codes, counts = np.unique(observed, return_counts=True)
                histogram.update({int(code): int(count) for code, count in zip(codes, counts, strict=True)})

    nodata_count = total - sum(histogram.values())
    valid_count = sum(histogram.get(code, 0) for code in valid_codes)
    class_masked_count = sum(histogram.get(code, 0) for code in masked_codes)
    unknown_count = sum(
        count for code, count in histogram.items()
        if code not in valid_codes and code not in masked_codes
    )

    rows: list[dict[str, Any]] = []
    for code in sorted(categories):
        category = categories[code]
        count = histogram.get(code, 0)
        if category["group"] == "nodata":
            count = nodata_count
        rows.append({
            "code": code,
            "label": category["label"],
            "group": category["group"],
            "count": count,
            "percent_of_all_pixels": (count / total * 100) if total else 0.0,
            "percent_of_valid_classes": (
                count / valid_count * 100 if category["group"] == "valid" and valid_count else None
            ),
        })
    for code, count in sorted(histogram.items()):
        if code not in categories:
            rows.append({
                "code": code,
                "label": f"Código {code} no documentado en la especificación consultada",
                "group": "unknown",
                "count": count,
                "percent_of_all_pixels": (count / total * 100) if total else 0.0,
                "percent_of_valid_classes": None,
            })

    return {
        "total_pixels": total,
        "valid_class_pixels": valid_count,
        "masked_class_pixels": class_masked_count,
        "nodata_pixels": nodata_count,
        "unknown_code_pixels": unknown_count,
        "dataset_masked_pixels": masked_pixels,
        "categories": rows,
    }


def _safe_output_stem(relative_path: Path) -> str:
    text = "__".join(relative_path.with_suffix("").parts)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "geotiff"


def _make_map(
    dataset: rasterio.io.DatasetReader,
    relative_path: Path,
    output_path: Path,
    categories: dict[int, dict[str, str]],
    stats: dict[str, Any],
    product: str,
    variable: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    scale = min(1.0, MAX_MAP_DIMENSION / max(dataset.width, dataset.height))
    out_height = max(1, int(round(dataset.height * scale)))
    out_width = max(1, int(round(dataset.width * scale)))
    values = dataset.read(
        1, out_shape=(out_height, out_width), resampling=Resampling.nearest, masked=False
    )
    masks = dataset.read_masks(
        1, out_shape=(out_height, out_width), resampling=Resampling.nearest
    )
    spec_nodata = {code for code, row in categories.items() if row["group"] == "nodata"}
    no_data = _is_nodata(values, masks, dataset.nodata, spec_nodata)

    present_codes = {int(value) for value in np.unique(values[~no_data])}
    known_codes = [code for code in sorted(categories) if code in present_codes]
    unknown_codes = sorted(present_codes - set(categories))
    display_codes = known_codes + unknown_codes
    display = np.full(values.shape, np.nan, dtype=np.float32)
    color_list: list[str] = []
    legend: list[Patch] = []

    for index, code in enumerate(display_codes):
        display[values == code] = index
        if code in categories:
            category = categories[code]
            color = category["color"]
            label = category["label"]
        else:
            color = "#ff00ff"
            label = f"Código {code} no documentado"
        color_list.append(color)
        count = next((r["count"] for r in stats["categories"] if r["code"] == code), 0)
        legend.append(Patch(facecolor=color, edgecolor="#555555", label=f"{code}: {label} ({count:,})"))

    for row in stats["categories"]:
        if row["group"] == "nodata" and row["count"]:
            legend.append(
                Patch(
                    facecolor="#eeeeee",
                    edgecolor="#555555",
                    label=f"{row['code']}: {row['label']} (transparente; {row['count']:,})",
                )
            )

    if not color_list:
        color_list = ["#ffffff"]
    cmap = ListedColormap(color_list)
    cmap.set_bad(color=(1, 1, 1, 0))
    norm = BoundaryNorm(np.arange(-0.5, len(color_list) + 0.5, 1), cmap.N)
    left, bottom, right, top = dataset.bounds

    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    ax.set_facecolor("#eeeeee")
    ax.imshow(
        display,
        cmap=cmap,
        norm=norm,
        extent=(left, right, bottom, top),
        origin="upper",
        interpolation="nearest",
    )
    ax.set_title(f"{product}\n{variable} · {relative_path.name}")
    if dataset.crs and dataset.crs.is_geographic:
        ax.set_xlabel("Longitud (°)")
        ax.set_ylabel("Latitud (°)")
    else:
        unit = getattr(dataset.crs, "linear_units", None) or "unidades CRS"
        ax.set_xlabel(f"Coordenada X ({unit})")
        ax.set_ylabel(f"Coordenada Y ({unit})")
    ax.set_aspect("equal")
    if legend:
        ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=True)
    ax.grid(color="#333333", alpha=0.15, linewidth=0.4)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def inspect_raster(path: Path, data_root: Path, results_dir: Path) -> dict[str, Any]:
    relative_path = path.relative_to(data_root)
    with rasterio.open(path) as dataset:
        tags = dataset.tags()
        band_tags = dataset.tags(1) if dataset.count else {}
        variable = _identify_variable(path, tags, band_tags)
        spec = PRODUCT_SPECS.get(variable)
        categories = spec["categories"] if spec else {}
        product = _identify_product(variable, path, tags)
        stats = _count_values(dataset, categories)

        try:
            geo_bounds = (
                list(transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21))
                if dataset.crs else None
            )
        except Exception:
            geo_bounds = None

        map_path = results_dir / f"{_safe_output_stem(relative_path)}_mapa.png"
        _make_map(dataset, relative_path, map_path, categories, stats, product, variable)
        transform = dataset.transform
        transform_bounds_native = list(array_bounds(dataset.height, dataset.width, transform))
        resolution = [abs(float(dataset.res[0])), abs(float(dataset.res[1]))]
        if dataset.crs and dataset.crs.is_geographic:
            units = ["degree", "degree"]
        elif dataset.crs:
            linear_unit = getattr(dataset.crs, "linear_units", None)
            units = [linear_unit, linear_unit] if linear_unit else None
        else:
            units = None
        return {
            "file": relative_path.as_posix(),
            "product": product,
            "variable": variable,
            "acquisition_time": _acquisition_times(path, tags),
            "metadata": {
                "driver": dataset.driver,
                "width_pixels": dataset.width,
                "height_pixels": dataset.height,
                "band_count": dataset.count,
                "band_types": list(dataset.dtypes),
                "resolution": resolution,
                "resolution_units": units,
                "crs": dataset.crs.to_string() if dataset.crs else None,
                "extent_native_left_bottom_right_top": transform_bounds_native,
                "extent_wgs84_west_south_east_north": geo_bounds,
                "nodata_value": dataset.nodata,
                "transform": list(transform),
                "dataset_tags": tags,
                "band_1_tags": band_tags,
            },
            "statistics": stats,
            "classification_specification": spec["specification"] if spec else None,
            "color_source": spec["color_source"] if spec else None,
            "map_png": map_path.relative_to(results_dir.parent).as_posix(),
        }


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    data_root = project_dir / "datos_opera"
    results_dir = data_root / "resultados"
    if not data_root.is_dir():
        print(f"No existe el directorio de datos: {data_root}", file=sys.stderr)
        return 2

    files = sorted(
        path for path in data_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
    )
    if not files:
        print(f"No se encontraron GeoTIFF en {data_root}", file=sys.stderr)
        return 1

    results_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_directory": "datos_opera",
        "files_processed": [],
        "errors": [],
    }

    print(f"GeoTIFF encontrados: {len(files)}")
    for path in files:
        try:
            result = inspect_raster(path, data_root, results_dir)
            report["files_processed"].append(result)
            stats = result["statistics"]
            meta = result["metadata"]
            print(
                f"\n{result['file']}\n"
                f"  Producto/capa: {result['product']} / {result['variable']}\n"
                f"  Raster: {meta['width_pixels']}×{meta['height_pixels']}, "
                f"{meta['resolution']} {meta['resolution_units']}, {meta['crs']}\n"
                f"  Bandas/tipos: {meta['band_count']} / {meta['band_types']}; "
                f"NoData={meta['nodata_value']}\n"
                f"  Extensión WGS84 (O,S,E,N): {meta['extent_wgs84_west_south_east_north']}\n"
                f"  Adquisición: {', '.join(result['acquisition_time']['timestamps_utc']) or 'no disponible'}\n"
                f"  Píxeles: total={stats['total_pixels']:,}; válidos={stats['valid_class_pixels']:,}; "
                f"enmascarados={stats['masked_class_pixels']:,}; sin datos={stats['nodata_pixels']:,}; "
                f"no documentados={stats['unknown_code_pixels']:,}"
            )
            for row in stats["categories"]:
                if row["count"]:
                    pct_valid = row["percent_of_valid_classes"]
                    pct_text = f"; {pct_valid:.3f}% de clases válidas" if pct_valid is not None else ""
                    print(
                        f"    {row['code']:>3} {row['label']}: {row['count']:,} "
                        f"({row['percent_of_all_pixels']:.3f}% total{pct_text})"
                    )
            print(f"  Mapa: {result['map_png']}")
        except Exception as error:
            report["errors"].append({
                "file": path.relative_to(data_root).as_posix(),
                "error_type": type(error).__name__,
                "error": str(error),
            })
            print(f"\nERROR {path.relative_to(data_root)}: {type(error).__name__}: {error}", file=sys.stderr)

    report_path = results_dir / "reporte_inspeccion_opera.json"
    temporary_path = report_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(report_path)
    print(f"\nReporte JSON: {report_path.relative_to(project_dir)}")
    print(f"Archivos procesados: {len(report['files_processed'])}/{len(files)}; errores: {len(report['errors'])}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
