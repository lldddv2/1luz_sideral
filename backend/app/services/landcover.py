"""ESA WorldCover 2021 land cover (10 m, v200): class table, AOI statistics and class masks.

WorldCover ships as 3°×3° COG tiles named by lower-left corner (e.g. N39W108). Tiles are read
remotely with GDAL /vsicurl/. A tile missing from the bucket (open ocean) counts as nodata.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import threading
import warnings
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.env import Env
from rasterio.errors import NotGeoreferencedWarning, RasterioError
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import Affine, from_origin
from rasterio.windows import Window
from shapely.errors import ShapelyError
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

BASE_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
TILE_FILE = "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
NATIVE_RES = 1 / 12000  # degrees per pixel, about 10 m
NATIVE_RES_M = 10.0
TILE_DEG = 3
TILE_PX = round(TILE_DEG / NATIVE_RES)  # pixels per tile side
MAX_AREA_KM2 = 2_000_000.0  # sanity cap on the AOI bbox; large AOIs are decimated to STATS_MAX_PX, not refused
STATS_MAX_PX = 2048  # longest grid side used for statistics
CACHE_SIZE = 8
_EPS = 1e-6  # tolerance, in native pixels, for float coordinates
_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_HTTP_TIMEOUT": "60",
}
# A tile that does not exist: S3 answers 404 for ocean-only tiles; local paths say "No such file".
_ABSENT_MARKERS = ("HTTP response code: 404", "No such file or directory")

# WGS84 ellipsoid, for exact cell areas.
_A = 6_378_137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)


class LandcoverUnavailableError(RuntimeError):
    """A WorldCover tile exists but could not be read from the remote store."""


@dataclass(frozen=True)
class WorldCoverClass:
    code: int
    key: str
    name: str  # Spanish label
    name_en: str  # ESA legend label
    color: str  # ESA legend colour, #rrggbb; same as the palette embedded in each tile


CLASSES: tuple[WorldCoverClass, ...] = (
    WorldCoverClass(10, "tree", "Cubierta arbórea", "Tree cover", "#006400"),
    WorldCoverClass(20, "shrubland", "Matorral", "Shrubland", "#ffbb22"),
    WorldCoverClass(30, "grassland", "Pastizal", "Grassland", "#ffff4c"),
    WorldCoverClass(40, "cropland", "Cultivos", "Cropland", "#f096ff"),
    WorldCoverClass(50, "built_up", "Zona construida", "Built-up", "#fa0000"),
    WorldCoverClass(60, "bare", "Suelo desnudo o vegetación escasa", "Bare / sparse vegetation", "#b4b4b4"),
    WorldCoverClass(70, "snow_ice", "Nieve y hielo", "Snow and ice", "#f0f0f0"),
    WorldCoverClass(80, "water", "Cuerpos de agua permanentes", "Permanent water bodies", "#0064c8"),
    WorldCoverClass(90, "wetland", "Humedal herbáceo", "Herbaceous wetland", "#0096a0"),
    WorldCoverClass(95, "mangrove", "Manglar", "Mangroves", "#00cf75"),
    WorldCoverClass(100, "moss", "Musgo y liquen", "Moss and lichen", "#fae6a0"),
)
_BY_KEY = {cls.key: cls for cls in CLASSES}
_CODES = np.array([cls.code for cls in CLASSES], dtype=np.uint8)


def resolve_classes(keys: Iterable[str]) -> tuple[WorldCoverClass, ...]:
    """Classes named by key, in table order. No keys means every class."""
    wanted = list(keys)
    if not wanted:
        return CLASSES
    unknown = [key for key in wanted if key not in _BY_KEY]
    if unknown:
        raise ValueError(f"Unknown class key(s): {', '.join(unknown)}; see GET /api/landcover/classes")
    selected = set(wanted)
    return tuple(cls for cls in CLASSES if cls.key in selected)


def cell_area_km2(lat_top: Any, lat_bottom: Any, dlon_deg: float) -> np.ndarray:
    """Area in km² of lon/lat cells on the WGS84 ellipsoid. Latitudes may be arrays."""
    dlon = math.radians(dlon_deg)
    return np.abs(dlon * _A * _A * (_authalic(lat_top) - _authalic(lat_bottom)) / 2) / 1e6


def _authalic(lat_deg: Any) -> np.ndarray:
    sin = np.sin(np.radians(lat_deg))
    return (1 - _E2) * (sin / (1 - _E2 * sin * sin) - np.log((1 - _E * sin) / (1 + _E * sin)) / (2 * _E))


def parse_aoi(geometry: dict[str, Any]) -> BaseGeometry:
    """Validate client GeoJSON and the AOI size. Raises ValueError (422) before any remote read."""
    try:
        raw = geometry["geometry"] if geometry.get("type") == "Feature" else geometry
        aoi = shape(raw)
    except (AttributeError, KeyError, TypeError, ValueError, ShapelyError) as error:
        raise ValueError(f"Invalid GeoJSON geometry ({type(error).__name__}): {error}") from error
    if aoi.is_empty or aoi.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("AOI must be a GeoJSON Polygon or MultiPolygon")
    if not aoi.is_valid:
        raise ValueError("AOI geometry is invalid; repair it before requesting land cover")
    west, south, east, north = aoi.bounds
    if not all(math.isfinite(value) for value in aoi.bounds):
        raise ValueError("AOI coordinates must be finite numbers")
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise ValueError("AOI must use WGS84 longitude/latitude coordinates")
    area = float(cell_area_km2(north, south, east - west))
    if area > MAX_AREA_KM2:
        raise ValueError(f"AOI bounding box is {area:,.0f} km²; the limit is {MAX_AREA_KM2:,.0f} km²")
    return aoi


def tile_name(lat0: int, lon0: int) -> str:
    """WorldCover tile name from its lower-left corner, e.g. (39, -108) gives N39W108."""
    ns = "N" if lat0 >= 0 else "S"
    ew = "E" if lon0 >= 0 else "W"
    return f"{ns}{abs(lat0):02d}{ew}{abs(lon0):03d}"


@dataclass(frozen=True)
class Grid:
    codes: np.ndarray  # uint8 WorldCover codes; 0 outside the AOI, where a tile is absent or has no data
    inside: np.ndarray  # bool, True where the pixel centre lies inside the AOI
    transform: Affine  # north-west corner and pixel size, in degrees
    factor: int  # native pixels per grid pixel side; 1 is native 10 m

    def bounds(self) -> list[list[float]]:
        """Corners as MapLibre image source coordinates: NW, NE, SE, SW."""
        rows, cols = self.codes.shape
        west, north = self.transform.c, self.transform.f
        east = west + cols * self.transform.a
        south = north + rows * self.transform.e
        corners = [[west, north], [east, north], [east, south], [west, south]]
        return [[round(lon, 8), round(lat, 8)] for lon, lat in corners]


@dataclass(frozen=True)
class _Plan:
    row0: int
    row1: int
    col0: int
    col1: int
    factor: int


@lru_cache(maxsize=None)
def _divisors(n: int) -> tuple[int, ...]:
    small = [d for d in range(1, math.isqrt(n) + 1) if n % d == 0]
    return tuple(sorted({*small, *(n // d for d in small)}))


def _plan(west: float, south: float, east: float, north: float, max_px: int) -> _Plan:
    """Native-grid window over the AOI bbox, decimated by a divisor of TILE_PX so tiles stay aligned."""
    # The native grid is global: column c starts at lon -180 + c*NATIVE_RES, row r at lat 90 - r*NATIVE_RES.
    lo_c = math.floor((west + 180.0) / NATIVE_RES + _EPS)
    hi_c = max(math.ceil((east + 180.0) / NATIVE_RES - _EPS), lo_c + 1)
    lo_r = math.floor((90.0 - north) / NATIVE_RES + _EPS)
    hi_r = max(math.ceil((90.0 - south) / NATIVE_RES - _EPS), lo_r + 1)
    factor = TILE_PX
    for candidate in _divisors(TILE_PX):
        rows = -(-hi_r // candidate) - lo_r // candidate
        cols = -(-hi_c // candidate) - lo_c // candidate
        if max(rows, cols) <= max_px:
            factor = candidate
            break
    return _Plan(
        row0=lo_r // factor * factor,
        row1=-(-hi_r // factor) * factor,
        col0=lo_c // factor * factor,
        col1=-(-hi_c // factor) * factor,
        factor=factor,
    )


def _tile_reads(plan: _Plan):
    """Per tile: (name, window in tile pixels, output shape, output (row, col) offset)."""
    f = plan.factor
    for k in range(plan.row0 // TILE_PX, (plan.row1 - 1) // TILE_PX + 1):
        for j in range(plan.col0 // TILE_PX, (plan.col1 - 1) // TILE_PX + 1):
            tile_row, tile_col = k * TILE_PX, j * TILE_PX
            r_a, r_b = max(plan.row0, tile_row), min(plan.row1, tile_row + TILE_PX)
            c_a, c_b = max(plan.col0, tile_col), min(plan.col1, tile_col + TILE_PX)
            window = Window(c_a - tile_col, r_a - tile_row, c_b - c_a, r_b - r_a)
            out_shape = ((r_b - r_a) // f, (c_b - c_a) // f)
            offset = ((r_a - plan.row0) // f, (c_a - plan.col0) // f)
            name = tile_name(90 - TILE_DEG * (k + 1), -180 + TILE_DEG * j)
            yield name, window, out_shape, offset


def _tile_source(name: str) -> str:
    filename = TILE_FILE.format(tile=name)
    if BASE_URL.startswith("https://"):
        return f"/vsicurl/{BASE_URL}/{filename}"
    return os.path.join(BASE_URL, filename)


def _read_tile(name: str, window: Window, out_shape: tuple[int, int]) -> np.ndarray | None:
    """One tile window resampled to out_shape. None when the tile does not exist (open ocean)."""
    try:
        with rasterio.open(_tile_source(name)) as src:
            if not math.isclose(src.res[0], NATIVE_RES, rel_tol=1e-9):
                raise LandcoverUnavailableError(f"{name}: pixel size {src.res[0]} is not {NATIVE_RES}")
            return src.read(1, window=window, out_shape=out_shape, resampling=Resampling.nearest)
    except RasterioError as error:
        if any(marker in str(error) for marker in _ABSENT_MARKERS):
            return None
        raise LandcoverUnavailableError(f"WorldCover tile {name} unreadable: {error}") from error


def _read_grid(aoi: BaseGeometry, max_px: int) -> Grid:
    plan = _plan(*aoi.bounds, max_px)
    f = plan.factor
    rows, cols = (plan.row1 - plan.row0) // f, (plan.col1 - plan.col0) // f
    codes = np.zeros((rows, cols), dtype=np.uint8)
    with Env(**_GDAL_ENV):
        for name, window, out_shape, (y, x) in _tile_reads(plan):
            data = _read_tile(name, window, out_shape)
            if data is not None:
                codes[y : y + out_shape[0], x : x + out_shape[1]] = data
    pixel = f * NATIVE_RES
    transform = from_origin(plan.col0 * NATIVE_RES - 180.0, 90.0 - plan.row0 * NATIVE_RES, pixel, pixel)
    inside = geometry_mask([mapping(aoi)], out_shape=(rows, cols), transform=transform, invert=True)
    codes[~inside] = 0
    return Grid(codes=codes, inside=inside, transform=transform, factor=f)


_cache: OrderedDict[tuple[str, int], Grid] = OrderedDict()
_cache_lock = threading.Lock()


def read_window(geometry: dict[str, Any], max_px: int) -> Grid:
    """WorldCover grid over the AOI bbox, decimated so the longest side is at most max_px. Cached."""
    key = (hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest(), max_px)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
    grid = _read_grid(parse_aoi(geometry), max_px)
    with _cache_lock:
        _cache[key] = grid
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return grid


def _row_areas(grid: Grid) -> np.ndarray:
    """km² of one grid pixel in each row; every row has its own latitude band."""
    t = grid.transform
    tops = t.f + np.arange(grid.codes.shape[0]) * t.e
    return cell_area_km2(tops, tops + t.e, t.a)


def stats(geometry: dict[str, Any]) -> dict[str, Any]:
    """Per-class pixels, area and share of the AOI. Percent is of total_km2 (nodata excluded)."""
    grid = read_window(geometry, STATS_MAX_PX)
    areas = _row_areas(grid)
    valid = grid.inside & np.isin(grid.codes, _CODES)
    nodata = grid.inside & ~valid
    total = float(valid.sum(axis=1) @ areas)
    classes = []
    for cls in CLASSES:
        counts = (grid.inside & (grid.codes == cls.code)).sum(axis=1)
        area = float(counts @ areas)
        classes.append(
            {
                "code": cls.code,
                "key": cls.key,
                "name": cls.name,
                "name_en": cls.name_en,
                "color": cls.color,
                # Native-pixel estimate: a decimated pixel stands for factor x factor native pixels.
                "pixels": int(counts.sum()) * grid.factor**2,
                "area_km2": round(area, 6),
                "percent": round(100 * area / total, 4) if total > 0 else 0.0,
            }
        )
    return {
        "total_km2": round(total, 6),
        "nodata_km2": round(float(nodata.sum(axis=1) @ areas), 6),
        "resolution_m": NATIVE_RES_M * grid.factor,
        "classes": classes,
    }


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _png(rgba: np.ndarray) -> bytes:
    """RGBA PNG from GDAL's PNG driver, written to memory."""
    rows, cols = rgba.shape[:2]
    bands = np.ascontiguousarray(np.moveaxis(rgba, -1, 0))
    with warnings.catch_warnings(), MemoryFile() as memfile:
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with memfile.open(driver="PNG", width=cols, height=rows, count=4, dtype="uint8") as dst:
            dst.write(bands)
        return memfile.read()


def mask(geometry: dict[str, Any], classes: Iterable[str], max_px: int) -> dict[str, Any]:
    """RGBA PNG of the chosen classes. Other, nodata and outside-AOI pixels are transparent."""
    selected = resolve_classes(classes)
    grid = read_window(geometry, max_px)
    rgba = np.zeros((*grid.codes.shape, 4), dtype=np.uint8)
    for cls in selected:
        rgba[grid.inside & (grid.codes == cls.code)] = (*_rgb(cls.color), 255)
    rows, cols = grid.codes.shape
    return {
        "bounds": grid.bounds(),
        "width": cols,
        "height": rows,
        "png_base64": base64.b64encode(_png(rgba)).decode("ascii"),
    }
