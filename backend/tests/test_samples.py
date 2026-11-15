import json

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.main import app


def make_tif(path, tags=None, count=1, crs="EPSG:32614", origin=(480000, 2150000), nodata=-9999.0):
    data = np.arange(64 * 64, dtype="float32").reshape(1, 64, 64).repeat(count, axis=0)
    data[:, :4, :4] = nodata
    with rasterio.open(
        path, "w", driver="GTiff", width=64, height=64, count=count, dtype="float32",
        crs=crs, transform=from_origin(*origin, 30, 30), nodata=nodata,
    ) as dst:
        dst.write(data)
        if tags:
            dst.update_tags(**tags)


@pytest.fixture
def env(tmp_path):
    with TestClient(app) as c:
        app.state.samples_dir = tmp_path
        yield c, tmp_path


def by_id(client):
    return {i["id"]: i for i in client.get("/api/samples").json()["items"]}


def test_time_sources(env):
    client, d = env
    make_tif(d / "tagged.tif", tags={"TIFFTAG_DATETIME": "2025:03:04 10:20:30"})
    make_tif(d / "S1_20240115T051530_vv.tif")
    make_tif(d / "dated_2023-07-01.tif")
    make_tif(d / "side_20200101.tif", tags={"ACQUISITION_DATE": "2019-05-05"})
    (d / "side_20200101.json").write_text(json.dumps({"datetime": "2022-02-02T00:00:00Z", "label": "L"}))
    make_tif(d / "plain.tif")
    items = by_id(client)
    assert items["tagged"]["datetime"] == "2025-03-04T10:20:30Z"
    assert items["tagged"]["time_source"] == "tag:TIFFTAG_DATETIME"
    assert items["s1_20240115t051530_vv"]["datetime"] == "2024-01-15T05:15:30Z"
    assert items["s1_20240115t051530_vv"]["time_source"] == "filename"
    assert items["dated_2023-07-01"]["datetime"] == "2023-07-01T00:00:00Z"
    assert items["side_20200101"]["time_source"] == "sidecar"
    assert items["side_20200101"]["label"] == "L"
    assert items["plain"]["datetime"] is None and items["plain"]["time_source"] == "none"
    order = [i["id"] for i in client.get("/api/samples").json()["items"]]
    assert order[-1] == "plain"
    assert order[0] == "side_20200101"
    b = items["plain"]["bounds_wgs84"]
    assert -100 < b[0] < b[2] < -98 and 19 < b[1] < b[3] < 20


def test_filters(env):
    client, d = env
    make_tif(d / "a_20200101.tif")
    make_tif(d / "b_20240101.tif", crs="EPSG:4326", origin=(10, 10))
    make_tif(d / "nodate.tif")
    ids = lambda **p: [i["id"] for i in client.get("/api/samples", params=p).json()["items"]]
    assert ids(bbox="-100,19,-98,20") == ["a_20200101", "nodate"]
    assert ids(start="2023-01-01") == ["b_20240101"]
    assert ids(end="2021-01-01") == ["a_20200101"]
    assert client.get("/api/samples", params={"bbox": "1,2"}).status_code == 422


def test_detail_file_preview(env):
    client, d = env
    make_tif(d / "one.tif", tags={"TIFFTAG_DATETIME": "2025:03:04 10:20:30"})
    make_tif(d / "rgb.tif", count=3)
    detail = client.get("/api/samples/one").json()
    assert detail["tags"][""]["TIFFTAG_DATETIME"]
    assert detail["crs"] == "EPSG:32614"
    f = client.get("/api/samples/one/file")
    assert f.status_code == 200 and f.content[:2] in (b"II", b"MM")
    for sid in ("one", "rgb"):
        p = client.get(f"/api/samples/{sid}/preview.png")
        assert p.status_code == 200 and p.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(p.headers["x-bounds-wgs84"].split(",")) == 4


def test_upload(env, tmp_path_factory):
    client, d = env
    src = tmp_path_factory.mktemp("up") / "New File.tif"
    make_tif(src)
    r = client.post(
        "/api/samples",
        files={"file": ("New File.tif", src.read_bytes(), "image/tiff")},
        data={"datetime": "2024-06-01T12:00:00Z"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "new-file" and r.json()["time_source"] == "sidecar"
    assert (d / "new-file.json").exists()
    dup = client.post("/api/samples", files={"file": ("new file.tif", src.read_bytes())})
    assert dup.status_code == 409
    bad = client.post("/api/samples", files={"file": ("junk.tif", b"not a tiff")})
    assert bad.status_code == 422
    assert not list(d.glob("junk*")) and not list(d.glob(".upload*"))
    assert client.post("/api/samples", files={"file": ("x.png", b"x")}).status_code == 422


def test_traversal(env):
    client, d = env
    make_tif(d / "ok.tif")
    for bad in ("..%2F..%2Fetc%2Fpasswd", "../ok", "%2e%2e", "nope"):
        r = client.get(f"/api/samples/{bad}/file")
        assert r.status_code == 404
