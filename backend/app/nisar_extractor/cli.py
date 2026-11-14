from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import ExtractionConfig
from .service import NisarExtractor


def _region_from_args(args, extractor: NisarExtractor):
    selected = sum(bool(getattr(args, name, None)) for name in ("bbox", "geojson", "wkt"))
    if selected != 1:
        raise ValueError("Provide exactly one of --bbox, --geojson, or --wkt")
    if args.bbox:
        values = [float(value) for value in args.bbox.split(",")]
        return extractor.bbox(values)
    if args.geojson:
        return extractor.geojson(args.geojson)
    return extractor.wkt(args.wkt)


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default="nisar_output")
    parser.add_argument("--max-area-km2", type=float, default=500_000.0)
    parser.add_argument("--max-products", type=int, default=100)
    parser.add_argument("--max-output-mib", type=float, default=64.0)
    parser.add_argument("--max-concurrent", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--retry-backoff", type=float, default=2.0)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--read-timeout", type=float, default=90.0)
    parser.add_argument("--job-timeout", type=float, default=1200.0)
    parser.add_argument("--no-force-ipv4", action="store_true")
    parser.add_argument("--overwrite", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nisar-extract",
        description="Discover NISAR products with ASF and extract selected variables with Harmony.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search and save an inventory; does not download data")
    _add_config(search)
    region = search.add_mutually_exclusive_group(required=True)
    region.add_argument("--bbox", help="W,S,E,N longitude/latitude degrees")
    region.add_argument("--geojson", help="GeoJSON Polygon/MultiPolygon or Feature file")
    region.add_argument("--wkt", help="WKT Polygon or MultiPolygon in lon/lat")
    search.add_argument("--start", required=True, help="ISO-8601 acquisition start time")
    search.add_argument("--stop", required=True, help="ISO-8601 acquisition stop time")
    search.add_argument("--product", default="GCOV", choices=["GCOV", "GUNW", "GOFF", "SME2"])
    search.add_argument("--production-configuration", default="PR", choices=["PR", "UR", "OD"])
    search.add_argument("--max-results", type=int, default=10)
    search.add_argument("--inventory", default="nisar_inventory.json")

    extract = subparsers.add_parser("extract", help="Extract explicitly selected inventory products")
    _add_config(extract)
    extract.add_argument("--inventory", required=True)
    extract.add_argument("--product-id", action="append", required=True, help="ASF product/file ID; repeat per product")
    extract.add_argument("--variables", required=True, help="Comma-separated exact Harmony variable names or UMM-Var IDs")
    extract.add_argument("--output-crs", help="Output CRS, e.g. EPSG:4326 (only if service advertises it)")
    extract.add_argument("--reuse-job-id", help="Resume/reuse an existing completed Harmony job, for one product")

    jobs = subparsers.add_parser("jobs", help="List local Harmony job ledger entries")
    _add_config(jobs)
    jobs.add_argument("--limit", type=int, default=100)

    return parser


def _config(args) -> ExtractionConfig:
    return ExtractionConfig(
        output_dir=args.output_dir,
        max_area_km2=args.max_area_km2,
        max_products=args.max_products,
        max_output_bytes=int(args.max_output_mib * 1024 * 1024),
        max_concurrent=args.max_concurrent,
        max_attempts=args.max_attempts,
        retry_backoff_seconds=args.retry_backoff,
        connect_timeout_seconds=args.connect_timeout,
        read_timeout_seconds=args.read_timeout,
        job_timeout_seconds=args.job_timeout,
        force_ipv4=not args.no_force_ipv4,
        overwrite=args.overwrite,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        extractor = NisarExtractor(_config(args))
        if args.command == "search":
            region = _region_from_args(args, extractor)
            inventory = extractor.discover(
                region,
                start=args.start,
                stop=args.stop,
                product_type=args.product,
                production_configuration=args.production_configuration,
                max_results=args.max_results,
                inventory_path=args.inventory,
            )
            print(f"Inventario guardado: {args.inventory}")
            print(json.dumps(inventory.to_dict(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "extract":
            inventory = extractor.load_inventory(args.inventory)
            variables = [v.strip() for v in args.variables.split(",") if v.strip()]
            results = extractor.extract(
                inventory,
                product_ids=args.product_id,
                variables=variables,
                output_crs=args.output_crs,
                reuse_job_id=args.reuse_job_id,
            )
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return 0 if all(result["state"] == "downloaded" for result in results) else 1
        if args.command == "jobs":
            print(json.dumps(extractor.jobs(args.limit), indent=2, ensure_ascii=False))
            return 0
    except Exception as error:
        from .harmony_service import safe_error

        print(f"Error: {type(error).__name__}: {safe_error(error)}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
