from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import requests
from shapely.geometry import mapping

from .models import ProductRecord, Region


class HarmonyJobFailed(RuntimeError):
    """Harmony confirmed this remote job is terminally failed."""


def variable_catalog(capabilities: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "name": str(item["name"]),
            "concept_id": str(item.get("href", "")).rsplit("/", 1)[-1],
        }
        for item in capabilities.get("variables", [])
        if item.get("name")
    ]


def validate_capabilities(
    capabilities: dict[str, Any], variables: list[str], region: Region
) -> tuple[dict[str, Any], bool]:
    if not capabilities.get("conceptId"):
        raise RuntimeError("Harmony capabilities response has no collection concept ID")
    services = capabilities.get("services", [])
    gdal = next(
        (
            service.get("capabilities", {})
            for service in services
            if service.get("name") == "nasa/harmony-gdal-adapter"
        ),
        {},
    )
    subset = gdal.get("subsetting", {})
    formats = {f.get("mimeType") for f in gdal.get("outputFormats", [])}
    if "image/tiff" not in formats:
        raise RuntimeError("This collection's Harmony GeoTIFF service does not advertise image/tiff")
    if not subset.get("variable"):
        raise RuntimeError("Harmony GeoTIFF service does not support variable selection")
    if not (subset.get("bbox") or subset.get("shape")):
        raise RuntimeError("Harmony GeoTIFF service supports no spatial subset method")

    catalog = variable_catalog(capabilities)
    names = {v["name"] for v in catalog}
    ids = {v["concept_id"] for v in catalog}
    missing = [v for v in variables if v not in names and v not in ids]
    if missing:
        raise ValueError(f"Variables are not listed by Harmony for this collection: {missing}")

    # shape support must come from the same service used for GeoTIFF, not from
    # the collection-wide summary or a preview-only PNG service.
    use_shape = not region.is_bbox and bool(subset.get("shape"))
    if not use_shape and not subset.get("bbox"):
        raise RuntimeError("Requested geometry requires polygon subsetting, which is unavailable")
    return gdal, use_shape


def stable_request_key(
    product: ProductRecord,
    region: Region,
    variables: list[str],
    output_crs: str | None,
) -> tuple[str, dict[str, Any]]:
    request = {
        "collection_id": product.collection_concept_id,
        "granule_id": product.cmr_granule_id,
        "region_wkt": region.wkt,
        "variables": sorted(variables),
        "format": "image/tiff",
        "output_crs": output_crs,
    }
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest(), request


def safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "nisar"


def safe_error(error: Exception) -> str:
    text = str(error)
    text = re.sub(r"https?://[^\s'\"]+", "[redacted-url]", text)
    text = re.sub(
        r"(?i)(authorization|password|token|cookie)(\s*[:=]\s*)\S+",
        r"\1\2[redacted]",
        text,
    )
    return text[:1200]


class HarmonyRunner:
    def __init__(self, config, capabilities_client):
        self.config = config
        self.catalog = capabilities_client

    def _new_client(self):
        from harmony import Client

        client = Client(
            should_validate_auth=False,
            check_interval=3,
            download_timeout=(
                self.config.connect_timeout_seconds,
                self.config.read_timeout_seconds,
            ),
        )
        session = client._session()
        # harmony-py itself does not time out job status polls. This wrapper
        # supplies bounded connect/read timeouts while honoring explicit ones.
        original = session.request

        def request_with_timeout(method, url, **kwargs):
            kwargs.setdefault(
                "timeout",
                (self.config.connect_timeout_seconds, self.config.read_timeout_seconds),
            )
            return original(method, url, **kwargs)

        session.request = request_with_timeout
        return client, session

    def _request(self, product: ProductRecord, region: Region, variables: list[str], output_crs: str | None):
        from harmony import BBox, Collection, Request

        capabilities = self.catalog.capabilities(product.collection_concept_id)
        gdal, use_shape = validate_capabilities(capabilities, variables, region)
        geometry_path = None
        request_kwargs: dict[str, Any] = {
            "collection": Collection(product.collection_concept_id),
            "granule_id": [product.cmr_granule_id],
            "variables": variables,
            "format": "image/tiff",
            "max_results": 1,
            "skip_preview": True,
        }
        reproject = gdal.get("reprojection", {}).get("supported", False)
        if output_crs:
            if not reproject:
                raise RuntimeError("Requested reprojection is not supported by the GeoTIFF service")
            supported_crs = {
                entry.get("crs")
                for entry in gdal.get("reprojection", {}).get("supportedProjections", [])
            }
            if output_crs not in supported_crs:
                raise ValueError(f"CRS {output_crs!r} is not advertised by Harmony")
            request_kwargs["crs"] = output_crs

        if use_shape:
            temp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".geojson", prefix="nisar-aoi-", delete=False
            )
            json.dump(mapping(region.geometry), temp)
            temp.close()
            geometry_path = Path(temp.name)
            request_kwargs["shape"] = str(geometry_path)
        else:
            if not gdal.get("subsetting", {}).get("bbox"):
                raise RuntimeError("No supported spatial subsetting route for this geometry")
            request_kwargs["spatial"] = BBox(*region.bounds)

        request = Request(**request_kwargs)
        if not request.is_valid():
            if geometry_path:
                geometry_path.unlink(missing_ok=True)
            raise ValueError("Harmony rejected request validation: " + "; ".join(request.error_messages()))
        return request, geometry_path, capabilities, use_shape

    def _wait(self, client, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.job_timeout_seconds
        last_error = None
        while time.monotonic() < deadline:
            try:
                status = client.status(job_id)
                last_error = None
            except (requests.RequestException, TimeoutError) as error:
                last_error = safe_error(error)
                time.sleep(min(2.0, self.config.retry_backoff_seconds))
                continue
            state = status.get("status", "unknown")
            if state == "successful":
                return status
            if state in {"failed", "canceled", "paused"}:
                raise HarmonyJobFailed(f"Harmony job {state}: {status.get('message', '')}")
            time.sleep(3)
        raise TimeoutError(f"Harmony polling timed out; last network error: {last_error or 'none'}")

    def _download_tiff(
        self,
        session: requests.Session,
        url: str,
        output_path: Path,
        remaining_bytes: int,
    ) -> dict[str, Any]:
        if Path(url.split("?", 1)[0]).suffix.lower() not in {".tif", ".tiff"}:
            raise RuntimeError("Harmony result URL is not a TIFF; refusing to save it")
        if output_path.exists() and not self.config.overwrite:
            return self._verify_tiff(output_path, reused=True)

        partial = output_path.with_suffix(output_path.suffix + ".part")
        partial.unlink(missing_ok=True)
        hasher = hashlib.sha256()
        transferred = 0
        try:
            with session.get(
                url,
                stream=True,
                headers={"Accept-Encoding": "identity"},
                timeout=(self.config.connect_timeout_seconds, self.config.read_timeout_seconds),
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type not in {"image/tiff", "image/geotiff", "application/octet-stream"}:
                    raise RuntimeError(f"Unexpected Harmony output Content-Type: {content_type or 'missing'}")
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > remaining_bytes:
                    raise RuntimeError("GeoTIFF Content-Length exceeds the configured output byte limit")
                with partial.open("wb") as target:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        transferred += len(chunk)
                        if transferred > remaining_bytes:
                            raise RuntimeError("GeoTIFF exceeded the configured output byte limit")
                        hasher.update(chunk)
                        target.write(chunk)
                if declared and transferred != int(declared):
                    raise IOError("GeoTIFF byte count does not match Content-Length")
            self._check_tiff_signature(partial)
            raster_metadata = self._open_with_rasterio(partial)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            partial.replace(output_path)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return {
            "path": str(output_path),
            "bytes": transferred,
            "sha256": hasher.hexdigest(),
            "content_type": content_type,
            "reused": False,
            "raster": raster_metadata,
            "integrity": "Content-Length (when supplied), TIFF signature and Rasterio open verified",
        }

    @staticmethod
    def _check_tiff_signature(path: Path) -> None:
        with path.open("rb") as stream:
            header = stream.read(4)
        if header not in {b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"}:
            raise IOError("Harmony result has no valid TIFF/BigTIFF signature")

    @staticmethod
    def _open_with_rasterio(path: Path) -> dict[str, Any]:
        import rasterio

        with rasterio.open(path) as dataset:
            if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
                raise IOError("GeoTIFF has invalid raster dimensions")
            return {
                "width": dataset.width,
                "height": dataset.height,
                "bands": dataset.count,
                "crs": str(dataset.crs) if dataset.crs else None,
                "dtype": dataset.dtypes[0],
                "bounds": list(dataset.bounds),
                "nodata": None if dataset.nodata is None or math.isnan(dataset.nodata) else dataset.nodata,
            }

    def _verify_tiff(self, path: Path, *, reused: bool) -> dict[str, Any]:
        if path.stat().st_size > self.config.max_output_bytes:
            raise RuntimeError("Existing TIFF exceeds configured max_output_bytes")
        self._check_tiff_signature(path)
        raster = self._open_with_rasterio(path)
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "content_type": "local-existing-tiff",
            "reused": reused,
            "raster": raster,
            "integrity": "local size, TIFF signature and Rasterio open verified",
        }

    def execute(
        self,
        product: ProductRecord,
        region: Region,
        variables: list[str],
        *,
        output_crs: str | None,
        store,
        reuse_job_id: str | None = None,
    ) -> dict[str, Any]:
        request_key, request_description = stable_request_key(product, region, variables, output_crs)
        output_dir = Path(self.config.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        # Check live service/variable/subsetting support before creating a local
        # reservation or submitting any remote work.
        request, geometry_path, capabilities, use_shape = self._request(
            product, region, variables, output_crs
        )
        client, session = self._new_client()
        try:
            ledger_row = store.get(request_key)
            if reuse_job_id and not ledger_row:
                ledger_row, _ = store.reserve(
                    request_key, request_description, max_attempts=self.config.max_attempts
                )
                store.update(request_key, state="submitted", job_id=reuse_job_id)
            elif not reuse_job_id:
                ledger_row, _ = store.reserve(
                    request_key, request_description, max_attempts=self.config.max_attempts
                )
            if ledger_row and ledger_row.get("state") == "downloaded":
                existing = ledger_row.get("outputs", [])
                if existing and all(Path(x["path"]).exists() for x in existing):
                    if geometry_path:
                        geometry_path.unlink(missing_ok=True)
                    client.executor.shutdown(wait=True)
                    return {
                        "product_id": product.product_id,
                        "job_id": ledger_row.get("job_id"),
                        "state": "downloaded",
                        "reused": True,
                        "outputs": existing,
                    }
        except Exception:
            if geometry_path:
                geometry_path.unlink(missing_ok=True)
            client.executor.shutdown(wait=True)
            client.session.close()
            raise

        job_id = reuse_job_id or (ledger_row.get("job_id") if ledger_row else None)
        try:
            if job_id:
                status = client.status(job_id)
                job_request = status.get("request", "")
                if (
                    product.cmr_granule_id not in job_request
                    or not any(v.rsplit("/", 1)[-1] in job_request for v in variables)
                ):
                    raise RuntimeError("Existing Harmony job does not match this granule/variable request")
                state = status.get("status")
                if state in {"failed", "canceled"}:
                    store.update(request_key, state="failed", error=f"Harmony status={state}")
                    ledger_row, is_new = store.reserve(
                        request_key, request_description, max_attempts=self.config.max_attempts
                    )
                    job_id = None
                    time.sleep(self.config.retry_backoff_seconds * max(1, ledger_row["attempts"] - 1))
                elif state != "successful":
                    store.update(request_key, state="running", job_id=job_id)
                    status = self._wait(client, job_id)
                else:
                    store.update(request_key, state="successful", job_id=job_id)
            if not job_id:
                while True:
                    store.update(request_key, state="submitting")
                    # POST submission is intentionally not retried after a network
                    # error: the server may have accepted it before the reply was lost.
                    try:
                        submitted = client.submit(request)
                    except Exception as error:
                        store.update(
                            request_key,
                            state="submission_unknown",
                            error=f"{type(error).__name__}: {safe_error(error)}",
                        )
                        raise
                    if not isinstance(submitted, str):
                        store.update(
                            request_key,
                            state="submission_unknown",
                            error="Harmony returned a non-job response; refusing automatic resubmission",
                        )
                        raise RuntimeError("Harmony returned a non-job response; inspect the server response")
                    job_id = submitted
                    store.update(request_key, state="submitted", job_id=job_id)
                    try:
                        self._wait(client, job_id)
                    except HarmonyJobFailed as error:
                        store.update(request_key, state="failed", job_id=job_id, error=safe_error(error))
                        failed_row = store.get(request_key)
                        if failed_row["attempts"] >= self.config.max_attempts:
                            raise
                        ledger_row, _ = store.reserve(
                            request_key, request_description, max_attempts=self.config.max_attempts
                        )
                        time.sleep(
                            self.config.retry_backoff_seconds
                            * max(1, ledger_row["attempts"] - 1)
                        )
                        job_id = None
                        continue
                    store.update(request_key, state="successful", job_id=job_id)
                    break

            # Do not set ``limit=1``: Harmony's paginated result endpoint can
            # return an empty page with that limit even when the completed job
            # has data. With maxResults=1, this remains bounded by variables.
            urls = list(client.result_urls(job_id, allow_incomplete=True))
            if len(urls) != len(variables):
                raise RuntimeError(
                    f"Harmony returned {len(urls)} result TIFFs for {len(variables)} requested variables"
                )
            outputs: list[dict[str, Any]] = []
            total_downloaded = 0
            for index, (variable, url) in enumerate(zip(variables, urls, strict=True)):
                variable_label = safe_component(variable.rsplit("/", 1)[-1])
                file_name = Path(url.split("?", 1)[0]).name
                if not file_name.lower().endswith((".tif", ".tiff")):
                    raise RuntimeError("Harmony output filename is not a TIFF")
                output_path = output_dir / f"{safe_component(product.product_id)}_{index}_{variable_label}_{file_name}"
                remaining = self.config.max_output_bytes - total_downloaded
                result = self._download_tiff(session, url, output_path, remaining)
                total_downloaded += int(result["bytes"])
                result["variable"] = variable
                raster = result.get("raster") or self._open_with_rasterio(output_path)
                result["raster"] = raster
                if not region.is_bbox and not use_shape:
                    result["masked_path"] = str(
                        self._apply_local_mask(output_path, region, output_dir)
                    )
                outputs.append(result)

            metadata = {
                "schema_version": 1,
                "product": product.to_dict(),
                "request": request_description,
                "region": {
                    "wkt": region.wkt,
                    "source_kind": region.source_kind,
                    "bounds_wsen": list(region.bounds),
                    "area_km2_wgs84_geodesic": region.area_km2,
                },
                "harmony": {
                    "job_id": job_id,
                    "state": "successful",
                    "capabilities_version": capabilities.get("capabilitiesVersion"),
                    "bbox_supported": bool(
                        next(
                            (
                                s.get("capabilities", {}).get("subsetting", {}).get("bbox", False)
                                for s in capabilities.get("services", [])
                                if s.get("name") == "nasa/harmony-gdal-adapter"
                            ),
                            False,
                        )
                    ),
                    "polygon_service_supported": use_shape,
                    "local_mask_applied": not region.is_bbox and not use_shape,
                    "output_format": "image/tiff",
                    "outputs": outputs,
                },
                "limits": {
                    "max_output_bytes": self.config.max_output_bytes,
                    "source_hdf5_downloaded": False,
                },
            }
            metadata_path = output_dir / f"{safe_component(product.product_id)}_{request_key[:12]}_metadata.json"
            capability_path = output_dir / (
                f"{safe_component(product.collection_short_name)}_{request_key[:12]}_capabilities.json"
            )
            if not capability_path.exists():
                capability_temp = capability_path.with_suffix(".json.tmp")
                capability_temp.write_text(json.dumps(capabilities, indent=2, sort_keys=True) + "\n")
                capability_temp.replace(capability_path)
            metadata["capabilities_snapshot_path"] = str(capability_path)
            metadata["metadata_path"] = str(metadata_path)
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            outputs[0]["metadata_path"] = str(metadata_path)
            store.update(request_key, state="downloaded", job_id=job_id, outputs=outputs)
            return {
                "product_id": product.product_id,
                "job_id": job_id,
                "state": "downloaded",
                "reused": bool(reuse_job_id or ledger_row.get("job_id")),
                "outputs": outputs,
                "metadata_path": str(metadata_path),
            }
        except Exception as error:
            current = store.get(request_key) or {}
            if current.get("state") not in {"submission_unknown", "failed"}:
                store.update(request_key, state="poll_error" if job_id else "failed", error=safe_error(error))
            raise
        finally:
            if geometry_path:
                geometry_path.unlink(missing_ok=True)
            client.executor.shutdown(wait=True)
            client.session.close()

    def _apply_local_mask(self, source_path: Path, region: Region, output_dir: Path) -> Path:
        import rasterio
        from rasterio.features import geometry_mask
        from rasterio.warp import transform_geom

        with rasterio.open(source_path) as source:
            array = source.read()
            nodata = source.nodata
            if nodata is None or (isinstance(nodata, float) and math.isnan(nodata)):
                nodata = np.nan if np.issubdtype(array.dtype, np.floating) else 0
            geometry = transform_geom("EPSG:4326", source.crs, mapping(region.geometry))
            inside = geometry_mask(
                [geometry],
                out_shape=(source.height, source.width),
                transform=source.transform,
                invert=True,
                all_touched=False,
            )
            output_array = array.copy()
            output_array[:, ~inside] = nodata
            profile = source.profile.copy()
            profile.update(nodata=nodata, compress="deflate")
            destination = output_dir / (source_path.stem + "_masked.tif")
            with rasterio.open(destination, "w", **profile) as target:
                target.write(output_array)
                target.update_tags(
                    local_mask_wkt=region.wkt,
                    mask_reason="Harmony service did not advertise polygon subsetting",
                )
        return destination
