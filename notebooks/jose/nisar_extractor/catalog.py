from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import shape

from .geometry import region_to_record
from .models import Inventory, ProductRecord, Region, parse_utc
from .network import requests_session

ASF_SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
CMR_BASE = "https://cmr.earthdata.nasa.gov/search"
HARMONY_CAPABILITIES_URL = "https://harmony.earthdata.nasa.gov/capabilities"
HARMONY_PRODUCTS = {"GCOV", "GUNW", "GOFF", "SME2"}


def _wkt_for_asf(region: Region) -> str:
    # ASF Search API accepts closed 2-D polygon WKT; BBOX input becomes WKT too.
    return region.geometry.wkt


class AsfCatalog:
    def __init__(self, *, timeout: tuple[float, float] = (15, 45), retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.http = requests_session(retries)
        self._collection_cache: dict[str, dict[str, Any]] = {}
        self._capabilities_cache: dict[str, dict[str, Any]] = {}
        self._cache_lock = threading.RLock()

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> requests.Response:
        response = self.http.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response

    def collection(self, short_name: str) -> dict[str, Any]:
        with self._cache_lock:
            if short_name not in self._collection_cache:
                data = self._get(
                    f"{CMR_BASE}/collections.json",
                    params={"short_name": short_name, "page_size": 2},
                ).json()
                entries = data.get("feed", {}).get("entry", [])
                exact = [e for e in entries if e.get("short_name") == short_name]
                if len(exact) != 1:
                    raise RuntimeError(f"CMR could not resolve collection {short_name!r}")
                self._collection_cache[short_name] = exact[0]
            return self._collection_cache[short_name]

    def capabilities(self, collection_id: str) -> dict[str, Any]:
        with self._cache_lock:
            if collection_id not in self._capabilities_cache:
                data = self._get(
                    HARMONY_CAPABILITIES_URL,
                    params={"collectionId": collection_id},
                ).json()
                if data.get("conceptId") != collection_id:
                    raise RuntimeError(f"Unexpected Harmony capabilities for {collection_id}")
                self._capabilities_cache[collection_id] = data
            return self._capabilities_cache[collection_id]

    def granule(self, collection_id: str, producer_granule_id: str) -> dict[str, Any]:
        data = self._get(
            f"{CMR_BASE}/granules.json",
            params={
                "collection_concept_id": collection_id,
                "producer_granule_id": producer_granule_id,
                "page_size": 2,
            },
        ).json()
        entries = data.get("feed", {}).get("entry", [])
        if len(entries) != 1:
            raise RuntimeError(
                f"CMR returned {len(entries)} granules for {producer_granule_id!r}; expected 1"
            )
        return entries[0]

    @staticmethod
    def _product_variables(
        variables: list[dict[str, str]], properties: dict[str, Any]
    ) -> tuple[list[dict[str, str]], str]:
        band_polarizations = {
            "frequencyA": properties.get("mainBandPolarization"),
            "frequencyB": properties.get("sideBandPolarization"),
        }
        normalized: dict[str, set[str] | None] = {}
        for band, values in band_polarizations.items():
            if values is None:
                normalized[band] = None
            elif isinstance(values, str):
                normalized[band] = {part.strip().upper() for part in values.split("+") if part.strip()}
            else:
                normalized[band] = {str(part).upper() for part in values}

        filtered: list[dict[str, str]] = []
        for variable in variables:
            name = variable["name"]
            band = "frequencyA" if "/frequencyA/" in name else "frequencyB" if "/frequencyB/" in name else None
            if band and normalized[band] is not None:
                allowed = normalized[band]
                if not allowed:
                    continue
            filtered.append(variable)
        scope = (
            "Harmony collection variables filtered for bands present in ASF polarization metadata; Harmony validates each term's file presence"
            if any(values is not None for values in normalized.values())
            else "collection capabilities; granule contents are verified by Harmony"
        )
        return filtered, scope

    def discover(
        self,
        region: Region,
        *,
        start: str | None,
        stop: str | None,
        product_type: str = "GCOV",
        production_configuration: str | None = "PR",
        max_results: int = 10,
    ) -> Inventory:
        import asf_search as asf

        product_type = product_type.upper()
        if product_type not in HARMONY_PRODUCTS:
            raise ValueError(f"product_type must be one of {sorted(HARMONY_PRODUCTS)}")
        if not 1 <= max_results:
            raise ValueError("max_results must be >= 1")
        start = parse_utc(start, "start")
        stop = parse_utc(stop, "stop")
        if start and stop and start >= stop:
            raise ValueError("start must be earlier than stop")

        search_args: dict[str, Any] = {
            "dataset": "NISAR",
            "intersectsWith": _wkt_for_asf(region),
            "processingLevel": product_type,
            "maxResults": max_results,
        }
        if start:
            search_args["start"] = start
        if stop:
            search_args["end"] = stop
        if production_configuration:
            search_args["productionConfiguration"] = production_configuration

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                results = asf.search(**search_args)
                break
            except Exception as error:
                last_error = error
                if attempt + 1 >= self.retries:
                    raise
                time.sleep(min(8.0, 0.5 * (2**attempt)))
        else:
            raise RuntimeError("ASF Search request failed") from last_error
        products: list[ProductRecord] = []
        for product in results:
            props = product.properties
            producer_id = str(props.get("fileID") or Path(props["fileName"]).stem)
            collection_name = props.get("collectionName")
            if not collection_name:
                raise RuntimeError(f"ASF record {producer_id} has no collectionName")
            cmr_collection = self.collection(collection_name)
            collection_id = cmr_collection["id"]
            cmr_granule = self.granule(collection_id, producer_id)
            capability = self.capabilities(collection_id)
            collection_variables = [
                {
                    "name": str(v.get("name", "")),
                    "concept_id": str(v.get("href", "")).rsplit("/", 1)[-1],
                }
                for v in capability.get("variables", [])
                if v.get("name")
            ]
            variables, variable_scope = self._product_variables(collection_variables, props)
            size_value = cmr_granule.get("granule_size")
            size_mb = float(size_value) if size_value not in (None, "") else None
            # CMR's granule_size is reported in MB, not bytes. Keep that raw
            # value and clearly mark this decimal-byte conversion as estimated.
            size_estimate = round(size_mb * 1_000_000) if size_mb is not None else None
            geometry = product.geometry
            footprint = shape(geometry)
            if not footprint.is_valid:
                geometry = footprint.buffer(0).__geo_interface__

            safe_props = {
                key: props.get(key)
                for key in (
                    "fileName",
                    "fileID",
                    "collectionName",
                    "startTime",
                    "stopTime",
                    "processingLevel",
                    "processingType",
                    "productionConfiguration",
                    "polarization",
                    "mainBandPolarization",
                    "sideBandPolarization",
                    "frameNumber",
                    "flightDirection",
                    "pathNumber",
                )
                if props.get(key) is not None
            }
            products.append(
                ProductRecord(
                    product_id=str(props.get("fileID") or producer_id),
                    producer_granule_id=producer_id,
                    cmr_granule_id=str(cmr_granule["id"]),
                    collection_short_name=collection_name,
                    collection_concept_id=collection_id,
                    product_type=product_type,
                    processing_configuration=props.get("productionConfiguration")
                    or production_configuration,
                    acquisition_start=props.get("startTime") or cmr_granule.get("time_start"),
                    acquisition_stop=props.get("stopTime") or cmr_granule.get("time_end"),
                    geometry=geometry,
                    size_mb_cmr=size_mb,
                    estimated_size_bytes=size_estimate,
                    data_url=props.get("url"),
                    variables=variables,
                    collection_variables=collection_variables,
                    variables_scope=variable_scope,
                    properties=safe_props,
                )
            )

        return Inventory(
            query={
                "endpoint": ASF_SEARCH_URL,
                "dataset": "NISAR",
                "product_type": product_type,
                "production_configuration": production_configuration,
                "start": start,
                "stop": stop,
                "max_results": max_results,
                "intersects_wkt": _wkt_for_asf(region),
                "result_count": len(products),
            },
            region=region_to_record(region),
            products=products,
            queried_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def close(self) -> None:
        self.http.close()
