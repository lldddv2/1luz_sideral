"""Benchmark: deliver NISAR GCOV rasters to MapLibre.
A  = single image (backend warps to EPSG:3857, encodes PNG/WebP) -> MapLibre `image` source (4 corners)
A0 = same but no warp (UTM corners straight to lon/lat) -> measure misregistration
B  = XYZ tiles from a COG (rio-tiler, like TiTiler) -> MapLibre `raster` source
"""
import glob, io, json, math, os, sys, time
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform as wtransform
from rasterio.io import MemoryFile
from PIL import Image

# Usage: python bench_overlay.py ../bench_output   (needs rasterio, rio-tiler, rio-cogeo, pillow)
ROOT = sys.argv[1]
OUT = {}

def to_u8(a, lo=None, hi=None):
    valid = np.isfinite(a) & (a > 0)
    db = np.full(a.shape, np.nan, np.float32)
    db[valid] = 10 * np.log10(a[valid])
    if lo is None:
        lo, hi = np.nanpercentile(db, [2, 98])
    u8 = np.clip((db - lo) / (hi - lo) * 254 + 1, 1, 255).astype(np.uint8)
    u8[~valid] = 0
    return u8, valid, float(lo), float(hi)

def enc(rgba, fmt, **kw):
    b = io.BytesIO(); t = time.perf_counter()
    Image.fromarray(rgba).save(b, fmt, **kw)
    return len(b.getvalue()), round((time.perf_counter() - t) * 1000, 1)

def gray_rgba(u8, valid):
    return np.dstack([u8, u8, u8, np.where(valid, 255, 0).astype(np.uint8)])

def option_a(path):
    r = {}
    with rasterio.open(path) as src:
        a = src.read(1); prof = src.profile
        r["src_px"] = list(a.shape); r["src_crs"] = str(src.crs)
        t0 = time.perf_counter()
        dst_t, w, h = calculate_default_transform(src.crs, "EPSG:3857", src.width, src.height, *src.bounds)
        dst = np.zeros((h, w), np.float32)
        reproject(a, dst, src_transform=src.transform, src_crs=src.crs, dst_transform=dst_t,
                  dst_crs="EPSG:3857", resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=0)
        r["warp_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        u8, valid, lo, hi = to_u8(dst)
        rgba = gray_rgba(u8, valid)
        r["out_px"] = [h, w]
        r["png"], r["png_ms"] = enc(rgba, "PNG", optimize=False)
        r["webp_lossless"], r["webp_ll_ms"] = enc(rgba, "WEBP", lossless=True)
        r["webp_q80"], r["webp_q80_ms"] = enc(rgba, "WEBP", quality=80)
        # A0 misregistration: corners of UTM footprint -> lon/lat, image stretched linearly in mercator.
        H, W = a.shape
        corners_px = [(0, 0), (W, 0), (W, H), (0, H)]
        cx, cy = zip(*[src.transform * p for p in corners_px])
        mx, my = wtransform(src.crs, "EPSG:3857", list(cx), list(cy))
        # sample grid of true positions vs bilinear quad interpolation
        us = np.linspace(0, 1, 21); err = 0.0
        for u in us:
            for v in us:
                tx, ty = src.transform * (u * W, v * H)
                X, Y = wtransform(src.crs, "EPSG:3857", [tx], [ty])
                qx = (1-u)*(1-v)*mx[0] + u*(1-v)*mx[1] + u*v*mx[2] + (1-u)*v*mx[3]
                qy = (1-u)*(1-v)*my[0] + u*(1-v)*my[1] + u*v*my[2] + (1-u)*v*my[3]
                lat = math.degrees(math.atan(math.sinh(Y[0] / 6378137)))
                err = max(err, math.hypot(X[0]-qx, Y[0]-qy) * math.cos(math.radians(lat)))
        r["no_warp_max_err_m"] = round(err, 2)
        r["pixel_m"] = abs(src.transform.a)
    return r

def option_b(path, tmpdir):
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles
    from rio_tiler.io import Reader
    import morecantile
    r = {}
    cog = os.path.join(tmpdir, "tmp_cog.tif")
    t = time.perf_counter()
    cog_translate(path, cog, cog_profiles.get("deflate"), quiet=True, web_optimized=False)
    r["cog_ms"] = round((time.perf_counter() - t) * 1000, 1)
    tms = morecantile.tms.get("WebMercatorQuad")
    with Reader(cog) as rdr:
        w, s, e, n = rdr.get_geographic_bounds("epsg:4326")
        # zoom that fits bbox in a 1100x800 map viewport (desktop, sidebar open)
        z = 0
        for zz in range(0, 19):
            tl = tms.xy(w, n); br = tms.xy(e, s)
            res = 2 * math.pi * 6378137 / (256 * 2 ** zz)
            if (br.x - tl.x) / res <= 1100 and (tl.y - br.y) / res <= 800:
                z = zz
        r["fit_zoom"] = z
        stats = rdr.statistics()
        b1 = list(stats.values())[0]
        tot_b = 0; tot_ms = 0; n_t = 0
        for zz in (z, z + 1, z + 2):  # initial view + 2 zoom-ins
            tiles = list(tms.tiles(w, s, e, n, [zz]))
            for tl in tiles:
                t0 = time.perf_counter()
                try:
                    img = rdr.tile(tl.x, tl.y, tl.z, tilesize=256)
                except Exception:
                    continue
                img.rescale(in_range=((b1.percentile_2, b1.percentile_98),))
                png = img.render(img_format="PNG")
                tot_ms += (time.perf_counter() - t0) * 1000; tot_b += len(png); n_t += 1
            if zz == z:
                r["tiles_initial"] = n_t; r["bytes_initial"] = tot_b; r["ms_initial"] = round(tot_ms, 1)
        r["tiles_3zooms"] = n_t; r["bytes_3zooms"] = tot_b; r["ms_3zooms"] = round(tot_ms, 1)
    os.remove(cog)
    return r

tmpdir = os.path.dirname(os.path.abspath(__file__))
for size in ["1.5km", "5km", "10km", "20km"]:
    p = [f for f in glob.glob(f"{ROOT}/extract_area_{size}/*HHHH*subsetted.tif") if "_masked" not in f][0]
    OUT[size] = {"A": option_a(p), "B": option_b(p, tmpdir), "tif_bytes": os.path.getsize(p)}
    print(size, json.dumps(OUT[size]))

# Time slider: 6 dates HH, 10 km
series = sorted(f for f in glob.glob(f"{ROOT}/extract_series_10km/*HHHH*subsetted.tif") if "_masked" not in f)
sa = [option_a(p) for p in series]
OUT["series_6dates_10km"] = {
    "A_webp_q80_total": sum(x["webp_q80"] for x in sa),
    "A_png_total": sum(x["png"] for x in sa),
    "A_warp_encode_ms_total": round(sum(x["warp_ms"] + x["webp_q80_ms"] for x in sa), 1),
    "B_bytes_initial_per_date": OUT["10km"]["B"]["bytes_initial"],
    "B_bytes_initial_6dates": OUT["10km"]["B"]["bytes_initial"] * len(series),
}
print(json.dumps(OUT["series_6dates_10km"]))
json.dump(OUT, open(os.path.join(ROOT, "bench_overlay.json"), "w"), indent=1)
