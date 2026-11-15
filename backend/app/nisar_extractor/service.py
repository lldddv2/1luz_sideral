from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from .catalog import AsfCatalog
from .geometry import from_bbox, from_geojson, from_wkt
from .harmony_service import HarmonyRunner
from .models import ExtractionConfig, Inventory, ProductRecord, Region
from .network import configure_ipv4
from .store import JobStore


class NisarExtractor:
    """ASF discovery plus capability-checked, bounded Harmony extraction."""

    def __init__(
        self,
        config: ExtractionConfig | None = None,
        *,
        earthdata_auth: tuple[str, str] | None = None,
    ):
        self.config = config or ExtractionConfig()
        configure_ipv4(self.config.force_ipv4)
        self.catalog = AsfCatalog(
            timeout=(self.config.connect_timeout_seconds, self.config.read_timeout_seconds),
            retries=self.config.max_attempts,
        )
        self.runner = HarmonyRunner(self.config, self.catalog, earthdata_auth=earthdata_auth)
        self.store = JobStore(Path(self.config.output_dir) / ".nisar-extractor-jobs.sqlite3")

    def close(self) -> None:
        self.catalog.close()

    def __enter__(self) -> "NisarExtractor":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @staticmethod
    def bbox(values: tuple[float, float, float, float] | list[float]) -> Region:
        return from_bbox(values)

    @staticmethod
    def geojson(value: dict[str, Any] | str | Path) -> Region:
        return from_geojson(value)

    @staticmethod
    def wkt(value: str) -> Region:
        return from_wkt(value)

    def discover(
        self,
        region: Region,
        *,
        start: str | None,
        stop: str | None,
        product_type: str = "GCOV",
        production_configuration: str | None = "PR",
        max_results: int = 10,
        inventory_path: str | Path | None = None,
    ) -> Inventory:
        if region.area_km2 > self.config.max_area_km2:
            raise ValueError(
                f"AOI {region.area_km2:.2f} km² exceeds configured limit "
                f"{self.config.max_area_km2:.2f} km²"
            )
        if max_results > self.config.max_discover_results:
            raise ValueError(
                f"max_results={max_results} exceeds configured "
                f"max_discover_results={self.config.max_discover_results}"
            )
        inventory = self.catalog.discover(
            region,
            start=start,
            stop=stop,
            product_type=product_type,
            production_configuration=production_configuration,
            max_results=max_results,
        )
        if inventory_path:
            path = Path(inventory_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_text(json.dumps(inventory.to_dict(), indent=2, sort_keys=True) + "\n")
            temp.replace(path)
        return inventory

    def load_inventory(self, path: str | Path) -> Inventory:
        return Inventory.from_dict(json.loads(Path(path).read_text()))

    def extract(
        self,
        inventory: Inventory,
        *,
        product_ids: list[str],
        variables: list[str],
        output_crs: str | None = None,
        reuse_job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not product_ids:
            raise ValueError("Select at least one product explicitly; extraction is never implicit")
        unique_ids = list(dict.fromkeys(product_ids))
        if len(unique_ids) != len(product_ids):
            raise ValueError("Duplicate product IDs were provided")
        if len(unique_ids) > self.config.max_products:
            raise ValueError("Selected product count exceeds configured max_products")
        if len(unique_ids) > 1 and reuse_job_id:
            raise ValueError("A single --reuse-job-id can only be used with one selected product")
        if not variables:
            raise ValueError("Select at least one scientific variable explicitly")

        product_by_id = {product.product_id: product for product in inventory.products}
        missing = [product_id for product_id in unique_ids if product_id not in product_by_id]
        if missing:
            raise ValueError(f"Selected IDs are not in this inventory: {missing}")
        region = Region(
            geometry=shape(inventory.region["geojson"]),
            source_kind=inventory.region["source_kind"],
            is_bbox=inventory.region["is_bbox"],
        )
        if region.area_km2 > self.config.max_area_km2:
            raise ValueError("Inventory AOI exceeds this extractor's configured area limit")

        product_records = [product_by_id[product_id] for product_id in unique_ids]
        results: list[dict[str, Any] | None] = [None] * len(product_records)

        def run_one(index: int, product: ProductRecord) -> dict[str, Any]:
            try:
                return self.runner.execute(
                    product,
                    region,
                    variables,
                    output_crs=output_crs,
                    store=self.store,
                    reuse_job_id=reuse_job_id,
                )
            except Exception as error:
                return {
                    "product_id": product.product_id,
                    "state": "error",
                    "error_type": type(error).__name__,
                    "error": self._safe_error(error),
                }

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.config.max_concurrent, len(product_records))
        ) as pool:
            futures = {
                pool.submit(run_one, index, product): index
                for index, product in enumerate(product_records)
            }
            for future in concurrent.futures.as_completed(futures):
                results[futures[future]] = future.result()
        return [r for r in results if r is not None]

    @staticmethod
    def _safe_error(error: Exception) -> str:
        from .harmony_service import safe_error

        return safe_error(error)

    def jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list(limit)
