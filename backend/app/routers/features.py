"""Global catalog of named natural features (deserts, wetlands, glaciers, ...)."""

import json
import unicodedata
from functools import cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from shapely.geometry import shape
from shapely.prepared import prep

router = APIRouter(prefix="/features", tags=["features"])

DATA = Path(__file__).resolve().parents[1] / "data" / "features.json"

# Category key -> Spanish label and search words (Spanish and English, accent-free, lowercase).
CATEGORIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "desert": ("Desierto", ("desierto", "desiertos", "desert", "deserts", "arido", "dunas", "erg")),
    "wetland": ("Humedal", ("humedal", "humedales", "wetland", "wetlands", "pantano", "pantanos", "cienaga", "delta", "deltas", "marisma")),
    "glacier": ("Glaciar", ("glaciar", "glaciares", "glacier", "glaciers", "hielo", "ice", "icefield", "nieve")),
    "forest": ("Bosque", ("bosque", "bosques", "forest", "forests", "taiga")),
    "jungle": ("Selva", ("selva", "selvas", "jungla", "jungle", "rainforest", "selva tropical")),
    "mangrove": ("Manglar", ("manglar", "manglares", "mangrove", "mangroves")),
    "tundra": ("Tundra", ("tundra", "tundras")),
    "volcano": ("Volcán", ("volcan", "volcanes", "volcano", "volcanoes")),
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip()


@cache
def _catalog() -> list[dict]:
    items = json.loads(DATA.read_text(encoding="utf-8"))
    for item in items:
        item["category_name"] = CATEGORIES[item["category"]][0]
    return items


@cache
def _shapes() -> dict[str, object]:
    return {i["id"]: shape(i["geometry"]) for i in _catalog()}


def _light(items: list[dict]) -> list[dict]:
    """List responses leave the outline out; GET /features/{id} has it."""
    return [{k: v for k, v in i.items() if k != "geometry"} for i in items]


def category_of(q: str) -> str | None:
    nq = _norm(q)
    for key, (_, words) in CATEGORIES.items():
        if nq in words:
            return key
    return None


def find(q: str = "", category: str | None = None, limit: int = 300) -> list[dict]:
    items = _catalog()
    category = category or (category_of(q) if q else None)
    if category:
        return [i for i in items if i["category"] == category][:limit]
    nq = _norm(q)
    if len(nq) < 2:
        return []
    # Name match: prefix of the name or of a word in it ranks first, then substring.
    scored = []
    for i in items:
        name = _norm(i["name"])
        if nq not in name:
            continue
        rank = 0 if name.startswith(nq) else 1 if any(w.startswith(nq) for w in name.split()) else 2
        scored.append((rank, len(name), i))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [i for _, _, i in scored][:limit]


@router.get("/categories")
def categories() -> list[dict]:
    counts: dict[str, int] = {}
    for i in _catalog():
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    return [{"key": k, "name": v[0], "count": counts.get(k, 0)} for k, v in CATEGORIES.items()]


def _parse_boxes(raw: list[str]) -> list[tuple[float, ...]]:
    boxes = []
    for text in raw:
        try:
            box = tuple(float(v) for v in text.split(","))
        except ValueError:
            box = ()
        if len(box) != 4:
            raise HTTPException(422, "bbox must be minx,miny,maxx,maxy")
        boxes.append(box)
    return boxes


def _intersects(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


@router.get("")
def features(
    q: str = "",
    category: str | None = None,
    bbox: list[str] = Query(default=[], description="Repeatable minx,miny,maxx,maxy; keeps features whose bbox meets any"),
) -> list[dict]:
    items = find(q, category)
    boxes = _parse_boxes(bbox)
    if boxes:
        items = [i for i in items if any(_intersects(i["bbox"], b) for b in boxes)]
    return _light(items)


class FeatureQuery(BaseModel):
    q: str = ""
    category: str | None = None
    areas: list[dict] = []  # GeoJSON Polygon/MultiPolygon geometries of the study areas


@router.post("/search")
def search(body: FeatureQuery) -> list[dict]:
    """Like GET /features, but keeps only features whose outline meets one of the areas."""
    items = find(body.q, body.category)
    if body.areas:
        try:
            areas = [prep(shape(a).buffer(0)) for a in body.areas]
        except Exception as exc:
            raise HTTPException(422, f"invalid area geometry: {exc}") from exc
        shapes = _shapes()
        items = [i for i in items if any(a.intersects(shapes[i["id"]]) for a in areas)]
    return _light(items)


@router.get("/{feature_id}")
def feature(feature_id: str) -> dict:
    for i in _catalog():
        if i["id"] == feature_id:
            return i
    raise HTTPException(404, "feature not found")
