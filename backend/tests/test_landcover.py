import base64
import warnings

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from pyproj import Geod
from rasterio.errors import NotGeoreferencedWarning
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import shape

from app.main import app
from app.services import landcover

ENDPOINT = "/api/landcover"
GEOD = Geod(ellps="WGS84")
EARTH_KM2 = 510_065_621.724  # WGS84 ellipsoid surface area
BOX = {
    "type": "Polygon",
    "coordinates": [[[-105.3, 39.95], [-105.2, 39.95], [-105.2, 40.05], [-105.3, 40.05], [-105.3, 39.95]]],
}


def box_geojson(west, south, east, north):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def geodesic_km2(west, south, east, north):
    """Independent reference: pyproj geodesic area of the box."""
    area, _ = GEOD.geometry_area_perimeter(shape(box_geojson(west, south, east, north)))
    return abs(area) / 1e6


def synthetic_grid(codes: np.ndarray, aoi: dict, factor: int = 1) -> landcover.Grid:
    """Grid of class codes stretched over the AOI bounds. factor is the nominal decimation."""
    west, south, east, north = shape(aoi).bounds
    rows, cols = codes.shape
    transform = from_origin(west, north, (east - west) / cols, (north - south) / rows)
    inside = geometry_mask([aoi], out_shape=codes.shape, transform=transform, invert=True)
    return landcover.Grid(codes=codes.astype(np.uint8), inside=inside, transform=transform, factor=factor)


def write_tile(folder, name, west, north, res, data):
    path = folder / landcover.TILE_FILE.format(tile=name)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(west, north, res, res),
        nodata=0,
    ) as dst:
        dst.write(data, 1)


def decode_png(png_bytes: bytes) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile(png_bytes) as memfile, memfile.open() as ds:
            return ds.read()


@pytest.fixture(autouse=True)
def fresh_cache():
    landcover._cache.clear()
    yield
    landcover._cache.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def local_tiles(tmp_path, monkeypatch):
    """Two adjacent 3-degree tiles at 0.01-degree pixels, read from disk so GDAL runs offline.

    N39W108 (lon -108..-105): code 10 west of -105.25, else 90.
    N39W105 (lon -105..-102): code 30 west of -104.75, else 40.
    N42 tiles are not written, so they count as absent.
    """
    res = 0.01
    monkeypatch.setattr(landcover, "NATIVE_RES", res)
    monkeypatch.setattr(landcover, "TILE_PX", 300)
    monkeypatch.setattr(landcover, "BASE_URL", str(tmp_path))
    x = np.arange(300)
    west_tile = np.tile(np.where(x < 275, 10, 90), (300, 1)).astype(np.uint8)
    write_tile(tmp_path, "N39W108", -108, 42, res, west_tile)
    east_tile = np.tile(np.where(x < 25, 30, 40), (300, 1)).astype(np.uint8)
    write_tile(tmp_path, "N39W105", -105, 42, res, east_tile)
    return tmp_path


def test_classes_endpoint_lists_eleven_classes(client):
    response = client.get(f"{ENDPOINT}/classes")
    assert response.status_code == 200
    classes = response.json()
    assert [c["code"] for c in classes] == [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
    assert len({c["key"] for c in classes}) == 11
    assert all(c["color"].startswith("#") and len(c["color"]) == 7 for c in classes)
    wetland = next(c for c in classes if c["key"] == "wetland")
    assert wetland == {
        "code": 90,
        "key": "wetland",
        "name": "Humedal herbáceo",
        "name_en": "Herbaceous wetland",
        "color": "#0096a0",
    }


def test_tile_names_use_lower_left_corner():
    assert landcover.tile_name(39, -108) == "N39W108"
    assert landcover.tile_name(-3, 0) == "S03E000"
    assert landcover.tile_name(0, 0) == "N00E000"
    assert landcover.tile_name(-60, 150) == "S60E150"


def test_cell_area_matches_geodesic_and_earth_total():
    assert float(landcover.cell_area_km2(90, -90, 360)) == pytest.approx(EARTH_KM2, rel=1e-8)
    expected = geodesic_km2(-105.3, 39.95, -105.2, 40.05)
    assert float(landcover.cell_area_km2(40.05, 39.95, 0.1)) == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize(
    ("max_px", "long_side", "factor"),
    [(1200, 1200, 1), (1024, 600, 2), (100, 100, 12), (16, 16, 75)],
)
def test_plan_decimates_to_fit_max_px(max_px, long_side, factor):
    plan = landcover._plan(-105.30, 39.95, -105.20, 40.05, max_px)
    assert plan.factor == factor
    assert (plan.row1 - plan.row0) // plan.factor == long_side
    assert (plan.col1 - plan.col0) // plan.factor == long_side
    assert landcover.TILE_PX % plan.factor == 0


def test_boulder_aoi_reads_one_tile():
    plan = landcover._plan(-105.30, 39.95, -105.20, 40.05, 1024)
    reads = list(landcover._tile_reads(plan))
    assert [name for name, *_ in reads] == ["N39W108"]
    name, window, out_shape, offset = reads[0]
    assert (window.col_off, window.row_off, window.width, window.height) == (32400, 23400, 1200, 1200)
    assert out_shape == (600, 600) and offset == (0, 0)


def test_stats_percent_area_and_nodata(client, monkeypatch):
    codes = np.full((1200, 1200), 10, dtype=np.uint8)
    codes[:, 600:] = 90  # east half wetland
    codes[:100, :] = 0  # top band without data
    grid = synthetic_grid(codes, BOX)
    monkeypatch.setattr(landcover, "read_window", lambda geometry, max_px: grid)

    response = client.post(f"{ENDPOINT}/stats", json={"geometry": BOX})
    assert response.status_code == 200
    body = response.json()
    by_key = {c["key"]: c for c in body["classes"]}
    assert len(body["classes"]) == 11
    assert body["resolution_m"] == 10.0
    assert sum(c["percent"] for c in body["classes"]) == pytest.approx(100.0, abs=1e-3)
    assert by_key["tree"]["pixels"] == 600 * 1100
    assert by_key["wetland"]["pixels"] == 600 * 1100
    assert by_key["tree"]["percent"] == pytest.approx(50.0, abs=1e-3)
    grassland = by_key["grassland"]
    assert (grassland["pixels"], grassland["area_km2"], grassland["percent"]) == (0, 0.0, 0.0)

    band_top = 40.05 - 100 * landcover.NATIVE_RES
    valid_km2 = float(landcover.cell_area_km2(band_top, 39.95, 0.1))
    assert body["total_km2"] == pytest.approx(valid_km2, abs=1e-6)  # service rounds to 6 decimals
    assert body["total_km2"] == pytest.approx(geodesic_km2(-105.3, 39.95, -105.2, band_top), rel=1e-3)
    assert body["nodata_km2"] == pytest.approx(geodesic_km2(-105.3, band_top, -105.2, 40.05), rel=1e-2)
    tree_west = geodesic_km2(-105.3, 39.95, -105.25, band_top)
    assert by_key["tree"]["area_km2"] == pytest.approx(tree_west, rel=1e-3)


def test_stats_decimated_grid_scales_pixels_and_resolution(client, monkeypatch):
    codes = np.full((400, 400), 90, dtype=np.uint8)  # 1200 native pixels per side, 3x3 blocks
    grid = synthetic_grid(codes, BOX, factor=3)
    monkeypatch.setattr(landcover, "read_window", lambda geometry, max_px: grid)

    body = client.post(f"{ENDPOINT}/stats", json={"geometry": BOX}).json()
    wetland = next(c for c in body["classes"] if c["key"] == "wetland")
    assert body["resolution_m"] == 30.0
    assert wetland["pixels"] == 1200 * 1200
    assert wetland["percent"] == pytest.approx(100.0)
    assert body["total_km2"] == pytest.approx(geodesic_km2(-105.3, 39.95, -105.2, 40.05), rel=1e-3)


def test_mask_draws_selected_class_only_inside_aoi(client, monkeypatch):
    ring = [[-105.3, 39.95], [-105.2, 39.95], [-105.3, 40.05], [-105.3, 39.95]]
    triangle = {"type": "Polygon", "coordinates": [ring]}
    codes = np.full((1200, 1200), 10, dtype=np.uint8)
    codes[:, 600:] = 90
    grid = synthetic_grid(codes, triangle)
    monkeypatch.setattr(landcover, "read_window", lambda geometry, max_px: grid)

    body_in = {"geometry": triangle, "classes": ["wetland"], "max_px": 1024}
    response = client.post(f"{ENDPOINT}/mask", json=body_in)
    assert response.status_code == 200
    body = response.json()
    assert body["width"] == 1200 and body["height"] == 1200
    assert body["bounds"] == grid.bounds()

    rgba = decode_png(base64.b64decode(body["png_base64"]))
    assert rgba.shape == (4, 1200, 1200)
    opaque = rgba[3] == 255
    assert np.array_equal(opaque, grid.inside & (codes == 90))
    assert tuple(rgba[:3, opaque][:, 0]) == (0, 150, 160)


def test_mask_without_classes_draws_every_class(client, monkeypatch):
    codes = np.full((100, 100), 10, dtype=np.uint8)
    codes[:, 50:] = 80
    grid = synthetic_grid(codes, BOX)
    monkeypatch.setattr(landcover, "read_window", lambda geometry, max_px: grid)

    body = client.post(f"{ENDPOINT}/mask", json={"geometry": BOX}).json()
    rgba = decode_png(base64.b64decode(body["png_base64"]))
    assert rgba.shape == (4, 100, 100)
    assert np.all(rgba[3] == 255)  # both classes and the full box are opaque
    assert tuple(rgba[:3, 0, 0]) == (0, 100, 0)  # tree
    assert tuple(rgba[:3, 0, 99]) == (0, 100, 200)  # water


def test_unknown_class_key_is_422_before_any_read(client, monkeypatch):
    def no_read(*args):
        raise AssertionError("read must not run for a bad request")

    monkeypatch.setattr(landcover, "read_window", no_read)
    response = client.post(f"{ENDPOINT}/mask", json={"geometry": BOX, "classes": ["forest"]})
    assert response.status_code == 422
    assert "forest" in response.json()["detail"]


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-105.0, 40.0]},
        {"type": "Polygon", "coordinates": [[[-105, 39], [-104.99, 40], [-104.99, 39], [-105, 40], [-105, 39]]]},
        {"type": "Polygon", "coordinates": [[[-105, 39], [-104.99, 39], [-104.99, 95], [-105, 39]]]},
        {"type": "Feature", "properties": {}},
        {"type": "Foo", "coordinates": []},
        {"type": "Polygon"},
    ],
)
def test_bad_geometry_is_422(client, geometry):
    assert client.post(f"{ENDPOINT}/stats", json={"geometry": geometry}).status_code == 422


def test_aoi_over_limit_is_422(client):
    response = client.post(f"{ENDPOINT}/stats", json={"geometry": box_geojson(-30, -30, 30, 30)})
    assert response.status_code == 422
    assert "limit" in response.json()["detail"]


def test_unreadable_tile_is_502(client, monkeypatch):
    def broken(name, window, out_shape):
        message = f"WorldCover tile {name} unreadable: HTTP response code: 503"
        raise landcover.LandcoverUnavailableError(message)

    monkeypatch.setattr(landcover, "_read_tile", broken)
    response = client.post(f"{ENDPOINT}/stats", json={"geometry": BOX})
    assert response.status_code == 502
    assert "503" in response.json()["detail"]


def test_read_window_is_cached_per_geometry_and_max_px(monkeypatch):
    calls = []

    def fake_read(aoi, max_px):
        calls.append(max_px)
        return synthetic_grid(np.full((4, 4), 10, dtype=np.uint8), BOX)

    monkeypatch.setattr(landcover, "_read_grid", fake_read)
    first = landcover.read_window(BOX, 1024)
    assert landcover.read_window(BOX, 1024) is first
    landcover.read_window(BOX, 512)
    assert calls == [1024, 512]


def test_tiles_stitch_across_boundary(local_tiles):
    body = landcover.stats(box_geojson(-105.5, 39.5, -104.5, 40.5))
    pixels = {c["code"]: c["pixels"] for c in body["classes"]}
    # Each quarter of the 100 x 100 native grid is 25 columns wide.
    assert pixels == {10: 2500, 90: 2500, 30: 2500, 40: 2500, **{c: 0 for c in (20, 50, 60, 70, 80, 95, 100)}}
    assert body["nodata_km2"] == 0.0
    assert body["total_km2"] == pytest.approx(float(landcover.cell_area_km2(40.5, 39.5, 1.0)), rel=1e-9)


def test_decimated_stitch_covers_both_tiles(local_tiles, monkeypatch):
    # 2x2 native blocks; the tile boundary falls inside one block.
    monkeypatch.setattr(landcover, "STATS_MAX_PX", 50)
    body = landcover.stats(box_geojson(-105.5, 39.5, -104.5, 40.5))
    pixels = {c["code"]: c["pixels"] for c in body["classes"]}
    assert body["resolution_m"] == 20.0
    assert sum(pixels.values()) == 10_000
    # Nearest sampling moves each class by at most one output column (4 native px x 50 rows).
    assert all(abs(pixels[code] - 2500) <= 200 for code in (10, 90, 30, 40))
    assert body["total_km2"] == pytest.approx(float(landcover.cell_area_km2(40.5, 39.5, 1.0)), rel=1e-9)


def test_missing_tile_counts_as_nodata(local_tiles):
    body = landcover.stats(box_geojson(-105.5, 41.5, -104.5, 42.5))  # north half lies in absent N42 tiles
    assert body["nodata_km2"] == pytest.approx(float(landcover.cell_area_km2(42.5, 42.0, 1.0)), rel=1e-6)
    assert body["total_km2"] == pytest.approx(float(landcover.cell_area_km2(42.0, 41.5, 1.0)), rel=1e-6)
    assert sum(c["percent"] for c in body["classes"]) == pytest.approx(100.0, abs=1e-3)


def test_mask_png_from_local_tiles_is_transparent_outside_aoi(local_tiles):
    aoi = box_geojson(-105.5, 39.5, -104.5, 40.5)
    body = landcover.mask(aoi, ["moss"], 1024)  # moss is absent here, so nothing is drawn
    rgba = decode_png(base64.b64decode(body["png_base64"]))
    assert rgba.shape == (4, 100, 100)
    assert not np.any(rgba[3])
    assert body["bounds"] == [[-105.5, 40.5], [-104.5, 40.5], [-104.5, 39.5], [-105.5, 39.5]]
