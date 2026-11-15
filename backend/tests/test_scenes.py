import io
import json

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.main import app


def make_tif(path, count=1, date=None):
    # 100x100 px, 0.01 deg: lon -99.5..-98.5, lat 19..20
    data = np.arange(100 * 100, dtype="float32").reshape(1, 100, 100).repeat(count, axis=0)
    with rasterio.open(path, "w", driver="GTiff", width=100, height=100, count=count, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(-99.5, 20, 0.01, 0.01), nodata=-9999.0) as dst:
        dst.write(data)
    if date:
        path.with_suffix(".json").write_text(json.dumps({"datetime": date}))


def poly(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


TRI = {"type": "Polygon", "coordinates": [[[-99.4, 19.1], [-98.9, 19.1], [-99.4, 19.6], [-99.4, 19.1]]]}


@pytest.fixture
def env(tmp_path):
    make_tif(tmp_path / "a.tif", date="2025-01-10")
    make_tif(tmp_path / "b.tif", count=3, date="2025-03-01")
    make_tif(tmp_path / "nodate.tif")
    with TestClient(app) as c:
        app.state.samples_dir = tmp_path
        yield c


def q(client, **body):
    return client.post("/api/scenes/query", json=body)


def fc(*geoms):
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"id": f"z{i}"}, "geometry": g} for i, g in enumerate(geoms)]}


def test_query_date_window(env):
    r = q(env, regions=fc(poly(-99.2, 19.2, -99.0, 19.4)), date="2025-01-01").json()
    assert [f["properties"]["scene_id"] for f in r["features"]] == ["a"]
    assert r["features"][0]["properties"]["days_from_date"] == 9
    r = q(env, regions=fc(poly(-99.2, 19.2, -99.0, 19.4)), date="2025-01-01", window_days=365).json()
    assert [f["properties"]["scene_id"] for f in r["features"]] == ["a", "b"]


def test_query_start_end_and_no_filter(env):
    r = q(env, regions=poly(-99.2, 19.2, -99.0, 19.4), start="2025-02-01", end="2025-04-01").json()
    assert [f["properties"]["scene_id"] for f in r["features"]] == ["b"]
    r = q(env, regions=poly(-99.2, 19.2, -99.0, 19.4)).json()
    ids = [f["properties"]["scene_id"] for f in r["features"]]
    assert ids == ["a", "b", "nodate"]
    assert r["features"][0]["properties"]["regions"] == [{"id": "r1", "coverage_pct": 100.0}]


def test_query_coverage_and_empty(env):
    r = q(env, regions=fc(poly(-100, 19, -99, 20), poly(10, 10, 11, 11))).json()
    regs = r["features"][0]["properties"]["regions"]
    assert regs == [{"id": "z0", "coverage_pct": 50.0}]
    assert q(env, regions=poly(10, 10, 11, 11)).json()["features"] == []


def test_query_limits(env, monkeypatch):
    monkeypatch.delenv("NISAR_BUCKET", raising=False)
    assert q(env, regions=fc(*[TRI] * 11)).status_code == 422
    assert q(env, regions=TRI, source="nisar").status_code == 501


def data(client, sid="a", **body):
    return client.post(f"/api/scenes/{sid}/data", json={"geometry": TRI, **body})


def png(resp):
    with rasterio.open(io.BytesIO(resp.content)) as src:
        return src.read()


def test_png_sizes(env):
    r = data(env, width=128, height=128)
    assert r.status_code == 200 and r.headers["x-out-size"] == "128x128"
    img = png(r)
    assert img.shape == (4, 128, 128)
    assert img[3, 5, 120] == 0 and img[3, 120, 5] == 255  # triangle: upper-right outside
    r = data(env, width=100)
    assert r.headers["x-out-size"] == "100x100"
    assert data(env, geometry=poly(-99.4, 19.1, -98.9, 19.35), width=100).headers["x-out-size"] == "100x50"


def test_pad_vs_stretch(env):
    g = poly(-99.4, 19.1, -98.9, 19.35)
    pad = png(data(env, geometry=g, width=64, height=64, fit="pad"))
    assert pad[3, 0, 32] == 0 and pad[3, 32, 32] == 255
    st = png(data(env, geometry=g, width=64, height=64, fit="stretch"))
    assert st[3, 0, 32] == 255


def test_geotiff_and_json(env):
    r = data(env, "b", format="geotiff", width=64, height=32, fit="stretch")
    with rasterio.open(io.BytesIO(r.content)) as src:
        assert (src.width, src.height, src.count, src.crs.to_epsg()) == (64, 32, 3, 4326)
        assert src.nodata == -9999.0
    s = data(env, format="json", mask=False).json()
    assert s["bands"][0]["valid_pct"] == 100.0 and s["bands"][0]["min"] < s["bands"][0]["max"]
    assert data(env, format="json").json()["bands"][0]["valid_pct"] < 60


def test_data_limits(env):
    assert data(env, width=2048, height=2048).status_code == 200
    assert data(env, width=4096).status_code == 422
    assert data(env, geometry=poly(10, 10, 11, 11)).status_code == 422
    assert data(env, "nope").status_code == 404


def test_png_corners_header(env):
    import json

    r = data(env, geometry=poly(-99.4, 19.1, -98.9, 19.35), width=100)
    assert "X-Corners-WGS84" in r.headers["access-control-expose-headers"]
    tl, tr, br, bl = json.loads(r.headers["x-corners-wgs84"])
    assert tl[0] < tr[0] and bl[0] < br[0] and tl[1] > bl[1] and tr[1] > br[1]
    b = [float(v) for v in r.headers["x-bounds-wgs84"].split(",")]
    assert abs(tl[0] - b[0]) < 0.05 and abs(br[1] - b[1]) < 0.05
