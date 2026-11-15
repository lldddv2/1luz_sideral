import io

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.main import app
from app.services import nisar_s3

AOI = {"type": "Polygon", "coordinates": [[[-90.2, 29.9], [-90.0, 29.9], [-90.0, 30.1], [-90.2, 30.1], [-90.2, 29.9]]]}
FOOT = {"type": "Polygon", "coordinates": [[[-91, 29], [-89, 29], [-89, 31], [-91, 31], [-91, 29]]]}


def scene(gid, start):
    return {"granule_id": gid, "acquired_start": start, "acquired_stop": start, "track": 156, "frame": 73,
            "direction": "Descending", "polarizations": ["HH", "HV"], "footprint": FOOT,
            "aoi": {"name": "t", "geometry": AOI}, "crs": "EPSG:4326", "pixel_size_m": 20.0,
            "units": "linear power (gamma0)",
            "assets": {"HH": {"key": f"nisar/gcov/{gid}/HH.tif"}, "HV": {"key": f"nisar/gcov/{gid}/HV.tif"}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    tif = tmp_path / "hh.tif"
    with rasterio.open(tif, "w", driver="GTiff", width=40, height=40, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(-90.2, 30.1, 0.005, 0.005), nodata=float("nan")) as dst:
        dst.write(np.random.default_rng(0).random((1, 40, 40), dtype="float32"))
    index = {"scenes": [scene("G2", "2026-11-04T00:45:09Z"), scene("G1", "2026-10-23T00:45:09Z")]}
    calls = []
    monkeypatch.setenv("NISAR_BUCKET", "bkt")
    monkeypatch.setattr(nisar_s3, "_cache", {})
    monkeypatch.setattr(nisar_s3, "fetch_index", lambda name: calls.append(name) or index)
    monkeypatch.setattr(nisar_s3, "vsis3_path", lambda name, s, pol: str(tif) if pol in s["assets"] else None)
    with TestClient(app) as c:
        c.calls = calls
        yield c


def q(c, **body):
    return c.post("/api/scenes/query", json={"source": "nisar", **body})


def test_query_sorted_and_cached(env):
    r = q(env, regions=AOI).json()
    props = [f["properties"] for f in r["features"]]
    assert [p["scene_id"] for p in props] == ["G1", "G2"]
    assert props[0]["source"] == "nisar" and props[0]["polarizations"] == ["HH", "HV"]
    assert props[0]["regions"][0]["coverage_pct"] == 100.0
    q(env, regions=AOI)
    assert env.calls == ["bkt"]


def test_query_date_and_outside(env):
    r = q(env, regions=AOI, date="2026-11-05", window_days=3).json()
    assert [f["properties"]["scene_id"] for f in r["features"]] == ["G2"]
    far = {"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 10]]]}
    assert q(env, regions=far).json()["features"] == []


def test_data_png_and_404(env):
    r = env.post("/api/scenes/G1/data", json={"geometry": AOI, "source": "nisar", "width": 128, "height": 128})
    assert r.status_code == 200 and r.headers["x-out-size"] == "128x128"
    with rasterio.open(io.BytesIO(r.content)) as src:
        assert src.count == 4
    assert env.post("/api/scenes/NOPE/data", json={"geometry": AOI, "source": "nisar"}).status_code == 404


def test_no_bucket_501(env, monkeypatch):
    monkeypatch.delenv("NISAR_BUCKET")
    assert q(env, regions=AOI).status_code == 501


def test_index_error_502(env, monkeypatch):
    def boom(name):
        raise OSError("down")
    monkeypatch.setattr(nisar_s3, "fetch_index", boom)
    assert q(env, regions=AOI).status_code == 502
