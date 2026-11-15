from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class Region:
    geometry: BaseGeometry
    source_kind: str
    is_bbox: bool = False

    @property
    def wkt(self) -> str:
        return self.geometry.wkt

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return tuple(float(v) for v in self.geometry.bounds)

    @property
    def area_km2(self) -> float:
        from pyproj import Geod

        area, _ = Geod(ellps="WGS84").geometry_area_perimeter(self.geometry)
        return abs(float(area)) / 1_000_000


@dataclass
class ProductRecord:
    product_id: str
    producer_granule_id: str
    cmr_granule_id: str
    collection_short_name: str
    collection_concept_id: str
    product_type: str
    processing_configuration: str | None
    acquisition_start: str | None
    acquisition_stop: str | None
    geometry: dict[str, Any]
    size_mb_cmr: float | None
    estimated_size_bytes: int | None
    data_url: str | None = None
    variables: list[dict[str, str]] = field(default_factory=list)
    collection_variables: list[dict[str, str]] = field(default_factory=list)
    variables_scope: str = "collection capabilities; granule contents are verified by Harmony"
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProductRecord":
        return cls(**value)


@dataclass
class Inventory:
    query: dict[str, Any]
    region: dict[str, Any]
    products: list[ProductRecord]
    queried_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "query": self.query,
            "region": self.region,
            "queried_at_utc": self.queried_at_utc,
            "products": [p.to_dict() for p in self.products],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Inventory":
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported inventory schema_version")
        return cls(
            query=value["query"],
            region=value["region"],
            products=[ProductRecord.from_dict(x) for x in value["products"]],
            queried_at_utc=value["queried_at_utc"],
        )


@dataclass(frozen=True)
class ExtractionConfig:
    output_dir: str = "nisar_output"
    max_area_km2: float = 500_000.0
    max_products: int = 100
    # Bounds one discovery search; kept apart from max_products, which bounds extraction.
    max_discover_results: int = 200
    max_output_bytes: int = 64 * 1024 * 1024
    max_concurrent: int = 2
    max_attempts: int = 2
    retry_backoff_seconds: float = 2.0
    connect_timeout_seconds: float = 15.0
    read_timeout_seconds: float = 90.0
    job_timeout_seconds: float = 1200.0
    force_ipv4: bool = True
    overwrite: bool = False

    def __post_init__(self) -> None:
        positive = {
            "max_area_km2": self.max_area_km2,
            "max_products": self.max_products,
            "max_discover_results": self.max_discover_results,
            "max_output_bytes": self.max_output_bytes,
            "max_concurrent": self.max_concurrent,
            "max_attempts": self.max_attempts,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "read_timeout_seconds": self.read_timeout_seconds,
            "job_timeout_seconds": self.job_timeout_seconds,
        }
        for key, value in positive.items():
            if value <= 0:
                raise ValueError(f"{key} must be greater than zero")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")


def parse_utc(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone (prefer UTC/Z)")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
