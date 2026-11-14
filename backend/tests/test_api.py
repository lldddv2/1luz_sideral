import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_extractor, get_settings
from app.main import app
from app.nisar_extractor import Inventory, ProductRecord
from app.nisar_extractor.geometry import region_to_record

VARIABLE = "/science/LSAR/GCOV/grids/frequencyA/HHHH"
PRODUCT_ID = "NISAR_FAKE_PRODUCT_001"
START = "2026-01-01T00:00:00Z"
END = "2026-02-01T00:00:00Z"
AOI = {
    "type": "Polygon",
    "coordinates": [
        [[-105.0, 39.99], [-104.99, 39.99], [-104.99, 40.0], [-105.0, 40.0], [-105.0, 39.99]]
    ],
}


class FakeExtractor:
    """Stands in for NisarExtractor. Never touches ASF, CMR or Harmony."""

    def __init__(self) -> None:
        self.extract_calls: list[dict] = []

    def discover(
        self,
        region,
        *,
        start,
        stop,
        product_type="GCOV",
        production_configuration="PR",
        max_results=10,
        inventory_path=None,
    ):
        product = ProductRecord(
            product_id=PRODUCT_ID,
            producer_granule_id=PRODUCT_ID,
            cmr_granule_id="G0000000-ASF",
            collection_short_name="NISAR_L2_GCOV_V1",
            collection_concept_id="C0000000-ASF",
            product_type=product_type,
            processing_configuration=production_configuration,
            acquisition_start=start,
            acquisition_stop=stop,
            geometry=region.geometry.__geo_interface__,
            size_mb_cmr=12.5,
            estimated_size_bytes=12_500_000,
            variables=[{"name": VARIABLE, "concept_id": "V0000000-ASF"}],
        )
        inventory = Inventory(
            query={"dataset": "NISAR", "result_count": 1},
            region=region_to_record(region),
            products=[product],
            queried_at_utc="2026-01-01T00:00:00Z",
        )
        if inventory_path:
            Path(inventory_path).parent.mkdir(parents=True, exist_ok=True)
            Path(inventory_path).write_text(json.dumps(inventory.to_dict()))
        return inventory

    def extract(self, inventory, *, product_ids, variables, output_crs=None, reuse_job_id=None):
        self.extract_calls.append(
            {"product_ids": product_ids, "variables": variables, "output_crs": output_crs}
        )
        return [{"product_id": pid, "state": "downloaded", "outputs": []} for pid in product_ids]


@pytest.fixture
def fake_extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def client(tmp_path, monkeypatch, fake_extractor):
    # The lifespan builds the real NisarExtractor, but only under tmp_path. No network I/O.
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    app.dependency_overrides[get_extractor] = lambda: fake_extractor
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def search_body(geometry=AOI):
    return {"geometry": geometry, "start": START, "end": END}


def job_body(inventory_id, product_ids=(PRODUCT_ID,), variables=(VARIABLE,)):
    return {"inventory_id": inventory_id, "product_ids": list(product_ids), "variables": list(variables)}


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_products_and_inventory_id(client):
    response = client.post("/api/search", json=search_body())
    assert response.status_code == 200
    body = response.json()
    assert len(body["inventory_id"]) == 32
    assert [product["product_id"] for product in body["products"]] == [PRODUCT_ID]
    assert body["products"][0]["variables"] == [{"name": VARIABLE, "concept_id": "V0000000-ASF"}]


def test_search_rejects_non_polygon_aoi(client):
    point = {"type": "Point", "coordinates": [-105.0, 40.0]}
    response = client.post("/api/search", json=search_body(point))
    assert response.status_code == 400


def test_search_rejects_unknown_geojson_type(client):
    unknown = {"type": "Foo", "coordinates": []}
    response = client.post("/api/search", json=search_body(unknown))
    assert response.status_code == 422


def test_job_runs_extract_in_background(client, fake_extractor):
    inventory_id = client.post("/api/search", json=search_body()).json()["inventory_id"]
    response = client.post("/api/jobs", json=job_body(inventory_id))
    assert response.status_code == 202
    assert response.json()["state"] == "queued"
    job_id = response.json()["id"]

    # TestClient runs background tasks before it returns, so the job is already finished here.
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["state"] == "done"
    assert job["results"] == [{"product_id": PRODUCT_ID, "state": "downloaded", "outputs": []}]
    assert fake_extractor.extract_calls == [
        {"product_ids": [PRODUCT_ID], "variables": [VARIABLE], "output_crs": None}
    ]
    assert [item["id"] for item in client.get("/api/jobs").json()] == [job_id]


def test_job_rejects_product_not_in_inventory(client):
    inventory_id = client.post("/api/search", json=search_body()).json()["inventory_id"]
    response = client.post("/api/jobs", json=job_body(inventory_id, product_ids=["NOT_IN_INVENTORY"]))
    assert response.status_code == 400


def test_job_rejects_unknown_or_malformed_inventory(client):
    missing = client.post("/api/jobs", json=job_body("0" * 32))
    assert missing.status_code == 404
    traversal = client.post("/api/jobs", json=job_body("../secrets"))
    assert traversal.status_code == 400


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_earthdata_auth_needs_both_username_and_password(monkeypatch):
    monkeypatch.setenv("EARTHDATA_USERNAME", "tester")
    monkeypatch.setenv("EARTHDATA_PASSWORD", "")
    assert Settings().earthdata_auth is None
    monkeypatch.setenv("EARTHDATA_PASSWORD", "tester-password")
    assert Settings().earthdata_auth == ("tester", "tester-password")


def test_earthdata_settings_reach_extractor(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EARTHDATA_USERNAME", "tester")
    monkeypatch.setenv("EARTHDATA_PASSWORD", "tester-password")
    get_settings.cache_clear()
    try:
        # The lifespan builds the real NisarExtractor under tmp_path; startup does no network I/O.
        with TestClient(app):
            assert app.state.extractor.runner.earthdata_auth == ("tester", "tester-password")
    finally:
        get_settings.cache_clear()
