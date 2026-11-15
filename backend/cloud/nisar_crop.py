"""Crop NISAR GCOV granules to an AOI inside AWS us-west-2 and store COGs in S3.

Runs on a one-shot EC2 instance. Earthdata credentials come from Secrets Manager
(secret JSON: {"username": ..., "password": ...}). Only the needed HDF5 chunks are
range-read from the ASF bucket; whole granules are never downloaded.

Output (native UTM grid of the granule, no reprojection):
  s3://<bucket>/nisar/gcov/<granule_id>/HH.tif, HV.tif, metadata.json
  s3://<bucket>/nisar/gcov/index.json
"""
import json
import os
import sys
import tempfile
import time

import boto3
import h5py
import numpy as np
import rasterio
import rasterio.shutil
import requests
import s3fs
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

REGION = "us-west-2"
BUCKET = os.environ["NISAR_BUCKET"]
SECRET_ID = os.environ.get("EARTHDATA_SECRET", "luz-sideral/earthdata")
AOI_NAME = "Lake Pontchartrain south shore pilot"
AOI = {
    "type": "Polygon",
    "coordinates": [[[-90.15306303, 29.95606402], [-90.0495598, 29.95378523], [-90.0468903, 30.04391117],
                     [-90.15048687, 30.04619821], [-90.15306303, 29.95606402]]],
}
START, END = "2026-10-21T00:00:00Z", "2026-11-15T23:59:59Z"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
CREDS_URL = "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials"
SRC_BUCKET = "sds-n-cumulus-prod-nisar-products"
GRID = "/science/LSAR/GCOV/grids/frequencyA"


def log(msg):
    print(f"[nisar_crop] {msg}", flush=True)


def earthdata_login():
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret = json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])
    return secret["username"], secret["password"]


def s3_credentials(auth):
    # requests drops Authorization on cross-host redirects, so EDL login goes via a private netrc.
    with tempfile.TemporaryDirectory() as tmp:
        netrc = os.path.join(tmp, "netrc")
        with open(os.open(netrc, os.O_WRONLY | os.O_CREAT, 0o600), "w") as fh:
            fh.write(f"machine urs.earthdata.nasa.gov login {auth[0]} password {auth[1]}\n")
        os.environ["NETRC"] = netrc
        try:
            r = requests.Session().get(CREDS_URL, timeout=60)
        finally:
            os.environ.pop("NETRC", None)
    r.raise_for_status()
    return r.json()


def find_granules():
    w, s, e, n = shape(AOI).bounds
    r = requests.get(CMR, params={
        "short_name": "NISAR_L2_GCOV_V1", "bounding_box": f"{w},{s},{e},{n}",
        "temporal": f"{START},{END}", "page_size": 100,
    }, timeout=60)
    r.raise_for_status()
    out = []
    for item in r.json()["items"]:
        umm = item["umm"]
        gid = umm["GranuleUR"]
        if "_PR_" not in gid:
            continue
        rng = umm["TemporalExtent"]["RangeDateTime"]
        poly = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
        footprint = {"type": "Polygon", "coordinates": [[[p["Longitude"], p["Latitude"]] for p in poly]]}
        if not shape(footprint).intersects(shape(AOI)):
            continue
        out.append({"granule_id": gid, "start": rng["BeginningDateTime"], "stop": rng["EndingDateTime"],
                    "footprint": footprint})
    return out


def crop_pol(h5, pol, aoi_utm, epsg):
    grid = h5[GRID]
    x = grid["xCoordinates"][()]
    y = grid["yCoordinates"][()]
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])  # dy negative (north-up)
    w, s, e, n = aoi_utm.bounds
    c0 = max(int(np.floor((w - x[0]) / dx)), 0)
    c1 = min(int(np.ceil((e - x[0]) / dx)) + 1, len(x))
    r0 = max(int(np.floor((n - y[0]) / dy)), 0)
    r1 = min(int(np.ceil((s - y[0]) / dy)) + 1, len(y))
    if c0 >= c1 or r0 >= r1:
        return None
    data = grid[f"{pol}{pol}"][r0:r1, c0:c1].astype("float32")
    transform = from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy)
    outside = geometry_mask([mapping(aoi_utm)], out_shape=data.shape, transform=transform, all_touched=True)
    data[outside] = np.nan
    if not np.isfinite(data).any():
        return None
    return data, transform, abs(dx)


def write_cog(path, data, transform, epsg):
    profile = {"driver": "GTiff", "height": data.shape[0], "width": data.shape[1], "count": 1,
               "dtype": "float32", "crs": f"EPSG:{epsg}", "transform": transform, "nodata": np.nan,
               "compress": "deflate", "tiled": True, "blockxsize": 256, "blockysize": 256}
    tmp = path + ".tmp.tif"
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(1, units="linear power (gamma0)")
    with rasterio.open(tmp) as src:
        rasterio.shutil.copy(src, path, driver="COG", compress="DEFLATE")
    os.remove(tmp)


def main():
    t0 = time.time()
    s3 = boto3.client("s3", region_name=REGION)
    granules = find_granules()
    log(f"granules over AOI: {len(granules)}")
    if not granules:
        sys.exit(2)
    creds = s3_credentials(earthdata_login())
    fs = s3fs.S3FileSystem(key=creds["accessKeyId"], secret=creds["secretAccessKey"],
                           token=creds["sessionToken"], client_kwargs={"region_name": REGION},
                           default_block_size=4 * 1024 * 1024)
    index = []
    for g in granules:
        gid = g["granule_id"]
        src = f"{SRC_BUCKET}/NISAR_L2_GCOV_V1/{gid}/{gid}.h5"
        tg = time.time()
        try:
            with fs.open(src, "rb", cache_type="blockcache") as fh, h5py.File(fh, "r") as h5:
                grid = h5[GRID]
                epsg = int(grid["projection"].attrs["epsg_code"])
                to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
                aoi_utm = shp_transform(to_utm, shape(AOI))
                pols = [p.decode() if isinstance(p, bytes) else str(p) for p in grid["listOfPolarizations"][()]]
                ident = h5["/science/LSAR/identification"]

                def ident_val(k):
                    try:
                        v = ident[k][()]
                        return v.decode() if isinstance(v, bytes) else v.item() if hasattr(v, "item") else v
                    except KeyError:
                        return None

                assets, pixel = {}, None
                with tempfile.TemporaryDirectory() as tmp:
                    for pol in ("HH", "HV"):
                        if pol not in pols:
                            continue
                        res = crop_pol(h5, pol, aoi_utm, epsg)
                        if res is None:
                            continue
                        data, transform, pixel = res
                        local = os.path.join(tmp, f"{pol}.tif")
                        write_cog(local, data, transform, epsg)
                        key = f"nisar/gcov/{gid}/{pol}.tif"
                        s3.upload_file(local, BUCKET, key)
                        assets[pol] = {"key": key, "bytes": os.path.getsize(local),
                                       "width": data.shape[1], "height": data.shape[0]}
                if not assets:
                    log(f"{gid}: AOI outside valid data, skipped")
                    continue
                meta = {
                    "granule_id": gid, "acquired_start": g["start"], "acquired_stop": g["stop"],
                    "track": ident_val("trackNumber"), "frame": ident_val("frameNumber"),
                    "direction": ident_val("orbitPassDirection"), "polarizations": sorted(assets),
                    "footprint": g["footprint"], "aoi": {"name": AOI_NAME, "geometry": AOI},
                    "crs": f"EPSG:{epsg}", "pixel_size_m": pixel, "frequency": "A",
                    "units": "linear power (gamma0)", "assets": assets,
                    "source_url": f"s3://{src}",
                    "source_https": f"https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_V1/{gid}/{gid}.h5",
                    "processed_seconds": round(time.time() - tg, 1),
                }
                s3.put_object(Bucket=BUCKET, Key=f"nisar/gcov/{gid}/metadata.json",
                              Body=json.dumps(meta, indent=2).encode(), ContentType="application/json")
                index.append(meta)
                log(f"{gid}: {sorted(assets)} in {meta['processed_seconds']} s")
        except Exception as error:  # keep going with other granules
            log(f"{gid}: FAILED {type(error).__name__}: {error}")
    s3.put_object(Bucket=BUCKET, Key="nisar/gcov/index.json",
                  Body=json.dumps({"aoi": {"name": AOI_NAME, "geometry": AOI}, "start": START, "end": END,
                                   "scenes": index}, indent=2).encode(), ContentType="application/json")
    log(f"done: {len(index)} scenes in {round(time.time() - t0, 1)} s")


if __name__ == "__main__":
    main()
