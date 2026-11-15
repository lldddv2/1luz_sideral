from fastapi.testclient import TestClient

from app.main import create_app
from app.routers import regions

client = TestClient(create_app())

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [0.5, 0.001], [1, 0], [1, 1], [0, 1], [0, 0]]]}
ITEMS = [
    {"place_id": 1, "name": "Medellín", "display_name": "Medellín, Antioquia, Colombia", "class": "place",
     "type": "city", "addresstype": "city", "boundingbox": ["6", "6.4", "-75.7", "-75.4"],
     "geojson": {"type": "Point", "coordinates": [-75.5, 6.2]}},
    {"place_id": 2, "name": "Antioquia", "display_name": "Antioquia, Colombia", "class": "boundary",
     "type": "administrative", "addresstype": "state", "boundingbox": ["0", "1", "0", "1"], "geojson": SQUARE},
    {"place_id": 3, "name": "Colombia", "display_name": "Colombia", "class": "boundary",
     "type": "administrative", "addresstype": "country", "boundingbox": ["0", "1", "0", "1"], "geojson": SQUARE},
]


def test_regions_ranked_simplified_and_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(regions, "_fetch", lambda q, box=None: calls.append(q) or ITEMS)
    regions._cache.clear()
    res = client.get("/api/regions", params={"q": "Antioquia "})
    assert res.status_code == 200
    data = res.json()
    assert [r["type"] for r in data] == ["País", "Departamento / Estado", "Ciudad"]
    assert data[0]["bbox"] == [0, 0, 1, 1]
    assert data[0]["geometry"]["type"] == "Polygon"
    assert len(data[0]["geometry"]["coordinates"][0]) < 6  # near-collinear point dropped
    assert data[2]["geometry"] is None
    client.get("/api/regions", params={"q": "antioquia"})
    assert calls == ["antioquia"]


def test_regions_short_query_rejected():
    assert client.get("/api/regions", params={"q": "a"}).status_code == 422


def test_regions_viewbox_passed_and_cached_apart(monkeypatch):
    calls = []
    monkeypatch.setattr(regions, "_fetch", lambda q, box=None: calls.append((q, box)) or ITEMS)
    regions._cache.clear()
    assert client.get("/api/regions", params={"q": "rio", "viewbox": "-77.2,5.4,-73.8,8.9"}).status_code == 200
    client.get("/api/regions", params={"q": "rio"})
    client.get("/api/regions", params={"q": "rio", "viewbox": "-77.2,5.4,-73.8,8.9"})
    assert calls == [("rio", (-77.2, 5.4, -73.8, 8.9)), ("rio", None)]


def test_regions_bad_viewbox_rejected():
    assert client.get("/api/regions", params={"q": "rio", "viewbox": "a,b,c,d"}).status_code == 422
    assert client.get("/api/regions", params={"q": "rio", "viewbox": "10,0,5,1"}).status_code == 422
