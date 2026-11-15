"""Build app/data/features.json: a small global catalog of natural features.

Sources: Natural Earth 10m (public domain) geography_regions_polys and glaciated_areas,
plus a hand-picked list of well-known forests, jungles, mangroves, wetlands and volcanoes.

Usage: python -I scripts/build_features.py <dir with the Natural Earth geojson files>
"""

import json
import math
import re
import sys
import unicodedata
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "features.json"

# Natural Earth FEATURECLA -> category key.
NE_CLASSES = {"Desert": "desert", "Tundra": "tundra", "Wetlands": "wetland", "Delta": "wetland"}

# Natural Earth entries whose class does not fit the catalog.
SKIP = {"Entre Ríos", "Punyab", "Escudo Canadiense", "Big Bend", "Meandro de Ordos"}

# Hand-picked features: (name, category, west, south, east, north).
MANUAL = [
    # Tropical forests (selvas)
    ("Amazonía", "jungle", -79.0, -17.0, -44.0, 5.5),
    ("Cuenca del Congo", "jungle", 12.0, -6.0, 31.0, 5.0),
    ("Selva de Borneo", "jungle", 108.8, -4.2, 119.3, 7.0),
    ("Selva de Nueva Guinea", "jungle", 131.0, -9.0, 150.5, -0.5),
    ("Chocó biogeográfico", "jungle", -79.5, 1.0, -76.0, 8.5),
    ("Selva Lacandona", "jungle", -91.7, 16.0, -90.3, 17.3),
    ("Bosque Atlántico", "jungle", -55.0, -30.0, -35.0, -6.0),
    ("Selva de Daintree", "jungle", 145.0, -16.6, 145.6, -15.8),
    ("Selva de Sumatra", "jungle", 95.0, -6.0, 106.0, 6.0),
    ("Selva Maya", "jungle", -91.5, 16.0, -88.0, 19.5),
    # Forests (bosques)
    ("Taiga siberiana", "forest", 60.0, 50.0, 140.0, 67.0),
    ("Bosque boreal canadiense", "forest", -125.0, 48.0, -60.0, 62.0),
    ("Selva Negra", "forest", 7.6, 47.6, 8.9, 49.0),
    ("Bosque de Białowieża", "forest", 23.5, 52.5, 24.2, 52.9),
    ("Bosque lluvioso templado del Pacífico", "forest", -134.0, 43.0, -122.0, 58.0),
    ("Bosque valdiviano", "forest", -74.5, -44.0, -71.5, -37.5),
    ("Bosques de Tasmania", "forest", 144.5, -43.6, 148.4, -40.7),
    ("Bosque de Yungas", "forest", -66.0, -27.0, -63.5, -21.0),
    ("Sierra Nevada de Santa Marta", "forest", -74.3, 10.5, -73.2, 11.4),
    # Mangroves (manglares)
    ("Sundarbans", "mangrove", 88.0, 21.5, 89.9, 22.6),
    ("Manglares del Delta del Níger", "mangrove", 4.5, 4.2, 8.0, 6.0),
    ("Ciénaga Grande de Santa Marta", "mangrove", -74.9, 10.6, -74.2, 11.1),
    ("Manglares de Marismas Nacionales", "mangrove", -105.9, 21.5, -105.2, 22.7),
    ("Manglares de Bhitarkanika", "mangrove", 86.7, 20.4, 87.1, 20.9),
    ("Manglares de los Everglades", "mangrove", -81.9, 24.9, -80.6, 25.9),
    ("Manglares del Golfo de Guayaquil", "mangrove", -80.5, -3.5, -79.7, -2.0),
    # Wetlands (humedales)
    ("Pantanal", "wetland", -58.5, -22.0, -54.8, -15.5),
    ("Delta del Okavango", "wetland", 22.0, -20.0, 24.0, -18.2),
    ("Sudd", "wetland", 29.5, 6.0, 32.0, 9.8),
    ("Everglades", "wetland", -81.4, 25.1, -80.3, 26.7),
    ("Esteros del Iberá", "wetland", -57.9, -28.8, -56.5, -27.6),
    ("Llanos de Moxos", "wetland", -67.0, -16.0, -63.0, -12.0),
    ("Doñana", "wetland", -6.6, 36.8, -6.1, 37.2),
    ("Camargue", "wetland", 4.1, 43.3, 4.9, 43.7),
    ("Pantanos de Vasyugan", "wetland", 75.0, 55.5, 83.5, 58.5),
    ("Delta del Danubio", "wetland", 28.6, 44.7, 29.8, 45.5),
    ("Humedales de Mesopotamia", "wetland", 46.0, 30.5, 48.0, 32.0),
    ("Llanos del Orinoco", "wetland", -72.0, 6.0, -66.0, 8.5),
    ("Depresión Momposina", "wetland", -75.2, 8.3, -73.8, 9.5),
    # Glaciers (glaciares)
    ("Campo de Hielo Patagónico Sur", "glacier", -74.0, -51.6, -72.8, -48.3),
    ("Campo de Hielo Patagónico Norte", "glacier", -74.0, -47.6, -73.0, -46.4),
    ("Glaciar Perito Moreno", "glacier", -73.4, -50.6, -72.9, -50.4),
    ("Vatnajökull", "glacier", -18.2, 63.9, -15.3, 65.0),
    ("Glaciar de Aletsch", "glacier", 7.9, 46.4, 8.1, 46.6),
    ("Glaciar Jakobshavn", "glacier", -50.5, 68.9, -48.5, 69.4),
    ("Glaciar Baltoro", "glacier", 76.2, 35.6, 76.8, 35.9),
    ("Glaciar Siachen", "glacier", 76.8, 35.2, 77.4, 35.7),
    ("Glaciar Columbia (Alaska)", "glacier", -147.3, 60.9, -146.6, 61.4),
    ("Glaciar Thwaites", "glacier", -110.0, -76.0, -104.0, -74.5),
    ("Nevado del Ruiz (glaciar)", "glacier", -75.4, 4.8, -75.2, 5.0),
    ("Glaciar Pastoruri", "glacier", -77.3, -10.0, -77.1, -9.8),
    ("Kilimanjaro (glaciares)", "glacier", 37.25, -3.15, 37.45, -3.0),
]

# Rough outlines (lon, lat rings, 8-20 points) for the larger hand-picked features;
# the rest of MANUAL keep their bbox as a rectangle.
OUTLINES = {
    "Amazonía": [(-79, -2), (-77, 2), (-72, 4.5), (-66, 5.5), (-60, 5), (-55, 3), (-51, 2), (-48, -1), (-44, -2.5),
                 (-46, -6), (-50, -10), (-56, -13), (-62, -14), (-66, -17), (-69, -15), (-73, -11), (-76, -7), (-78, -4)],
    "Cuenca del Congo": [(12, -2), (13, 2), (15, 4), (19, 5), (24, 4.5), (28, 4), (31, 2), (30, -2), (28, -5),
                         (24, -6), (19, -5), (15, -5), (12.5, -4)],
    "Bosque Atlántico": [(-35, -6), (-35.5, -9), (-37.5, -12), (-39, -15), (-39.8, -19), (-41, -22.5), (-44, -23.5),
                         (-47.5, -25.5), (-48.5, -28.5), (-50, -30), (-53, -29), (-55, -27), (-54, -24), (-50, -22),
                         (-46, -19), (-42, -15), (-39, -11), (-36.5, -8)],
    "Taiga siberiana": [(60, 56), (63, 61), (70, 64), (82, 66), (100, 67), (115, 66), (130, 64), (140, 62),
                        (138, 55), (130, 52), (115, 51), (100, 52), (85, 54), (72, 55)],
    "Bosque boreal canadiense": [(-125, 58), (-120, 61), (-110, 62), (-100, 60), (-92, 57), (-82, 55), (-75, 57),
                                 (-65, 55), (-60, 52), (-66, 48), (-76, 47), (-85, 48), (-95, 50), (-105, 54), (-115, 54)],
    "Bosque lluvioso templado del Pacífico": [(-124.5, 43), (-124.5, 47), (-125, 50), (-128, 52), (-131, 54.5),
                                              (-134, 57), (-134, 58), (-132, 58), (-128, 55), (-125, 52), (-122.5, 49),
                                              (-122, 45), (-122.5, 43)],
    "Pantanal": [(-58, -16), (-56, -15.5), (-55, -17), (-54.8, -19), (-55.5, -21), (-57, -22), (-58.3, -20.5),
                 (-58.5, -18)],
    "Selva de Borneo": [(109, 1.5), (110, -1), (111, -3), (114, -4), (116.5, -3.5), (117.5, -1), (118.5, 1),
                        (119, 4.5), (117.5, 7), (115, 5), (113, 3.3), (111, 2)],
    "Selva de Sumatra": [(95.2, 5.6), (97.5, 5.2), (100.2, 2.5), (103.5, 0), (106, -3), (105.8, -5.8),
                         (104.5, -5.8), (102.3, -4), (100.2, -1), (98.6, 1.7), (96.3, 3.6)],
    "Selva de Nueva Guinea": [(131, -1.2), (134, -0.8), (138, -1.6), (141, -2.6), (145, -4), (147.5, -6),
                              (150.5, -10.5), (147, -9), (144, -7.8), (141, -9), (138, -8.4), (137.5, -5), (133.5, -4)],
    "Sundarbans": [(88.05, 21.6), (88.3, 22.15), (88.8, 22.4), (89.5, 22.45), (89.9, 22.1), (89.7, 21.7),
                   (89.0, 21.55)],
}

# Volcanoes (volcanes): (name, lon, lat)

VOLCANOES = [
    ("Kīlauea", -155.29, 19.41),
    ("Mauna Loa", -155.61, 19.48),
    ("Etna", 14.99, 37.75),
    ("Vesubio", 14.43, 40.82),
    ("Popocatépetl", -98.62, 19.02),
    ("Volcán de Fuego", -90.88, 14.47),
    ("Nevado del Ruiz", -75.32, 4.89),
    ("Galeras", -77.37, 1.22),
    ("Cotopaxi", -78.44, -0.68),
    ("Tungurahua", -78.44, -1.47),
    ("Villarrica", -71.93, -39.42),
    ("Monte Santa Helena", -122.18, 46.19),
    ("Monte Fuji", 138.73, 35.36),
    ("Merapi", 110.44, -7.54),
    ("Krakatoa", 105.42, -6.10),
    ("Pinatubo", 120.35, 15.13),
    ("Taal", 120.99, 14.01),
    ("Erta Ale", 40.67, 13.60),
    ("Nyiragongo", 29.25, -1.52),
    ("Eyjafjallajökull", -19.61, 63.63),
    ("Fagradalsfjall", -22.27, 63.90),
    ("Cumbre Vieja (La Palma)", -17.84, 28.57),
    ("Teide", -16.64, 28.27),
    ("Klyuchevskoy", 160.64, 56.06),
    ("Sakurajima", 130.66, 31.58),
    ("Piton de la Fournaise", 55.71, -21.24),
    ("Erebus", 167.17, -77.53),
    ("Hunga Tonga", -175.39, -20.55),
]


def bbox_of(geom):
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return [min(xs), min(ys), max(xs), max(ys)]


TOLERANCE = 0.05  # degrees (~5 km), keeps big NE regions to a few hundred points


def slug(name):
    text = unicodedata.normalize("NFD", name.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def simplify(geom):
    g = shape(geom) if isinstance(geom, dict) else geom
    g = g.buffer(0) if not g.is_valid else g
    s = g.simplify(TOLERANCE, preserve_topology=True)
    if s.is_empty:
        s = g.envelope
    s = orient(s) if s.geom_type == "Polygon" else s
    m = mapping(s)

    def rnd(c):
        return [round(c[0], 3), round(c[1], 3)] if isinstance(c[0], (int, float)) else [rnd(x) for x in c]

    return {"type": m["type"], "coordinates": rnd(m["coordinates"])}


def entry(name, category, bbox, source, geometry=None):
    w, s, e, n = (round(v, 4) for v in bbox)
    return {
        "id": slug(name),
        "name": name,
        "category": category,
        "lon": round((w + e) / 2, 4),
        "lat": round((s + n) / 2, 4),
        "bbox": [w, s, e, n],
        "source": source,
        "geometry": geometry or {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]},
    }


def main(ne_dir: Path) -> None:
    out = []
    regions = json.loads((ne_dir / "ne_10m_geography_regions_polys.geojson").read_text())
    for f in regions["features"]:
        p = f["properties"]
        cat = NE_CLASSES.get(p["FEATURECLA"])
        if not cat or not f["geometry"]:
            continue
        name = p.get("NAME_ES") or p["NAME"]
        if name.isupper():
            name = name.title()
        if name in SKIP:
            continue
        out.append(entry(name, cat, bbox_of(f["geometry"]), "Natural Earth", simplify(f["geometry"])))
    glaciers = json.loads((ne_dir / "ne_10m_glaciated_areas.geojson").read_text())
    for f in glaciers["features"]:
        name = f["properties"].get("name")
        if name and f["geometry"]:
            out.append(entry(name.title(), "glacier", bbox_of(f["geometry"]), "Natural Earth", simplify(f["geometry"])))
    for name, cat, w, s, e, n in MANUAL:
        ring = OUTLINES.get(name)
        geom = simplify({"type": "Polygon", "coordinates": [ring + ring[:1]]}) if ring else None
        out.append(entry(name, cat, (w, s, e, n), "curated", geom))
    for name, lon, lat in VOLCANOES:
        # ~15 km radius circle (longitude stretched by latitude).
        k = 1 / max(math.cos(math.radians(lat)), 0.2)
        ring = [(round(lon + 0.135 * k * math.cos(a * math.pi / 8), 3), round(lat + 0.135 * math.sin(a * math.pi / 8), 3))
                for a in range(16)]
        geom = {"type": "Polygon", "coordinates": [[list(p) for p in ring + ring[:1]]]}
        out.append(entry(name, "volcano", (lon - 0.135 * k, lat - 0.135, lon + 0.135 * k, lat + 0.135), "curated", geom))
    # Drop duplicate names (Natural Earth repeats some), keep the first.
    seen, unique = set(), []
    for item in out:
        key = item["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    OUT.write_text(json.dumps(unique, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(unique)} features -> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
