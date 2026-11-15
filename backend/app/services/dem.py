"""Copernicus DEM GLO-90 (90 m) COG tiles from the public AWS bucket.

Tiles are 1x1 degree, named by the floor of the lower-left corner (e.g. N19 W100).
Reads go through GDAL /vsicurl/ so only headers and needed blocks travel.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import httpx
import numpy as np
import rasterio
from rasterio.env import Env
from rasterio.errors import RasterioError
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds

BASE_URL = "https://copernicus-dem-90m.s3.amazonaws.com"
_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_TIMEOUT": "60",
}
_ABSENT_MARKERS = ("404", "No such file or directory", "does not exist")


class DemTileMissingError(Exception):
    """The tile does not exist in the bucket (open ocean)."""


def tile_name(lat: float, lon: float) -> str:
    if not (-90 <= lat < 90 and -180 <= lon < 180):
        raise ValueError("lat must be in [-90, 90) and lon in [-180, 180)")
    la, lo = math.floor(lat), math.floor(lon)
    ns = f"{'N' if la >= 0 else 'S'}{abs(la):02d}"
    ew = f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}"
    return f"Copernicus_DSM_COG_30_{ns}_00_{ew}_00_DEM"


def tile_url(lat: float, lon: float) -> str:
    name = tile_name(lat, lon)
    return f"{BASE_URL}/{name}/{name}.tif"


def _gdal_path(url: str) -> str:
    return f"/vsicurl/{url}" if url.startswith("http") else url


def _open(url: str):
    try:
        return rasterio.open(_gdal_path(url))
    except RasterioError as error:
        if any(m in str(error) for m in _ABSENT_MARKERS):
            raise DemTileMissingError(f"No Copernicus DEM tile at {url} (likely open ocean)") from error
        raise


def metadata(lat: float, lon: float) -> dict[str, Any]:
    url = tile_url(lat, lon)
    with Env(**_GDAL_ENV), _open(url) as src:
        overviews = src.overviews(1)
        stats: dict[str, Any] = {"min": None, "max": None}
        if overviews:
            f = overviews[-1]
            arr = src.read(1, out_shape=(max(1, src.height // f), max(1, src.width // f)), masked=True)
            if arr.count():
                stats = {"min": float(arr.min()), "max": float(arr.max()), "stats_overview_factor": f}
        return {
            "url": url,
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": src.dtypes[0],
            "crs": src.crs.to_string() if src.crs else None,
            "bounds": list(src.bounds),
            "transform": list(src.transform)[:6],
            "res": list(src.res),
            "nodata": src.nodata,
            "compress": src.compression.value if src.compression else None,
            "overviews": overviews,
            "tags": src.tags(),
            **stats,
        }


def stream_file(lat: float, lon: float) -> tuple[str, Iterator[bytes]]:
    """Proxy the tile bytes. Returns (filename, chunk iterator); raises DemTileMissingError on 404."""
    url = tile_url(lat, lon)
    filename = url.rsplit("/", 1)[1]
    if not url.startswith("http"):
        def local() -> Iterator[bytes]:
            with open(url, "rb") as fh:
                yield from iter(lambda: fh.read(1 << 16), b"")
        try:
            open(url, "rb").close()
        except FileNotFoundError as error:
            raise DemTileMissingError(f"No Copernicus DEM tile at {url}") from error
        return filename, local()
    client = httpx.Client(timeout=60)
    resp = client.send(client.build_request("GET", url), stream=True)
    if resp.status_code in (403, 404):
        resp.close()
        client.close()
        raise DemTileMissingError(f"No Copernicus DEM tile at {url} (likely open ocean)")
    resp.raise_for_status()

    def chunks() -> Iterator[bytes]:
        try:
            yield from resp.iter_bytes(1 << 16)
        finally:
            resp.close()
            client.close()

    return filename, chunks()


def crop(bbox: tuple[float, float, float, float]) -> tuple[str, bytes]:
    minx, miny, maxx, maxy = bbox
    if not (minx < maxx and miny < maxy):
        raise ValueError("bbox must be minx,miny,maxx,maxy with min < max")
    if math.floor(minx) != math.floor(maxx - 1e-9) or math.floor(miny) != math.floor(maxy - 1e-9):
        raise ValueError("bbox must lie within a single 1x1 degree tile")
    url = tile_url(miny, minx)
    with Env(**_GDAL_ENV), _open(url) as src:
        win = from_bounds(minx, miny, maxx, maxy, src.transform).round_offsets().round_lengths()
        data = src.read(window=win)
        profile = src.profile.copy()
        profile.update(
            width=data.shape[2], height=data.shape[1], transform=src.window_transform(win),
            driver="GTiff", compress="deflate", tiled=False,
        )
        for key in ("blockxsize", "blockysize", "interleave"):
            profile.pop(key, None)
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(data)
        payload = mem.read()
    name = tile_name(miny, minx) + f"_crop_{minx:.4f}_{miny:.4f}_{maxx:.4f}_{maxy:.4f}.tif"
    return name, payload
