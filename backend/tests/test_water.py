import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from app.main import app
from app.water import model as unet

DATA = Path(__file__).parent / "data" / "water"


def test_model_loads():
    model, meta = unet.load()
    assert meta["threshold"] == 0.97 and meta["patch"] == 64
    assert sum(p.numel() for p in model.parameters()) > 100_000


def _grid_30m(crs, b):
    g = transform_bounds(crs, "EPSG:4326", *b, densify_pts=21)
    dc = CRS.from_epsg(unet.utm_epsg((g[0] + g[2]) / 2, (g[1] + g[3]) / 2))
    left, bottom, right, top = transform_bounds(crs, dc, *b, densify_pts=21)
    left, bottom = math.floor(left / 30) * 30, math.floor(bottom / 30) * 30
    right, top = math.ceil(right / 30) * 30, math.ceil(top / 30) * 30
    return dc, from_origin(left, top, 30, 30), int(round((top - bottom) / 30)), int(round((right - left) / 30))


@pytest.mark.skipif(not (DATA / "nisar_hhhh.tif").exists(), reason="example rasters missing")
def test_matches_reference_prediction():
    with rasterio.open(DATA / "nisar_hhhh.tif") as src:
        s = src.read(1).astype(np.float32)
        v = (src.read_masks(1) > 0) & np.isfinite(s) & (s > 0)
        if src.nodata is not None:
            v &= s != src.nodata
        dc, dt, h, w = _grid_30m(src.crs, src.bounds)
        power = np.full((h, w), np.nan, np.float32)
        reproject(
            source=np.where(v, s, np.nan), destination=power, src_transform=src.transform, src_crs=src.crs,
            src_nodata=np.nan, dst_transform=dt, dst_crs=dc, dst_nodata=np.nan, resampling=Resampling.average,
        )
    prob, valid = unet.predict(power)
    cls = unet.classify(prob, unet.load()[1]["threshold"])
    with rasterio.open(DATA / "prediccion_clase.tif") as r:
        ref = r.read(1)
    assert ref.shape == cls.shape
    both = valid & (ref != 255)
    assert both.sum() > 1000
    assert (ref[both] == cls[both]).mean() > 0.99


def test_aoi_too_large_is_400():
    with TestClient(app) as c:
        r = c.post("/api/water", json={"bbox": [20, -23, 24, -19]})
    assert r.status_code == 400


def test_bad_bbox_is_400():
    with TestClient(app) as c:
        r = c.post("/api/water", json={"bbox": [23, -19, 22, -20]})
    assert r.status_code == 400
