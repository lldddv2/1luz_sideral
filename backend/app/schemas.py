from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

TIFF_SUFFIXES = {".tif", ".tiff"}


class AOIRequest(BaseModel):
    geometry: dict[str, Any] = Field(
        description="GeoJSON Polygon or MultiPolygon (or Feature wrapping one), WGS84 lon/lat"
    )
    start: str = Field(description="ISO-8601 with timezone, e.g. 2025-08-01T00:00:00Z")
    end: str = Field(description="ISO-8601 with timezone, later than start")


class Product(BaseModel):
    product_id: str
    producer_granule_id: str
    collection_short_name: str
    product_type: str
    acquisition_start: str | None = None
    acquisition_stop: str | None = None
    geometry: dict[str, Any]
    size_mb_cmr: float | None = None
    estimated_size_bytes: int | None = None
    variables: list[dict[str, str]] = Field(default_factory=list)


class SearchResponse(BaseModel):
    inventory_id: str
    products: list[Product]


class JobCreate(BaseModel):
    inventory_id: str
    product_ids: list[str] = Field(min_length=1)
    variables: list[str] = Field(min_length=1)
    output_crs: str | None = None


class Job(BaseModel):
    id: str
    state: Literal["queued", "running", "done", "failed"]
    request: JobCreate
    # One entry per product, as returned by NisarExtractor.extract (see its "state" key).
    results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    created_at: str
    updated_at: str

    def output_paths(self) -> list[Path]:
        """GeoTIFFs recorded in results: each output, then its local masked copy when present.

        Index i of GET /api/jobs/{id}/files/{i} is element i of this list. Only paths the
        extractor recorded are listed; client input never becomes a path.
        """
        paths: list[Path] = []
        for result in self.results:
            for output in result.get("outputs") or []:
                for key in ("path", "masked_path"):
                    value = output.get(key)
                    if value and Path(value).suffix.lower() in TIFF_SUFFIXES:
                        paths.append(Path(value))
        return paths

    @computed_field
    @property
    def files(self) -> list[str]:
        """File names in download order; the UI links each one to /api/jobs/{id}/files/{index}."""
        return [path.name for path in self.output_paths()]


class EstimateRequest(BaseModel):
    geometry: dict[str, Any] = Field(
        description="GeoJSON Polygon or MultiPolygon (or Feature wrapping one), WGS84 lon/lat"
    )
    variables: int = Field(default=1, ge=1, description="GeoTIFF variables per product")
    products: int = Field(default=1, ge=1, description="Products to size; ignored when inventory_id is set")
    spacing_m: float = Field(default=10.0, gt=0, description="Output pixel spacing in metres")
    bytes_per_pixel: int = Field(default=4, ge=1, description="4 for float32")
    inventory_id: str | None = Field(
        default=None, description="Saved inventory: its product count and full HDF5 sizes are used"
    )


class EstimateExtent(BaseModel):
    width: float
    height: float


class EstimatePixels(BaseModel):
    width: int
    height: int
    total: int = Field(description="Pixels across all output GeoTIFFs")


class EstimateResponse(BaseModel):
    area_km2: float = Field(description="Geodesic WGS84 area of the AOI")
    bbox_km: EstimateExtent = Field(description="AOI bounding box extent in UTM, km")
    pixels: EstimatePixels
    per_file_bytes: int
    total_bytes: int
    human: str = Field(description="total_bytes in binary units, e.g. 34.8 KB")
    assumptions: str
    full_granules_bytes: int | None = Field(
        default=None, description="Sum of CMR estimated_size_bytes (full HDF5) over inventory products"
    )
