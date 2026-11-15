"""Administrative region search (countries, states, municipalities) proxied to OSM Nominatim.

Nominatim usage policy: at most 1 request per second and a valid User-Agent. Results are cached
in memory so repeated queries (typing, re-opening the list) do not hit the service again.
"""

import threading
import time
from collections import OrderedDict

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from shapely.geometry import mapping, shape

router = APIRouter(prefix="/regions", tags=["regions"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "1luz-sideral/0.1"
MIN_INTERVAL_S = 1.0
CACHE_SIZE = 256

# Nominatim addresstype -> Spanish label and priority (lower = more administrative).
TYPE_LABELS: dict[str, tuple[str, int]] = {
    "country": ("País", 0),
    "state": ("Departamento / Estado", 1),
    "province": ("Provincia", 1),
    "region": ("Región", 1),
    "state_district": ("Distrito", 2),
    "county": ("Municipio / Condado", 2),
    "municipality": ("Municipio", 2),
    "city": ("Ciudad", 3),
    "town": ("Pueblo", 3),
    "village": ("Vereda / Aldea", 4),
    "city_district": ("Localidad", 4),
    "suburb": ("Barrio", 5),
}
ADMIN_CLASSES = {"boundary", "place"}


class Region(BaseModel):
    id: str
    name: str
    label: str
    type: str  # Spanish label, e.g. "País"
    bbox: tuple[float, float, float, float]  # [west, south, east, north]
    geometry: dict | None  # simplified Polygon/MultiPolygon


_cache: OrderedDict[str, list[Region]] = OrderedDict()
_lock = threading.Lock()
_last_call = 0.0


def _fetch(q: str, viewbox: tuple[float, float, float, float] | None = None) -> list[dict]:
    """Calls Nominatim, waiting so calls are at least MIN_INTERVAL_S apart.

    With a viewbox (west, south, east, north), results are restricted to it (bounded=1).
    """
    params: dict = {
        "q": q,
        "format": "jsonv2",
        "polygon_geojson": 1,
        "polygon_threshold": 0.005,
        "limit": 10,
        "accept-language": "es",
    }
    if viewbox is not None:
        params["viewbox"] = ",".join(f"{v:.5f}" for v in viewbox)
        params["bounded"] = 1
    global _last_call
    with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        res = requests.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
    res.raise_for_status()
    return res.json()


def _simplify(geojson: dict | None) -> dict | None:
    """Simplifies proportionally to size (~0.3% of the bbox span) so countries stay small."""
    if not geojson or geojson.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    geom = shape(geojson)
    minx, miny, maxx, maxy = geom.bounds
    tol = max(maxx - minx, maxy - miny) * 0.003
    simple = geom.simplify(tol, preserve_topology=True) if tol > 0 else geom
    if simple.is_empty:
        simple = geom
    out = mapping(simple)

    def rnd(c):
        return [round(v, 4) for v in c] if isinstance(c[0], float | int) else [rnd(x) for x in c]

    return {"type": out["type"], "coordinates": rnd(out["coordinates"])}


def _to_region(item: dict) -> tuple[int, Region]:
    kind = item.get("addresstype") or item.get("type") or ""
    label, rank = TYPE_LABELS.get(kind, (kind.replace("_", " ").capitalize(), 9))
    if item.get("class") not in ADMIN_CLASSES:
        rank = 10
    s, n, w, e = (float(v) for v in item["boundingbox"])
    return rank, Region(
        id=str(item["place_id"]),
        name=item.get("name") or item["display_name"].split(",")[0],
        label=item["display_name"],
        type=label,
        bbox=(w, s, e, n),
        geometry=_simplify(item.get("geojson")),
    )


def _parse_viewbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """Parses "west,south,east,north"; None when absent."""
    if not raw:
        return None
    try:
        w, s, e, n = (float(v) for v in raw.split(","))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="viewbox must be west,south,east,north") from error
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise HTTPException(status_code=422, detail="viewbox out of range")
    return w, s, e, n


@router.get("", response_model=list[Region])
def search_regions(
    q: str = Query(..., min_length=2, max_length=120),
    viewbox: str | None = Query(None, description="west,south,east,north; limits results to this box"),
) -> list[Region]:
    box = _parse_viewbox(viewbox)
    text = " ".join(q.lower().split())
    key = text if box is None else f"{text}|{','.join(f'{v:.3f}' for v in box)}"
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    try:
        items = _fetch(text, box)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=f"Nominatim: {error}") from error
    ranked = [_to_region(it) for it in items]
    # Areas first (administrative before other places), Nominatim order kept within a rank.
    ranked.sort(key=lambda r: (r[1].geometry is None, r[0]))
    regions = [r for _, r in ranked]
    _cache[key] = regions
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return regions
