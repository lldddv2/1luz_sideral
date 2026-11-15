from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from shapely.geometry import Polygon

from app.nisar_extractor import NisarExtractor
from app.nisar_extractor.geometry import from_bbox, from_geojson, from_wkt
from app.nisar_extractor.harmony_service import HarmonyRunner, stable_request_key, validate_capabilities
from app.nisar_extractor.models import ExtractionConfig, ProductRecord, parse_utc
from app.nisar_extractor.store import JobConflict, JobStore


def gcov_capabilities(shape_support: bool = False) -> dict:
    return {
        "conceptId": "C3622241360-ASF",
        "capabilitiesVersion": 3,
        "variables": [
            {
                "name": "/science/LSAR/GCOV/grids/frequencyA/HHHH",
                "href": "https://cmr.earthdata.nasa.gov/search/concepts/V4137651715-ASF",
            }
        ],
        "services": [
            {
                "name": "nasa/harmony-gdal-adapter",
                "capabilities": {
                    "subsetting": {"bbox": True, "shape": shape_support, "variable": True},
                    "outputFormats": [{"mimeType": "image/tiff"}],
                    "reprojection": {"supported": True, "supportedProjections": [{"crs": "EPSG:4326"}]},
                },
            }
        ],
    }


def tiny_tiff_bytes() -> bytes:
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            width=5,
            height=4,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=rasterio.transform.from_origin(-105, 40, 0.001, 0.001),
            nodata=float("nan"),
        ) as dataset:
            dataset.write(np.ones((1, 4, 5), dtype=np.float32))
        return memfile.read()


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "image/tiff"):
        self.payload = payload
        self.headers = {"Content-Length": str(len(payload)), "Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        for index in range(0, len(self.payload), chunk_size):
            yield self.payload[index : index + chunk_size]


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


class GeometryAndConfigTests(unittest.TestCase):
    def test_bbox_area_and_bounds(self):
        region = from_bbox([-105.01, 39.99, -104.99, 40.01])
        self.assertTrue(region.is_bbox)
        self.assertEqual(len(region.bounds), 4)
        self.assertGreater(region.area_km2, 3.0)
        self.assertLess(region.area_km2, 5.0)

    def test_wkt_and_geojson(self):
        polygon = "POLYGON((-105 39,-104.99 39,-104.99 39.01,-105 39.01,-105 39))"
        self.assertFalse(from_wkt(polygon).is_bbox)
        geojson = {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-105, 39], [-104.99, 39], [-104.99, 39.01], [-105, 39.01], [-105, 39]]],
            },
        }
        self.assertEqual(from_geojson(geojson).geometry.geom_type, "Polygon")

    def test_rejects_invalid_bbox_and_geometry(self):
        with self.assertRaises(ValueError):
            from_bbox([-104, 40, -105, 41])
        with self.assertRaises(ValueError):
            from_wkt("POINT(-105 40)")

    def test_date_is_normalized_to_utc(self):
        self.assertEqual(parse_utc("2026-11-14T10:00:00-05:00", "start"), "2026-11-14T15:00:00Z")
        with self.assertRaises(ValueError):
            parse_utc("2026-11-14T10:00:00", "start")

    def test_config_rejects_non_positive_limits(self):
        with self.assertRaises(ValueError):
            ExtractionConfig(max_output_bytes=0)

    def test_discovery_limit_is_separate_from_extraction_limit(self):
        config = ExtractionConfig()
        self.assertEqual((config.max_discover_results, config.max_products), (200, 100))
        with self.assertRaises(ValueError):
            ExtractionConfig(max_discover_results=0)

    def test_discover_accepts_200_results_and_rejects_more(self):
        region = from_bbox([-105.01, 39.99, -104.99, 40.01])
        with tempfile.TemporaryDirectory() as temp:
            extractor = NisarExtractor(ExtractionConfig(output_dir=temp))
            try:
                with mock.patch.object(extractor.catalog, "discover", return_value="inventory") as discover:
                    self.assertEqual(extractor.discover(region, start=None, stop=None, max_results=200), "inventory")
                discover.assert_called_once()
                with self.assertRaises(ValueError):
                    extractor.discover(region, start=None, stop=None, max_results=201)
            finally:
                extractor.close()


class CapabilityAndIdempotencyTests(unittest.TestCase):
    def test_capability_response_selects_bbox_and_local_polygon_mask(self):
        region = from_wkt("POLYGON((-105 39,-104.99 39,-104.99 39.01,-105 39.01,-105 39))")
        service, use_shape = validate_capabilities(
            gcov_capabilities(False), ["/science/LSAR/GCOV/grids/frequencyA/HHHH"], region
        )
        self.assertTrue(service["subsetting"]["bbox"])
        self.assertFalse(use_shape)

    def test_missing_variable_is_rejected(self):
        region = from_bbox([-105.01, 39.99, -104.99, 40.01])
        with self.assertRaises(ValueError):
            validate_capabilities(gcov_capabilities(), ["/missing/var"], region)

    def test_request_key_is_deterministic(self):
        product = ProductRecord(
            product_id="p",
            producer_granule_id="p",
            cmr_granule_id="G1-ASF",
            collection_short_name="NISAR_L2_GCOV_V1",
            collection_concept_id="C3622241360-ASF",
            product_type="GCOV",
            processing_configuration="PR",
            acquisition_start=None,
            acquisition_stop=None,
            geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]).__geo_interface__,
            size_mb_cmr=None,
            estimated_size_bytes=None,
        )
        a = stable_request_key(product, from_bbox([0, 0, 1, 1]), ["v"], None)
        b = stable_request_key(product, from_bbox([0, 0, 1, 1]), ["v"], None)
        self.assertEqual(a, b)

    def test_job_ledger_reuses_existing_job_and_blocks_unknown_post(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp) / "jobs.sqlite")
            first, created = store.reserve("key", {"x": 1}, max_attempts=2)
            self.assertTrue(created)
            store.update("key", state="submitted", job_id="job-1")
            same, created_again = store.reserve("key", {"x": 1}, max_attempts=2)
            self.assertFalse(created_again)
            self.assertEqual(same["job_id"], "job-1")
            store.reserve("unknown", {"x": 2}, max_attempts=2)
            store.update("unknown", state="submission_unknown", error="ambiguous network error")
            with self.assertRaises(JobConflict):
                store.reserve("unknown", {"x": 2}, max_attempts=2)


class BoundedTiffDownloadTests(unittest.TestCase):
    def test_download_checks_signature_and_opens_tiff(self):
        payload = tiny_tiff_bytes()
        with tempfile.TemporaryDirectory() as temp:
            runner = HarmonyRunner(
                ExtractionConfig(output_dir=temp, max_output_bytes=len(payload) + 10), None
            )
            output = Path(temp) / "tiny.tif"
            result = runner._download_tiff(
                FakeSession(FakeResponse(payload)),
                "https://harmony.example/result.tif",
                output,
                len(payload) + 10,
            )
            self.assertEqual(result["bytes"], len(payload))
            self.assertEqual(result["raster"]["width"], 5)
            self.assertEqual(len(result["sha256"]), 64)

    def test_download_stops_at_configured_size_without_partial_file(self):
        payload = tiny_tiff_bytes()
        with tempfile.TemporaryDirectory() as temp:
            runner = HarmonyRunner(ExtractionConfig(output_dir=temp), None)
            output = Path(temp) / "tiny.tif"
            with self.assertRaises(RuntimeError):
                runner._download_tiff(
                    FakeSession(FakeResponse(payload)),
                    "https://harmony.example/result.tif",
                    output,
                    len(payload) - 1,
                )
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".tif.part").exists())

    def test_non_tiff_url_is_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = HarmonyRunner(ExtractionConfig(output_dir=temp), None)
            with self.assertRaises(RuntimeError):
                runner._download_tiff(
                    FakeSession(FakeResponse(b"not tiff")),
                    "https://example.test/file.h5",
                    Path(temp) / "file.tif",
                    100,
                )


class EarthdataAuthTests(unittest.TestCase):
    """Mocked harmony-py Client: checks the auth argument only, no network."""

    def new_client_kwargs(self, earthdata_auth):
        runner = HarmonyRunner(ExtractionConfig(), None, earthdata_auth=earthdata_auth)
        with mock.patch("harmony.Client") as client_class:
            runner._new_client()
        return client_class.call_args.kwargs

    def test_explicit_credentials_reach_harmony_client(self):
        kwargs = self.new_client_kwargs(("tester", "tester-password"))
        self.assertEqual(kwargs["auth"], ("tester", "tester-password"))

    def test_without_credentials_harmony_client_keeps_default_lookup(self):
        self.assertIsNone(self.new_client_kwargs(None)["auth"])


if __name__ == "__main__":
    unittest.main()
