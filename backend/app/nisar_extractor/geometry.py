from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely import make_valid, wkt
from shapely.geometry import MultiPolygon, box, shape
from shapely.geometry.base import BaseGeometry

from .models import Region


def _validate_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.is_empty:
        raise ValueError("Region geometry cannot be empty")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("NISAR extraction accepts Polygon or MultiPolygon regions")
    if not geometry.is_valid:
        # Self-intersecting outlines (e.g. simplified river shapes) are repaired, keeping only polygonal parts.
        repaired = make_valid(geometry)
        parts = getattr(repaired, "geoms", [repaired])
        polys = [p for g in parts for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]
        if not polys:
            raise ValueError("Region geometry is invalid and could not be repaired")
        geometry = polys[0] if len(polys) == 1 else MultiPolygon(polys)
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
    minx, miny, maxx, maxy = geometry.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise ValueError("Region must use WGS84 longitude/latitude coordinates")
    return geometry


def from_bbox(values: tuple[float, float, float, float] | list[float]) -> Region:
    if len(values) != 4:
        raise ValueError("BBOX format is west,south,east,north")
    west, south, east, north = map(float, values)
    if west >= east or south >= north:
        raise ValueError("BBOX must have west < east and south < north")
    geometry = _validate_geometry(box(west, south, east, north))
    return Region(geometry=geometry, source_kind="bbox", is_bbox=True)


def from_wkt(value: str) -> Region:
    geometry = _validate_geometry(wkt.loads(value))
    return Region(geometry=geometry, source_kind="wkt", is_bbox=False)


def from_geojson(value: dict[str, Any] | str | Path) -> Region:
    if isinstance(value, (str, Path)):
        raw = json.loads(Path(value).read_text())
    else:
        raw = value
    if raw.get("type") == "Feature":
        raw = raw["geometry"]
    elif raw.get("type") == "FeatureCollection":
        geometries = [shape(feature["geometry"]) for feature in raw.get("features", [])]
        if not geometries:
            raise ValueError("GeoJSON FeatureCollection is empty")
        merged = geometries[0]
        for geom in geometries[1:]:
            merged = merged.union(geom)
        raw = merged.__geo_interface__
    geometry = _validate_geometry(shape(raw))
    return Region(geometry=geometry, source_kind="geojson", is_bbox=False)


def region_to_record(region: Region) -> dict[str, Any]:
    return {
        "source_kind": region.source_kind,
        "is_bbox": region.is_bbox,
        "wkt": region.wkt,
        "geojson": region.geometry.__geo_interface__,
        "bounds_wsen": list(region.bounds),
        "area_km2_wgs84_geodesic": region.area_km2,
    }


def aoi_polygon_for_inventory(region_record: dict[str, Any]) -> BaseGeometry:
    return _validate_geometry(shape(region_record["geojson"]))
