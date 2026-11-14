"""Benchmark 1: ASF discovery latency and temporal availability by AOI size."""

from __future__ import annotations

from common import OUT, save, square_bbox, timer

from nisar_extractor import ExtractionConfig, NisarExtractor

START = "2025-08-01T00:00:00Z"
STOP = "2026-11-14T23:59:59Z"


def main() -> None:
    results = []
    cfg = ExtractionConfig(output_dir=str(OUT), max_products=200)
    with NisarExtractor(cfg) as ex:
        for side_km in (1.5, 5, 10, 20):
            region = ex.bbox(square_bbox(side_km))
            r = {"side_km": side_km, "area_km2": round(region.area_km2, 2)}
            try:
                with timer(r, "search_s"):
                    inv = ex.discover(
                        region,
                        start=START,
                        stop=STOP,
                        product_type="GCOV",
                        production_configuration="PR",
                        max_results=100,
                        inventory_path=OUT / f"inventory_{side_km}km.json",
                    )
                prods = inv.products
                dates = sorted({(p.acquisition_start or "")[:10] for p in prods})
                sizes = [p.size_mb_cmr or 0 for p in prods]
                r.update(
                    n_products=len(prods),
                    n_dates=len(dates),
                    first_date=dates[0] if dates else None,
                    last_date=dates[-1] if dates else None,
                    full_granule_mb_avg=round(sum(sizes) / len(sizes), 1) if sizes else None,
                    full_granule_mb_total=round(sum(sizes), 1),
                    n_variables=len(prods[0].variables or prods[0].collection_variables) if prods else 0,
                )
            except Exception as e:  # noqa: BLE001
                r["error"] = f"{type(e).__name__}: {e}"
            print(r, flush=True)
            results.append(r)
    save("bench_search.json", results)


if __name__ == "__main__":
    main()
