"""Benchmark: probe keyless water-related GIS layers over 2 water case areas.

Checks per layer/area: GIBS time-domain membership, HTTP status, latency, CORS and
whether tiles contain real (non-transparent) pixels. Max 4 tiles per layer per area.
"""
import io, json, math, re, statistics, time
from datetime import date
from pathlib import Path
import requests

try:
    from PIL import Image
except ImportError:
    Image = None

H = {"Origin": "http://localhost:5173", "User-Agent": "gis-layer-probe/0.1"}
CAPS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"
G = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{id}/default/{d}/{tms}/{z}/{y}/{x}.png"

AREAS = {
    # NISAR-published flood case (Jan 2026)
    "kruger_limpopo": {"bbox": [30.9, -25.5, 33.0, -22.3], "date": "2026-01-12"},
    # Mexico City subsidence = aquifer over-pumping; date inside NISAR >=2026-08-10 window
    "cdmx": {"bbox": [-99.30, 19.20, -98.90, 19.60], "date": "2026-10-01"},
}
# name: (gibs id or None, url template, zoom)
LAYERS = {
    "NISAR GCOV": ("NISAR_L2_Geocoded_Polarimetric_Covariance", None, 10),
    "OPERA DSWx-S1": ("OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1", None, 10),
    "OPERA DSWx-HLS": ("OPERA_L3_Dynamic_Surface_Water_Extent-HLS", None, 10),
    "OPERA RTC-S1": ("OPERA_L2_Radiometric_Terrain_Corrected_SAR_Sentinel-1", None, 10),
    "VIIRS Combined Flood 3-Day": ("VIIRS_Combined_Flood_3-Day", None, 8),
    "MODIS Combined Flood 3-Day": ("MODIS_Combined_Flood_3-Day", None, 8),
    "GRACE LWE mascon": ("GRACE_Tellus_Liquid_Water_Equivalent_Thickness_Mascon_CRI", None, 5),
    "GLDAS soil moisture (subsuelo)": ("GLDAS_Underground_Soil_Moisture_Monthly", None, 5),
    "JRC GSW occurrence": (None, "https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png", 10),
    "JRC GSW change": (None, "https://storage.googleapis.com/global-surface-water/tiles2021/change/{z}/{x}/{y}.png", 10),
}

def tile(lon, lat, z):
    n = 2 ** z
    lr = math.radians(lat)
    return int((lon + 180) / 360 * n), int((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n)

def tiles_for(bbox, z, k=4):
    w, s, e, n = bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    pts = [(cx, cy), ((w + cx) / 2, (s + cy) / 2), ((e + cx) / 2, (n + cy) / 2), ((w + cx) / 2, (n + cy) / 2)]
    out = []
    for p in pts:
        t = tile(*p, z)
        if t not in out:
            out.append(t)
    return out[:k]

def parse_caps():
    t = requests.get(CAPS, headers=H, timeout=60).text
    caps = {}
    for blk in re.findall(r"<Layer>(.*?)</Layer>", t, re.S):
        i = re.search(r"<ows:Identifier>(.*?)<", blk).group(1)
        tms = re.search(r"<TileMatrixSet>(.*?)<", blk)
        caps[i] = {"tms": tms.group(1) if tms else None, "ranges": re.findall(r"<Value>(.*?)</Value>", blk)}
    return caps

def pick_date(ranges, want):
    """Return (date_to_use, in_domain). Monthly/older layers fall back to nearest range end."""
    wd = date.fromisoformat(want)
    best = None
    for r in ranges:
        a, b, _ = r.split("/")
        a, b = date.fromisoformat(a[:10]), date.fromisoformat(b[:10])
        if a <= wd <= b:
            return want, True
        cand = b if b < wd else a
        if best is None or abs((cand - wd).days) < abs((best - wd).days):
            best = cand
    return (best.isoformat() if best else want), False

def pixel_info(content):
    if Image is None:
        return {"has_pixels": len(content) > 1500, "method": "size"}
    try:
        im = Image.open(io.BytesIO(content)).convert("RGBA")
        a = im.getchannel("A")
        opaque = sum(1 for v in a.tobytes() if v > 0)
        frac = opaque / (im.width * im.height)
        return {"has_pixels": frac > 0.001, "opaque_frac": round(frac, 3), "method": "PIL"}
    except Exception as ex:
        return {"has_pixels": False, "method": "PIL", "err": type(ex).__name__}

def main():
    caps = parse_caps()
    res = {"layers": {}}
    for name, (gid, tpl, z) in LAYERS.items():
        entry = {}
        if gid:
            c = caps.get(gid)
            entry["caps_found"] = bool(c)
            if not c:
                res["layers"][name] = entry
                continue
            entry["tms"], entry["ranges"] = c["tms"], c["ranges"]
            maxz = int(c["tms"].split("Level")[-1])
            z = min(z, maxz)
        for area, a in AREAS.items():
            d, ok = (pick_date(caps[gid]["ranges"], a["date"]) if gid and caps[gid]["ranges"] else (a["date"], None))
            probes = []
            for x, y in tiles_for(a["bbox"], z):
                url = G.format(id=gid, d=d, tms=caps[gid]["tms"], z=z, x=x, y=y) if gid else tpl.format(z=z, x=x, y=y)
                for attempt in range(3):  # GIBS drops some connections; retry briefly
                    t = time.perf_counter()
                    try:
                        r = requests.get(url, headers=H, timeout=30)
                        break
                    except requests.RequestException:
                        r = None
                        time.sleep(1.5)
                try:
                    if r is None:
                        raise ConnectionError("no response after 3 attempts")
                    p = {"status": r.status_code, "ms": round((time.perf_counter() - t) * 1000),
                         "bytes": len(r.content), "cors": r.headers.get("access-control-allow-origin")}
                    if r.status_code == 200 and "image" in (r.headers.get("content-type") or ""):
                        p.update(pixel_info(r.content))
                except Exception as ex:
                    p = {"error": type(ex).__name__}
                p["url"] = url
                probes.append(p)
            ms = [p["ms"] for p in probes if "ms" in p]
            entry[area] = {"date_used": d, "in_time_domain": ok, "z": z,
                           "statuses": sorted({p.get("status") for p in probes if p.get("status")}),
                           "ms_median": statistics.median(ms) if ms else None,
                           "tiles_with_pixels": sum(1 for p in probes if p.get("has_pixels")),
                           "n_tiles": len(probes),
                           "cors": sorted({str(p.get("cors")) for p in probes}),
                           "probes": probes}
            e = entry[area]
            print(f"{name:32} {area:15} {d} dom={ok} z={z} st={e['statuses']} ms={e['ms_median']} px={e['tiles_with_pixels']}/{e['n_tiles']} cors={e['cors']}")
        res["layers"][name] = entry
    out = Path(__file__).resolve().parent.parent / "bench_output" / "bench_water_layers.json"
    json.dump(res, open(out, "w"), indent=1)
    print("saved", out)

if __name__ == "__main__":
    main()
