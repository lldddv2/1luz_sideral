import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_extractor, get_settings
from app.main import app
from app.nisar_extractor import Inventory, ProductRecord
from app.nisar_extractor.geometry import region_to_record
from app.schemas import JobCreate

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


def make_product(product_id: str, properties: dict | None = None) -> ProductRecord:
    return ProductRecord(
        product_id=product_id,
        producer_granule_id=product_id,
        cmr_granule_id="G0000000-ASF",
        collection_short_name="NISAR_L2_GCOV_V1",
        collection_concept_id="C0000000-ASF",
        product_type="GCOV",
        processing_configuration="PR",
        acquisition_start="2026-01-01T00:00:00Z",
        acquisition_stop="2026-01-01T00:01:00Z",
        geometry=AOI,
        size_mb_cmr=12.5,
        estimated_size_bytes=12_500_000,
        variables=[{"name": VARIABLE, "concept_id": "V0000000-ASF"}],
        properties=properties or {},
    )


class FakeExtractor:
    """Stands in for NisarExtractor. Never touches ASF, CMR or Harmony."""

    def __init__(self) -> None:
        self.extract_calls: list[dict] = []
        self.discover_calls: list[int] = []  # max_results of each search
        self.products: list[ProductRecord] | None = None  # None: discovery returns one fake product

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
        self.discover_calls.append(max_results)
        products = self.products if self.products is not None else [make_product(PRODUCT_ID)]
        inventory = Inventory(
            query={"dataset": "NISAR", "result_count": len(products)},
            region=region_to_record(region),
            products=products,
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


@pytest.mark.parametrize(("sent", "discovered"), [(None, 100), (1, 1), (10, 10), (200, 200)])
def test_search_passes_max_results_to_discovery(client, fake_extractor, sent, discovered):
    body = search_body()
    if sent is not None:
        body["max_results"] = sent
    assert client.post("/api/search", json=body).status_code == 200
    assert fake_extractor.discover_calls == [discovered]


@pytest.mark.parametrize("max_results", [0, 201])
def test_search_rejects_max_results_outside_1_to_200(client, fake_extractor, max_results):
    response = client.post("/api/search", json={**search_body(), "max_results": max_results})
    assert response.status_code == 422
    assert fake_extractor.discover_calls == []


def test_search_reports_track_direction_and_frame(client, fake_extractor):
    asc_id = "NISAR_L2_PR_GCOV_034_091_A_022_4005_DHDH_A_20261030T120329_20261030T120404_P05036_N_F_J_001"
    desc_id = "NISAR_L2_PR_GCOV_034_027_D_068_4005_DHDH_A_20261026T015715_20261026T015753_P05036_N_F_J_001"
    fake_extractor.products = [
        make_product(asc_id),
        make_product(desc_id),
        make_product("NISAR_FAKE_PRODUCT_002", {"pathNumber": 5, "flightDirection": "DESCENDING", "frameNumber": 9}),
        make_product("NISAR_FAKE_PRODUCT_003"),
    ]
    products = client.post("/api/search", json=search_body()).json()["products"]
    assert [(p["track"], p["direction"], p["frame"]) for p in products] == [
        (91, "ascending", 22),  # from the product ID
        (27, "descending", 68),  # from the product ID
        (5, "descending", 9),  # no readable ID: from ASF properties
        (None, None, None),  # neither source yields them
    ]


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


def finished_job(client, results):
    jobs = client.app.state.jobs
    job = jobs.create(JobCreate(inventory_id="0" * 32, product_ids=[PRODUCT_ID], variables=[VARIABLE]))
    return jobs.update(job.id, state="done", results=results)


def write_file(path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def test_job_files_serve_recorded_tiffs_in_order(client, tmp_path):
    main = write_file(tmp_path / "HHHH.tif", b"II*\x00main")
    masked = write_file(tmp_path / "HHHH_masked.tif", b"II*\x00masked")
    job = finished_job(
        client,
        [{"product_id": PRODUCT_ID, "state": "downloaded", "outputs": [{"path": main, "masked_path": masked}]}],
    )

    assert client.get(f"/api/jobs/{job.id}").json()["files"] == ["HHHH.tif", "HHHH_masked.tif"]
    first = client.get(f"/api/jobs/{job.id}/files/0")
    assert first.status_code == 200
    assert first.content == b"II*\x00main"
    assert first.headers["content-type"] == "image/tiff"
    assert first.headers["content-disposition"] == 'attachment; filename="HHHH.tif"'
    assert client.get(f"/api/jobs/{job.id}/files/1").content == b"II*\x00masked"


@pytest.mark.parametrize("index", [2, 99, -1])
def test_job_file_index_outside_recorded_outputs_is_404(client, tmp_path, index):
    tif = write_file(tmp_path / "a.tif", b"II*\x00")
    job = finished_job(client, [{"product_id": PRODUCT_ID, "state": "downloaded", "outputs": [{"path": tif}]}])
    assert client.get(f"/api/jobs/{job.id}/files/{index}").status_code == 404


def test_job_files_skip_failed_products_and_non_tiff_outputs(client, tmp_path):
    notes = write_file(tmp_path / "notes.txt", b"not a tiff")
    tif = write_file(tmp_path / "ok.tif", b"II*\x00ok")
    job = finished_job(
        client,
        [
            {"product_id": "P1", "state": "error", "error": "boom"},
            {"product_id": "P2", "state": "downloaded", "outputs": [{"path": notes}, {"path": tif}]},
        ],
    )
    assert client.get(f"/api/jobs/{job.id}").json()["files"] == ["ok.tif"]
    assert client.get(f"/api/jobs/{job.id}/files/0").content == b"II*\x00ok"
    assert client.get(f"/api/jobs/{job.id}/files/1").status_code == 404


def test_job_file_missing_on_disk_is_404(client, tmp_path):
    job = finished_job(client, [{"product_id": PRODUCT_ID, "outputs": [{"path": str(tmp_path / "gone.tif")}]}])
    assert client.get(f"/api/jobs/{job.id}/files/0").status_code == 404


def test_job_file_before_job_finishes_is_404(client):
    jobs = client.app.state.jobs
    job = jobs.create(JobCreate(inventory_id="0" * 32, product_ids=[PRODUCT_ID], variables=[VARIABLE]))
    assert client.get(f"/api/jobs/{job.id}/files/0").status_code == 404


def test_unknown_job_file_is_404(client):
    assert client.get("/api/jobs/does-not-exist/files/0").status_code == 404


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
