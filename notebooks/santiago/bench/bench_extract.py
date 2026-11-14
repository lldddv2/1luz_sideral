"""Benchmark 2: real Harmony extraction time/size vs AOI size, and parallel time series."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from shapely.geometry import box, mapping

from common import OUT, save, square_bbox, timer

from nisar_extractor import ExtractionConfig, Inventory, NisarExtractor, ProductRecord

TRACK = (91, 22, "ASCENDING")
VARS_ONE = ["/science/LSAR/GCOV/grids/frequencyA/HHHH"]
VARS_TWO = VARS_ONE + ["/science/LSAR/GCOV/grids/frequencyA/HVHV"]


def track_products() -> list[ProductRecord]:
    data = json.loads((OUT / "inventory_20km.json").read_text(encoding="utf-8"))
    prods = [ProductRecord.from_dict(p) for p in data["products"]]
    sel = [
        p for p in prods
        if (p.properties.get("pathNumber"), p.properties.get("frameNumber"), p.properties.get("flightDirection")) == TRACK
    ]
    return sorted(sel, key=lambda p: p.acquisition_start or "", reverse=True)


def inventory_for(side_km: float, products: list[ProductRecord]) -> Inventory:
    return Inventory(
        query={"benchmark": True},
        region={"geojson": mapping(box(*square_bbox(side_km))), "source_kind": "bbox", "is_bbox": True},
        products=products,
        queried_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def summarize(res: list[dict]) -> dict:
    files = [o for r in res for o in r.get("outputs", [])]
    return {
        "states": [r.get("state") for r in res],
        "errors": [r.get("error") for r in res if r.get("error")],
        "n_files": len(files),
        "bytes_total": sum(int(o.get("bytes", 0)) for o in files),
        "shapes": sorted({(o.get("raster") or {}).get("width", 0) for o in files}),
        "rasters": [o.get("raster") for o in files[:2]],
    }


def main() -> None:
    prods = track_products()
    print(f"track {TRACK}: {len(prods)} products", flush=True)
    results = {"area_scaling": [], "time_series": None}

    # A) one product, one variable, growing AOI
    newest = prods[0]
    for side_km in (1.5, 5, 10, 20):
        cfg = ExtractionConfig(
            output_dir=str(OUT / f"extract_area_{side_km}km"),
            max_output_bytes=512 * 1024 * 1024,
            max_concurrent=1,
        )
        r = {"side_km": side_km, "product": newest.product_id}
        with NisarExtractor(cfg) as ex, timer(r, "wall_s"):
            res = ex.extract(inventory_for(side_km, [newest]), product_ids=[newest.product_id], variables=VARS_ONE)
        r.update(summarize(res))
        print(r, flush=True)
        results["area_scaling"].append(r)
        save("bench_extract.json", results)

    # B) time series: 6 dates x 2 polarizations, 10 km AOI, in parallel
    series = prods[1:7]
    cfg = ExtractionConfig(
        output_dir=str(OUT / "extract_series_10km"),
        max_output_bytes=512 * 1024 * 1024,
        max_concurrent=6,
    )
    r = {"side_km": 10, "n_dates": len(series), "variables": VARS_TWO, "concurrency": 6}
    t0 = time.perf_counter()
    with NisarExtractor(cfg) as ex:
        res = ex.extract(inventory_for(10, series), product_ids=[p.product_id for p in series], variables=VARS_TWO)
    r["wall_s"] = round(time.perf_counter() - t0, 3)
    r.update(summarize(res))
    print(r, flush=True)
    results["time_series"] = r
    save("bench_extract.json", results)


if __name__ == "__main__":
    main()
