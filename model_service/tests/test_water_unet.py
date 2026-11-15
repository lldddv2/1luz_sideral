import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from water_unet import client as cl
from water_unet import model as unet

DATA = Path(__file__).resolve().parents[2] / "backend" / "tests" / "data" / "water"


def _grid_30m(crs, b):
    g = transform_bounds(crs, "EPSG:4326", *b, densify_pts=21)
    dc = CRS.from_epsg(unet.utm_epsg((g[0] + g[2]) / 2, (g[1] + g[3]) / 2))
    left, bottom, right, top = transform_bounds(crs, dc, *b, densify_pts=21)
    left, bottom = math.floor(left / 30) * 30, math.floor(bottom / 30) * 30
    right, top = math.ceil(right / 30) * 30, math.ceil(top / 30) * 30
    return dc, from_origin(left, top, 30, 30), int(round((top - bottom) / 30)), int(round((right - left) / 30))


def _input_tif():
    """Backend-style input.tif (HH dB, 30 m UTM, NaN nodata) built from the example raster."""
    with rasterio.open(DATA / "nisar_hhhh.tif") as src:
        s = src.read(1).astype(np.float32)
        v = (src.read_masks(1) > 0) & np.isfinite(s) & (s > 0)
        if src.nodata is not None:
            v &= s != src.nodata
        dc, dt, h, w = _grid_30m(src.crs, src.bounds)
        power = np.full((h, w), np.nan, np.float32)
        reproject(source=np.where(v, s, np.nan), destination=power, src_transform=src.transform, src_crs=src.crs,
                  src_nodata=np.nan, dst_transform=dt, dst_crs=dc, dst_nodata=np.nan, resampling=Resampling.average)
    db = np.where(np.isfinite(power) & (power > 0), 10 * np.log10(power), np.nan).astype(np.float32)
    with rasterio.MemoryFile() as mf:
        with mf.open(driver="GTiff", width=w, height=h, count=1, dtype="float32", crs=dc, transform=dt,
                     nodata=np.nan) as d:
            d.write(db, 1)
        return mf.read(), dc, dt


@pytest.mark.skipif(not (DATA / "nisar_hhhh.tif").exists(), reason="example rasters missing")
def test_matches_reference_prediction():
    tif, crs, tr = _input_tif()
    out = cl.infer_tif(tif)
    with rasterio.MemoryFile(out) as mf, mf.open() as r:
        prob = r.read(1)
        assert r.crs == crs and r.transform == tr and r.dtypes[0] == "float32"
    valid = np.isfinite(prob)
    assert np.nanmin(prob) >= 0 and np.nanmax(prob) <= 1
    cls = np.where(prob >= unet.load()[1]["threshold"], 1, 0)
    with rasterio.open(DATA / "prediccion_clase.tif") as r:
        ref = r.read(1)
    both = valid & (ref != 255)
    assert both.sum() > 1000
    assert (ref[both] == cls[both]).mean() > 0.99


class Resp:
    def __init__(self, status=200, json=None, content=b""):
        self.status_code, self._json, self.content = status, json, content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, tif, next_status=200):
        self.headers, self.calls, self.tif, self.next_status = {}, [], tif, next_status

    def post(self, url, json=None, files=None, timeout=None):
        self.calls.append(("POST", url, json, files))
        return Resp(json={"ok": True})

    def get(self, url, timeout=None):
        self.calls.append(("GET", url, None, None))
        if url.endswith("/jobs/next"):
            if self.next_status == 204:
                return Resp(204)
            return Resp(json={"job_id": "j1", "bbox": [0, 0, 1, 1], "date": None,
                              "input_url": "/api/models/jobs/j1/input.tif"})
        return Resp(content=self.tif)


def _small_tif():
    db = np.full((40, 50), -12, np.float32)
    db[:10] = -22
    db[0, 0] = np.nan
    with rasterio.MemoryFile() as mf:
        with mf.open(driver="GTiff", width=50, height=40, count=1, dtype="float32", crs="EPSG:32734",
                     transform=from_origin(500000, 7800000, 30, 30), nodata=np.nan) as d:
            d.write(db, 1)
        return mf.read()


def test_client_one_cycle():
    s = FakeSession(_small_tif())
    c = cl.Client("http://x:8000/", "tok", session=s)
    c.hello()
    assert c.step() is True
    assert s.headers["Authorization"] == "Bearer tok"
    assert [(a, u) for a, u, *_ in s.calls] == [
        ("POST", "http://x:8000/api/models/hello"),
        ("GET", "http://x:8000/api/models/jobs/next"),
        ("GET", "http://x:8000/api/models/jobs/j1/input.tif"),
        ("POST", "http://x:8000/api/models/jobs/j1/result"),
    ]
    assert s.calls[0][2]["output"] == "probability" and s.calls[0][2]["pols"] == ["HH"]
    out = s.calls[-1][3]["file"][1]
    with rasterio.MemoryFile(out) as mf, mf.open() as r:
        p = r.read(1)
        assert p.shape == (40, 50) and np.isnan(p[0, 0]) and np.nanmax(p) <= 1


def test_client_204_and_401():
    s = FakeSession(b"", next_status=204)
    assert cl.Client("http://x", "t", session=s).step() is False
    s.get = lambda url, timeout=None: Resp(401)
    with pytest.raises(cl.Unauthorized):
        cl.Client("http://x", "t", session=s).step()
