"""Pull-based client: connects the local U-Net water model to a luzsi backend.

Loop: POST /api/models/hello -> GET /api/models/jobs/next (long poll) -> download input.tif
-> predict water probability -> POST result GeoTIFF.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import numpy as np
import rasterio
import requests

from .model import load, predict_db

log = logging.getLogger("water_unet")


class Unauthorized(Exception):
    pass


def _check(r):
    if r.status_code == 401:
        raise Unauthorized("401: token invalid or expired")
    r.raise_for_status()
    return r


def infer_tif(data: bytes) -> bytes:
    """Read a 1-band HH dB GeoTIFF (NaN nodata), return same-grid float32 probability GeoTIFF."""
    with rasterio.MemoryFile(data) as mf, mf.open() as src:
        db = src.read(1).astype(np.float32)
        if src.nodata is not None and not np.isnan(src.nodata):
            db[db == src.nodata] = np.nan
        profile = dict(src.profile)
    prob = predict_db(db)
    for k in ("blockxsize", "blockysize", "tiled", "interleave"):
        profile.pop(k, None)  # input block layout may not fit; let GDAL choose (avoids BLOCKXSIZE warning)
    profile.update(driver="GTiff", dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.MemoryFile() as mf:
        with mf.open(**profile) as dst:
            dst.write(prob, 1)
        return mf.read()


class Client:
    def __init__(self, url: str, token: str, session=None):
        self.root = url.rstrip("/")
        self.base = self.root + "/api/models"
        self.s = session or requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"

    def hello(self) -> None:
        body = {"name": "water_unet_v1", "output": "probability", "label": "Agua", "pols": ["HH"]}
        _check(self.s.post(f"{self.base}/hello", json=body, timeout=15))

    def step(self) -> bool:
        """One poll; returns True if a job was received (processed or failed)."""
        r = _check(self.s.get(f"{self.base}/jobs/next", timeout=35))
        if r.status_code == 204:
            return False
        job = r.json()
        jid = job["job_id"]
        log.info("job %s bbox=%s", jid, job.get("bbox"))
        try:
            url = job.get("input_url") or f"/api/models/jobs/{jid}/input.tif"
            if url.startswith("/"):
                url = self.root + url
            t = time.time()
            data = _check(self.s.get(url, timeout=300)).content
            out = infer_tif(data)
            files = {"file": ("result.tif", out, "image/tiff")}
            _check(self.s.post(f"{self.base}/jobs/{jid}/result", files=files, timeout=120))
            log.info("job %s done in %.1fs", jid, time.time() - t)
        except Unauthorized:
            raise
        except Exception as e:  # keep serving other jobs
            log.error("job %s failed: %s", jid, e)
        return True

    def run(self) -> None:
        self.hello()
        log.info("connected to %s", self.base)
        while True:
            try:
                self.step()
            except Unauthorized:
                raise
            except Exception as e:
                log.error("poll error: %s", e)
                time.sleep(3)
                try:
                    self.hello()
                except Unauthorized:
                    raise
                except Exception:
                    pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="luzsi U-Net water model client")
    p.add_argument("--url", default=os.environ.get("LUZSI_URL", "http://localhost:8000"))
    p.add_argument("--token", default=os.environ.get("LUZSI_TOKEN"))
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not a.token:
        p.error("--token or LUZSI_TOKEN required (copy it from the web app)")
    load()
    try:
        Client(a.url, a.token).run()
    except Unauthorized as e:
        log.error("%s; get a new token from the web app", e)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
