import json
import uuid

import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer

from app.deps import get_settings
from app.main import app
from app.nisar_extractor import Inventory, ProductRecord
from app.services.estimate import human_bytes

ENDPOINT = "/api/estimate"
# Stored Harmony subset from a real run: 80 x 105 px, float32, LZW, 35820 B.
MEASURED_BYTES = 35_820
MEASURED_AOI = {
    "type": "Polygon",
    "coordinates": [
        [[-105.0048, 39.9952], [-104.9952, 39.9952], [-105.0, 40.0048], [-105.0048, 39.9952]]
    ],
}
BAD_GEOMETRIES = [
    {"type": "Point", "coordinates": [-105.0, 40.0]},
    # Self-intersecting polygons are repaired (make_valid), so they are no longer rejected.
    {"type": "Polygon", "coordinates": [[[-105, 39], [-104.99, 39], [-104.99, 95], [-105, 39]]]},
    {"type": "Polygon"},
    {"type": "Unknown", "coordinates": []},
]


def utm_rectangle(width_m: float, height_m: float) -> dict:
    """Polygon whose UTM 13N extent is width_m x height_m, starting on the zone's central meridian."""
    to_lonlat = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True)
    east, north = 500_000.0, 4_428_000.0
    corners = [
        (east, north),
        (east + width_m, north),
        (east + width_m, north + height_m),
        (east, north + height_m),
    ]
    ring = [list(to_lonlat.transform(x, y)) for x, y in corners]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The lifespan builds the real NisarExtractor under tmp_path. Estimate never touches the network.
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def post_estimate(client, **fields) -> dict:
    response = client.post(ENDPOINT, json=fields)
    assert response.status_code == 200, response.text
    return response.json()


def product(product_id: str, size: int | None) -> ProductRecord:
    return ProductRecord(
        product_id=product_id,
        producer_granule_id=product_id,
        cmr_granule_id="G0000000-ASF",
        collection_short_name="NISAR_L2_GCOV_V1",
        collection_concept_id="C0000000-ASF",
        product_type="GCOV",
        processing_configuration="PR",
        acquisition_start=None,
        acquisition_stop=None,
        geometry=MEASURED_AOI,
        size_mb_cmr=None,
        estimated_size_bytes=size,
    )


def save_inventory(tmp_path, products: list[ProductRecord]) -> str:
    inventory_id = uuid.uuid4().hex
    inventory = Inventory(query={}, region={}, products=products, queried_at_utc="2026-01-01T00:00:00Z")
    path = tmp_path / "data" / "inventories" / f"{inventory_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory.to_dict()))
    return inventory_id


def test_800_by_1050_m_is_near_measured_size(client):
    body = post_estimate(client, geometry=utm_rectangle(800, 1050))
    assert abs(body["per_file_bytes"] - MEASURED_BYTES) <= 0.10 * MEASURED_BYTES
    # The lon/lat box is about 0.1 m wider in UTM (meridian convergence), so ceil adds one pixel per axis.
    assert (body["pixels"]["width"], body["pixels"]["height"]) == (81, 106)
    assert body["full_granules_bytes"] is None


def test_measured_aoi_is_ceil_of_utm_extent(client):
    body = post_estimate(client, geometry=MEASURED_AOI)
    # UTM extent is 819.5 x 1065.5 m. Harmony returned 80 x 105 px (full pixels inside the box),
    # so ceil overshoots by 2 px per axis here.
    assert (body["pixels"]["width"], body["pixels"]["height"]) == (82, 107)
    assert abs(body["per_file_bytes"] - MEASURED_BYTES) <= 0.10 * MEASURED_BYTES
    assert body["bbox_km"]["width"] == pytest.approx(0.8195, abs=1e-4)
    assert body["bbox_km"]["height"] == pytest.approx(1.0655, abs=1e-4)


def test_total_is_per_file_times_variables_times_products(client):
    one = post_estimate(client, geometry=MEASURED_AOI)
    many = post_estimate(client, geometry=MEASURED_AOI, variables=3, products=2)
    assert many["per_file_bytes"] == one["per_file_bytes"]
    assert many["total_bytes"] == one["per_file_bytes"] * 3 * 2
    assert many["pixels"]["total"] == one["pixels"]["total"] * 3 * 2


@pytest.mark.parametrize("geometry", BAD_GEOMETRIES)
def test_bad_geometry_is_422(client, geometry):
    response = client.post(ENDPOINT, json={"geometry": geometry})
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["variables", "products", "spacing_m", "bytes_per_pixel"])
def test_non_positive_parameters_are_422(client, field):
    response = client.post(ENDPOINT, json={"geometry": MEASURED_AOI, field: 0})
    assert response.status_code == 422


def test_inventory_sets_product_count_and_full_granule_bytes(client, tmp_path):
    inventory_id = save_inventory(tmp_path, [product("P1", 12_500_000), product("P2", None)])
    body = post_estimate(client, geometry=MEASURED_AOI, inventory_id=inventory_id, products=9, variables=2)
    # Two products in the inventory, so the body's products=9 is ignored.
    assert body["total_bytes"] == body["per_file_bytes"] * 2 * 2
    # Product P2 has no CMR size and is left out of the sum.
    assert body["full_granules_bytes"] == 12_500_000


def test_empty_inventory_has_no_bytes(client, tmp_path):
    inventory_id = save_inventory(tmp_path, [])
    body = post_estimate(client, geometry=MEASURED_AOI, inventory_id=inventory_id)
    assert body["total_bytes"] == 0
    assert body["pixels"]["total"] == 0


def test_unknown_or_malformed_inventory(client):
    missing = client.post(ENDPOINT, json={"geometry": MEASURED_AOI, "inventory_id": "0" * 32})
    assert missing.status_code == 404
    traversal = client.post(ENDPOINT, json={"geometry": MEASURED_AOI, "inventory_id": "../secrets"})
    assert traversal.status_code == 400


@pytest.mark.parametrize(
    "value,text",
    [(1023, "1023 B"), (35_648, "34.8 KB"), (3 * 1024**3, "3.0 GB")],
)
def test_human_bytes(value, text):
    assert human_bytes(value) == text
