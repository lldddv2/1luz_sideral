from pathlib import Path

import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile

from app.main import app
from app.services import dem

SAMPLE = Path(__file__).resolve().parents[2] / "notebooks" / "lucho" / "cop90_N19_W100.tif"
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample DEM tile missing")


@pytest.fixture
def client(monkeypatch, tmp_path):
    def fake_url(lat, lon):
        name = dem.tile_name(lat, lon)
        return str(SAMPLE) if "N19_00_W100" in name else str(tmp_path / f"{name}.tif")

    monkeypatch.setattr(dem, "tile_url", fake_url)
    with TestClient(app) as c:
        yield c


def test_tile_name():
    assert dem.tile_name(19.4, -99.1) == "Copernicus_DSM_COG_30_N19_00_W100_00_DEM"
    assert dem.tile_name(-0.5, 0.5) == "Copernicus_DSM_COG_30_S01_00_E000_00_DEM"
    with pytest.raises(ValueError):
        dem.tile_name(95, 0)


def test_metadata(client):
    r = client.get("/api/dem/metadata", params={"lat": 19.4, "lon": -99.1})
    assert r.status_code == 200
    body = r.json()
    assert body["crs"] == "EPSG:4326"
    assert body["bounds"][0] == pytest.approx(-100, abs=1e-3)
    assert body["min"] is not None and body["max"] > body["min"]


def test_file(client):
    r = client.get("/api/dem/file", params={"lat": 19.4, "lon": -99.1})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/tiff"
    assert ".tif" in r.headers["content-disposition"]
    assert r.content == SAMPLE.read_bytes()


def test_crop(client):
    r = client.get("/api/dem/crop", params={"bbox": "-99.3,19.3,-99.0,19.6"})
    assert r.status_code == 200
    with MemoryFile(r.content) as mem, mem.open() as ds:
        assert ds.bounds.left == pytest.approx(-99.3, abs=1e-3)
        assert ds.width > 0 and ds.height > 0


def test_crop_cross_tile(client):
    r = client.get("/api/dem/crop", params={"bbox": "-99.5,19.5,-98.5,19.8"})
    assert r.status_code == 422


def test_missing_tile(client):
    for path in ("metadata", "file"):
        r = client.get(f"/api/dem/{path}", params={"lat": 0.5, "lon": -30.5})
        assert r.status_code == 404, path
