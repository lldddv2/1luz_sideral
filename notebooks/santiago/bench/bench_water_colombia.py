"""Probe NISAR GCOV, OPERA DSWx-S1 and JRC GSW over Colombian wetland/flood areas.

Reuses helpers from bench_water_layers.py. For each region, searches recent dates in
the GIBS time domain until NISAR tiles contain pixels, then looks for a DSWx-S1 date
nearby. Hard cap: 150 tiles total.
"""
import json, statistics, sys, time
from datetime import date, timedelta
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_water_layers import H, G, parse_caps, tiles_for, pixel_info  # noqa: E402

REGIONS = {
    "la_mojana": [-75.2, 8.2, -74.4, 9.0],
    "cienaga_grande_santa_marta": [-74.6, 10.6, -74.2, 11.1],
    "depresion_momposina": [-74.8, 8.9, -74.2, 9.4],
    "llanos_arauca_casanare": [-71.5, 5.5, -70.0, 6.8],
}
NISAR = "NISAR_L2_Geocoded_Polarimetric_Covariance"
DSWX = "OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1"
JRC = {"occurrence": "https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png",
       "change": "https://storage.googleapis.com/global-surface-water/tiles2021/change/{z}/{x}/{y}.png"}
BUDGET = 150
used = 0

def in_domain(ranges, d):
    for r in ranges:
        a, b, _ = r.split("/")
        if date.fromisoformat(a[:10]) <= d <= date.fromisoformat(b[:10]):
            return True
    return False

def domain_dates(ranges, end, n, step):
    out, d = [], end
    while len(out) < n and d > end - timedelta(days=400):
        if in_domain(ranges, d):
            out.append(d)
            d -= timedelta(days=step)
        else:
            d -= timedelta(days=1)
    return out

def get(url):
    global used
    used += 1
    t = time.perf_counter()
    for _ in range(3):
        try:
            r = requests.get(url, headers=H, timeout=30)
            break
        except requests.RequestException:
            r = None
            time.sleep(1.5)
    if r is None:
        return {"url": url, "error": "no response"}
    p = {"url": url, "status": r.status_code, "ms": round((time.perf_counter() - t) * 1000), "bytes": len(r.content)}
    if r.status_code == 200 and "image" in (r.headers.get("content-type") or ""):
        p.update(pixel_info(r.content))
    return p

def probe(urls):
    ps = [get(u) for u in urls]
    ms = [p["ms"] for p in ps if "ms" in p]
    return {"statuses": sorted({p.get("status") for p in ps if p.get("status")}),
            "ms_median": statistics.median(ms) if ms else None,
            "tiles_with_pixels": sum(1 for p in ps if p.get("has_pixels")), "n_tiles": len(ps), "probes": ps}

def gibs_urls(lid, caps, d, bbox, z, k):
    c = caps[lid]
    z = min(z, int(c["tms"].split("Level")[-1]))
    return [G.format(id=lid, d=d, tms=c["tms"], z=z, x=x, y=y) for x, y in tiles_for(bbox, z, k)]

def main():
    caps = parse_caps()
    res = {"nisar_ranges": caps[NISAR]["ranges"][-10:], "dswx_ranges_tail": caps[DSWX]["ranges"][-5:], "regions": {}}
    today = date(2026, 11, 14)
    nisar_dates = domain_dates(caps[NISAR]["ranges"], today, 7, 12)
    for name, bbox in REGIONS.items():
        reg = {"bbox": bbox, "nisar": [], "dswx": [], "jrc": {}}
        found = None
        for d in nisar_dates:
            if used + 3 > BUDGET:
                break
            pr = probe(gibs_urls(NISAR, caps, d.isoformat(), bbox, 8, 2))
            pr["date"] = d.isoformat()
            reg["nisar"].append(pr)
            print(name, "NISAR", d, pr["statuses"], pr["tiles_with_pixels"], "/", pr["n_tiles"])
            if pr["tiles_with_pixels"]:
                found = d
                break
        ref = found or nisar_dates[0]
        for off in [0, -1, 1, -2, 2, -4, 4, -6, 6]:
            d = ref + timedelta(days=off)
            if not in_domain(caps[DSWX]["ranges"], d) or used + 2 > BUDGET:
                continue
            pr = probe(gibs_urls(DSWX, caps, d.isoformat(), bbox, 8, 2))
            pr["date"] = d.isoformat()
            reg["dswx"].append(pr)
            print(name, "DSWx", d, pr["statuses"], pr["tiles_with_pixels"], "/", pr["n_tiles"])
            if pr["tiles_with_pixels"] or len(reg["dswx"]) >= 4:
                break
        for k, tpl in JRC.items():
            if used + 2 > BUDGET:
                break
            reg["jrc"][k] = probe([tpl.format(z=10, x=x, y=y) for x, y in tiles_for(bbox, 10, 2)])
            print(name, "JRC", k, reg["jrc"][k]["tiles_with_pixels"])
        reg["nisar_date_with_data"] = found.isoformat() if found else None
        hit = [p["date"] for p in reg["dswx"] if p["tiles_with_pixels"]]
        reg["dswx_date_with_data"] = hit[0] if hit else None
        res["regions"][name] = reg
    res["tiles_used"] = used
    out = Path(__file__).resolve().parent.parent / "bench_output" / "bench_water_colombia.json"
    json.dump(res, open(out, "w"), indent=1)
    print("tiles", used, "saved", out)

if __name__ == "__main__":
    main()
