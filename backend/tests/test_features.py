from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def get(**params):
    res = client.get("/api/features", params=params)
    assert res.status_code == 200
    return res.json()


def test_category_word_returns_whole_category():
    wetlands = get(q="humedales")
    assert len(wetlands) > 10
    assert {f["category"] for f in wetlands} == {"wetland"}
    assert all(len(f["bbox"]) == 4 for f in wetlands)


def test_accent_and_english_synonyms():
    assert {f["category"] for f in get(q="Glaciar")} == {"glacier"}
    assert {f["category"] for f in get(q="volcán")} == {"volcano"}
    assert get(q="deserts") == get(q="desiertos")


def test_name_match():
    names = [f["name"] for f in get(q="Sahara")]
    assert names[0] == "Sahara"
    assert get(q="x") == []


def test_categories_all_populated():
    cats = client.get("/api/features/categories").json()
    assert all(c["count"] > 0 for c in cats)


def test_bbox_filter():
    sahara_box = "-10,15,30,30"
    names = [f["name"] for f in get(q="desierto", bbox=sahara_box)]
    assert "Sahara" in names
    assert len(names) < len(get(q="desierto"))
    iceland = [f["name"] for f in get(q="glaciares", bbox="-25,63,-13,67")]
    assert iceland and all(n != "Sahara" for n in iceland)
    assert get(q="Sahara", bbox="-25,63,-13,67") == []
    assert client.get("/api/features", params={"q": "x", "bbox": "1,2"}).status_code == 422


def test_list_is_light_and_detail_has_geometry():
    wetlands = get(q="humedales")
    assert all("geometry" not in f and f["id"] for f in wetlands)
    detail = client.get(f"/api/features/{wetlands[0]['id']}").json()
    assert detail["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert client.get("/api/features/no-such-place").status_code == 404


def search(q, areas):
    res = client.post("/api/features/search", json={"q": q, "areas": areas})
    assert res.status_code == 200
    return [f["name"] for f in res.json()]


def test_polygon_filter_beats_bbox():
    # Thin diagonal strip from Chile to southern Brazil: crosses the Amazon bbox (-79,-17,-44,5.5)
    # in its empty south-west corner, outside the rough Amazon outline.
    strip = {"type": "Polygon", "coordinates": [[[-75, -20], [-74.5, -20], [-70, -16.5], [-70.5, -16.5], [-75, -20]]]}
    assert "Amazonía" in [f["name"] for f in get(q="selvas", bbox="-75,-20,-70,-16.5")]
    assert "Amazonía" not in search("selvas", [strip])
    inside = {"type": "Polygon", "coordinates": [[[-62, -5], [-60, -5], [-60, -3], [-62, -3], [-62, -5]]]}
    assert search("selvas", [inside]) == ["Amazonía"]
    assert "Sahara" in search("desierto", [{"type": "Polygon", "coordinates": [[[0, 20], [5, 20], [5, 25], [0, 20]]]}])
    assert client.post("/api/features/search", json={"q": "x", "areas": [{"type": "Nope"}]}).status_code == 422
