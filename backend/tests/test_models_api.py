import asyncio
import io

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.main import app
from app.models_api import raster
from app.models_api.store import Store
from app.routers import models as models_router
from app.water import service

BBOX = [22.5, -19.5, 22.6, -19.4]


def _tif(path, data, transform=from_origin(500000, 7850000, 30, 30)):
    with rasterio.open(
        path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1, dtype="float32",
        crs="EPSG:32734", transform=transform, nodata=float("nan"),
    ) as dst:
        dst.write(data.astype(np.float32), 1)


@pytest.fixture
def client(tmp_path, monkeypatch):
    def fake_input(bbox, date, cache_dir, pols=None):
        pols = pols or ["HH"]
        cache_dir.mkdir(parents=True, exist_ok=True)
        p = cache_dir / f"in_{'_'.join(pols)}.tif"
        with rasterio.open(
            p, "w", driver="GTiff", width=50, height=40, count=len(pols), dtype="float32",
            crs="EPSG:32734", transform=from_origin(500000, 7850000, 30, 30), nodata=float("nan"),
        ) as dst:
            for i, pol in enumerate(pols, 1):
                dst.write(np.full((40, 50), -12.0 - i, np.float32), i)
                dst.set_band_description(i, pol)
        return p, {"scene_id": "NISAR_FAKE", "datetime": "2026-01-01T00:00:00Z", "pols": pols}

    monkeypatch.setattr(raster, "build_input", fake_input)
    monkeypatch.setattr(models_router, "LONG_POLL_S", 0.3)
    with TestClient(app) as c:
        app.state.models_dir = tmp_path / "models"
        app.state.models = Store()
        yield c


def _token(c):
    r = c.post("/api/models/token")
    assert r.status_code == 200 and r.json()["expires_at"] > 0
    return r.json()["token"]


def _drain(c, token):
    q = app.state.models.get(token).events
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_auth_required(client):
    assert client.get("/api/models/status").status_code == 401
    assert client.get("/api/models/status", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/models/events", params={"token": "nope"}).status_code == 401
    assert client.get("/api/models/jobs/next").status_code == 401


def test_hello_status_and_bbox_limit(client):
    h = {"Authorization": f"Bearer {_token(client)}"}
    assert client.get("/api/models/status", headers=h).json()["connected"] is False
    assert client.post("/api/models/hello", headers=h, json={"name": "unet", "kind": "water_prob", "pols": ["HH"]}).json() == {"ok": True}
    st = client.get("/api/models/status", headers=h).json()
    assert st["connected"] is True and st["name"] == "unet"
    assert client.post("/api/models/jobs", headers=h, json={"bbox": [20, -20, 21, -19]}).status_code == 400


def test_full_job_flow(client):
    token = _token(client)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/models/jobs/next", headers=h).status_code == 204
    job_id = client.post("/api/models/jobs", headers=h, json={"bbox": BBOX}).json()["job_id"]
    r = client.get("/api/models/jobs/next", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == job_id and body["bbox"] == BBOX and body["input_url"].endswith("/input.tif")

    r = client.get(body["input_url"], headers=h)
    assert r.status_code == 200
    with rasterio.MemoryFile(r.content) as m, m.open() as src:
        assert src.shape == (40, 50) and src.dtypes[0] == "float32"

    # Wrong grid is rejected.
    bad = io.BytesIO()
    with rasterio.open(bad, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32") as d:
        d.write(np.zeros((1, 10, 10), np.float32))
    assert client.post(f"/api/models/jobs/{job_id}/result", headers=h, files={"file": ("p.tif", bad.getvalue())}).status_code == 400

    prob = np.zeros((40, 50), np.float32)
    prob[:, :25] = 0.99
    good = client.app.state.models_dir / "prob.tif"
    _tif(good, prob)
    _drain(client, token)
    r = client.post(f"/api/models/jobs/{job_id}/result", headers=h, files={"file": ("p.tif", good.read_bytes())})
    assert r.status_code == 200, r.text
    done = [d for e, d in _drain(client, token) if e == "job" and d["state"] == "done"]
    assert done and abs(done[0]["stats"]["fraction"] - 0.5) < 1e-6 and len(done[0]["bounds"]) == 4
    assert done[0]["output"] == "probability" and done[0]["legend"] == {"min": 0.0, "max": 1.0}
    png = client.get(done[0]["png_url"])
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"


def test_no_scene_errors_job(client, monkeypatch):
    def none(*a):
        raise service.NoScene("no scene")

    monkeypatch.setattr(raster, "build_input", none)
    token = _token(client)
    h = {"Authorization": f"Bearer {token}"}
    job_id = client.post("/api/models/jobs", headers=h, json={"bbox": BBOX}).json()["job_id"]
    client.get("/api/models/jobs/next", headers=h)
    assert client.get(f"/api/models/jobs/{job_id}/input.tif", headers=h).status_code == 404
    assert any(e == "job" and d["state"] == "error" for e, d in _drain(client, token))


def test_sse_stream_format():
    st = Store()
    s = st.new_token()

    class Req:
        async def is_disconnected(self):
            return False

    async def run():
        gen = models_router.event_stream(Req(), s, st)
        first = await gen.__anext__()
        st.push(s, "job", {"job_id": "x", "state": "done"})
        second = await gen.__anext__()
        await gen.aclose()
        return first, second

    first, second = asyncio.run(run())
    assert first.startswith("event: status\ndata: ")
    assert second == 'event: job\ndata: {"job_id": "x", "state": "done"}\n\n'


def _run_job(c, h, token, arr):
    job_id = c.post("/api/models/jobs", headers=h, json={"bbox": BBOX}).json()["job_id"]
    body = c.get("/api/models/jobs/next", headers=h).json()
    inp = c.get(body["input_url"], headers=h)
    p = c.app.state.models_dir / f"r_{job_id}.tif"
    _tif(p, arr)
    _drain(c, token)
    r = c.post(f"/api/models/jobs/{job_id}/result", headers=h, files={"file": ("r.tif", p.read_bytes())})
    assert r.status_code == 200, r.text
    done = [d for e, d in _drain(c, token) if e == "job" and d["state"] == "done"][0]
    assert c.get(done["png_url"]).content[1:4] == b"PNG"
    return body, inp, done


def test_legacy_kind_is_probability(client):
    token = _token(client)
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/models/hello", headers=h, json={"name": "old", "kind": "water_prob"})
    st = client.get("/api/models/status", headers=h).json()
    assert st["output"] == "probability" and st["pols"] == ["HH"]
    assert client.post("/api/models/hello", headers=h, json={"name": "x", "pols": ["XX"]}).status_code == 400


def test_continuous_multipol(client):
    token = _token(client)
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/models/hello", headers=h, json={
        "name": "bio", "output": "continuous", "pols": ["HH", "HV"], "label": "Biomasa", "units": "t/ha"})
    st = client.get("/api/models/status", headers=h).json()
    assert st["output"] == "continuous" and st["pols"] == ["HH", "HV"] and st["units"] == "t/ha"
    arr = np.tile(np.linspace(0, 100, 50, dtype=np.float32), (40, 1))
    arr[0, 0] = np.nan
    body, inp, done = _run_job(client, h, token, arr)
    assert body["pols"] == ["HH", "HV"]
    with rasterio.MemoryFile(inp.content) as m, m.open() as src:
        assert src.count == 2 and src.descriptions == ("HH", "HV")
    assert done["output"] == "continuous" and done["label"] == "Biomasa" and done["units"] == "t/ha"
    assert "fraction" not in done["stats"] and done["stats"]["max"] == 100
    assert 0 < done["legend"]["min"] < done["legend"]["max"] < 100


def test_classes(client):
    token = _token(client)
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/models/hello", headers=h, json={"name": "lc", "output": "classes"})
    arr = np.zeros((40, 50), np.float32)
    arr[:, 10:20], arr[:, 20:30] = 1, 3
    _, _, done = _run_job(client, h, token, arr)
    assert [c["value"] for c in done["legend"]["classes"]] == [1, 3]
    assert all(c["color"].startswith("#") for c in done["legend"]["classes"])


def test_render_classes_too_many(tmp_path):
    p = tmp_path / "in.tif"
    _tif(p, np.zeros((4, 5)))
    arr = np.arange(20, dtype=np.float32).reshape(4, 5)
    out = tmp_path / "r.tif"
    _tif(out, arr)
    with pytest.raises(ValueError):
        raster.render_result(p, out.read_bytes(), tmp_path / "o.png", "classes")
