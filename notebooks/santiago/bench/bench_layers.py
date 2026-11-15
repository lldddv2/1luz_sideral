"""Benchmark: probe keyless public GIS context layers for MapLibre (status, CORS, latency, size)."""
import json, math, statistics, time
import requests

LON, LAT = -105.0, 40.0  # Boulder test area (same as NISAR bench)
DATE = "2026-10-30"

def xy(z):
    n = 2 ** z
    x = int((LON + 180) / 360 * n)
    lr = math.radians(LAT)
    y = int((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n)
    return x, y

L = {
    # optical context
    "GIBS MODIS Terra truecolor (diario)": ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{d}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg", 9),
    "GIBS VIIRS NOAA20 truecolor (diario)": ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/{d}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg", 9),
    "GIBS HLS Sentinel-2 30m": ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/HLS_S30_Nadir_BRDF_Adjusted_Reflectance/default/{d}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.jpg", 12),
    "EOX Sentinel-2 cloudless 2016": ("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg", 13),
    "Esri World Imagery": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", 13),
    # thematic
    "JRC Global Surface Water occurrence": ("https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png", 12),
    "Hansen forest loss v1.11": ("https://storage.googleapis.com/earthenginepartners-hansen/tiles/gfc_v1.11/loss_alpha/{z}/{x}/{y}.png", 12),
    "ESA WorldCover 2021": ("https://services.terrascope.be/wmts/v2?layer=WORLDCOVER_2021_MAP&style=&tilematrixset=EPSG:3857&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/png&TileMatrix=EPSG:3857:{z}&TileCol={x}&TileRow={y}", 12),
    "GIBS VIIRS fire anomalies": ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_Thermal_Anomalies_375m_All/default/{d}/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png", 9),
    # terrain
    "Esri World Hillshade": ("https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}", 12),
    "AWS Terrarium DEM (raster-dem)": ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png", 12),
}
VEC = {
    "USGS sismos 30 días (GeoJSON)": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.geojson",
}
H = {"Origin": "http://localhost:5173", "User-Agent": "gis-layer-probe/0.1"}
res = {}
for name, (tpl, z) in L.items():
    x, y = xy(z)
    url = tpl.format(z=z, x=x, y=y, d=DATE)
    ts = []; out = {}
    for _ in range(3):
        t = time.perf_counter()
        try:
            r = requests.get(url, headers=H, timeout=20)
            ts.append((time.perf_counter() - t) * 1000)
            out = {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type"),
                   "cors": r.headers.get("access-control-allow-origin")}
        except Exception as e:
            out = {"error": type(e).__name__}
            break
    out["ms_median"] = round(statistics.median(ts), 0) if ts else None
    out["z"] = z
    res[name] = out
    print(f"{name:42} {json.dumps(out)}")
for name, url in VEC.items():
    t = time.perf_counter()
    r = requests.get(url, headers=H, timeout=30)
    d = r.json()
    res[name] = {"status": r.status_code, "bytes": len(r.content), "features": len(d.get("features", [])),
                 "cors": r.headers.get("access-control-allow-origin"), "ms": round((time.perf_counter() - t) * 1000)}
    print(f"{name:42} {json.dumps(res[name])}")
from pathlib import Path
json.dump(res, open(Path(__file__).resolve().parent.parent / "bench_output" / "bench_layers.json", "w"), indent=1)
