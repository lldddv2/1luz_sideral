# NISAR data access

Code: `notebooks/jose/nisar_extractor/` (NISAR) and `notebooks/jose/opera/` (OPERA).

## NISAR extractor

A Python package and CLI that discovers NISAR products with ASF Search and asks
NASA Harmony for spatial subsets of science variables as GeoTIFF. It never
downloads the original full HDF5 files. It does only discovery and extraction:
no temporal analysis, change detection or scientific interpretation.

### Workflow

1. ASF Search finds granules that intersect a BBOX, GeoJSON or WKT for the given
   dates, product and production configuration.
2. `search` saves an inventory with IDs, dates, footprint, catalog size and
   advertised variables. It downloads no data.
3. The user explicitly selects product IDs and variables.
4. Before extracting, the client queries Harmony capabilities for the collection.
   Harmony produces GeoTIFF only if the service advertises the format and the
   requested operations.

### Requirements and authentication

- Tested on Fedora 43 with Python 3.14.
- An active Earthdata Login account, configured in `~/.netrc` outside the
  repository:

```text
machine urs.earthdata.nasa.gov
  login YOUR_EARTHDATA_USER
  password YOUR_EARTHDATA_PASSWORD
```

```bash
chmod 600 ~/.netrc
```

The code never asks for, writes or prints credentials, and creates no new tokens.
IPv4 is forced by default because of an IPv6 routing problem seen on the
development machine; disable it with `--no-force-ipv4`.

Install:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-nisar-extractor.txt
```

### Search

```bash
.venv/bin/python -m nisar_extractor.cli search \
  --wkt 'POLYGON((-105.0048 39.9952,-104.9952 39.9952,-105.0000 40.0048,-105.0048 39.9952))' \
  --start 2025-08-01T05:00:00Z \
  --stop 2026-11-15T04:59:59Z \
  --product GCOV \
  --production-configuration PR \
  --max-results 1 \
  --max-products 1 \
  --max-area-km2 2 \
  --output-dir nisar_output \
  --inventory nisar_output/inventory.json
```

- Exactly one geometry: `--bbox WEST,SOUTH,EAST,NORTH`, `--geojson`
  (Polygon/MultiPolygon, Feature or FeatureCollection) or `--wkt`.
- `--product` accepts `GCOV`, `GUNW`, `GOFF` or `SME2`.
- `--max-area-km2` is geodesic (WGS84). The limit can be raised for search, but
  extraction should keep a small AOI.

The inventory holds product and CMR granule IDs, collection short name and
concept ID, dates, GeoJSON footprint, CMR `granule_size` (MB) plus an estimated
byte count, and the variables listed for the collection. Listed variables come
from collection capabilities and may not exist in every granule.

### Extract

```bash
.venv/bin/python -m nisar_extractor.cli extract \
  --inventory nisar_output/inventory.json \
  --product-id NISAR_L2_PR_GCOV_..._001 \
  --variables /science/LSAR/GCOV/grids/frequencyA/HHHH \
  --output-dir nisar_output \
  --max-area-km2 2 \
  --max-products 1 \
  --max-output-mib 64 \
  --max-concurrent 1
```

- `--product-id` can repeat. `--variables` is comma-separated (full names or
  UMM-Var IDs).
- `--output-crs EPSG:4326` is accepted only if the GeoTIFF service advertises it.
  The default keeps the source CRS.
- `--reuse-job-id <UUID>` resumes a known Harmony job without a new POST.
- `jobs --output-dir ...` lists the job ledger.

### Robustness

- A SQLite ledger (`.nisar-extractor-jobs.sqlite3`) stores the idempotency key,
  job ID, state, attempts, paths, hashes and safe error messages.
- An ambiguous network response to a POST is recorded as `submission_unknown`
  and is not resubmitted, because Harmony may have created the job. Confirmed
  failed jobs can be retried up to `--max-attempts`.
- Each result is checked before publishing: `.tif`/`.tiff` URL, TIFF MIME type,
  byte cap while streaming, `Content-Length`, TIFF/BigTIFF signature, opening
  with Rasterio, and a local SHA256. Invalid results are deleted. HDF5 is never
  accepted.
- If Harmony supports bbox but not shape for a collection, the request uses the
  bbox and Rasterio writes a second TIFF masked by the original polygon.
- Each extraction saves a metadata JSON and a capabilities snapshot next to the
  TIFF.

### Python use

```python
from nisar_extractor import ExtractionConfig, NisarExtractor

extractor = NisarExtractor(ExtractionConfig(
    output_dir="data/nisar",
    max_area_km2=20,
    max_products=5,
    max_output_bytes=32 * 1024 * 1024,
    max_concurrent=2,
))

region = extractor.geojson("aoi.geojson")
inventory = extractor.discover(
    region,
    start="2025-08-01T05:00:00Z",
    stop="2026-11-15T04:59:59Z",
    product_type="GCOV",
    production_configuration="PR",
    max_results=5,
    inventory_path="data/nisar/inventory.json",
)
outputs = extractor.extract(
    inventory,
    product_ids=[inventory.products[0].product_id],
    variables=["/science/LSAR/GCOV/grids/frequencyA/HHHH"],
)
```

In FastAPI, run extraction in a worker or `asyncio.to_thread`. Do not keep a
browser request open while Harmony processes the job. The local SQLite ledger is
fine for the proof of concept, not as a distributed coordinator.

### Verified end-to-end test

A live run found one GCOV PR granule and extracted
`/science/LSAR/GCOV/grids/frequencyA/HHHH` through an already completed Harmony
job (`60ec0904-418f-4725-b38e-e7c79b3e4805`, reused). The download was a single
GeoTIFF of 39,032 bytes (raster 84 x 110); local masking produced a second TIFF
of 17,412 bytes. No `.h5` was downloaded (`source_hdf5_downloaded: false`).

### Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The unit tests use no network and build a tiny TIFF in memory.

## OPERA exploration tools

Two scripts independent of the NISAR extractor (Python 3.12+, Earthdata Login via
`~/.netrc`):

- `descargar_opera.py` searches and downloads one OPERA GeoTIFF layer with
  `earthaccess`:
  - **OPERA DIST-ALERT-HLS**: band `VEG-DIST-STATUS` (vegetation disturbance).
  - **OPERA DSWx-HLS**: band `B01_WTR` (surface water classes).
- `inspeccionar_opera.py` scans `datos_opera/`, processes rasters in blocks and
  writes categorical PNG maps and `reporte_inspeccion_opera.json` with per-class
  statistics. NoData is transparent; class percentages exclude NoData and masked
  codes.

```bash
python descargar_opera.py --product all \
  --bbox -105.05 39.95 -104.95 40.05 \
  --start 2026-10-01 --end 2026-11-14 --count 3
python inspeccionar_opera.py
```

`--yes` skips the per-product confirmation. Class codes follow the official OPERA
product specifications; DIST-ALERT colors are only a display palette.

## References

- [ASF `asf_search`](https://docs.asf.alaska.edu/asf_search/basics/)
- [ASF Search API keywords](https://docs.asf.alaska.edu/api/keywords/)
- [NISAR collections](https://nisar-docs.asf.alaska.edu/earthdata-search/)
- [Harmony for NISAR](https://nisar-docs.asf.alaska.edu/harmony/)
- [NASA Harmony](https://harmony.earthdata.nasa.gov/)
- [OPERA DIST-HLS specification](https://lpdaac.usgs.gov/documents/1766/OPERA_DIST_HLS_Product_Specification_V1.pdf)
- [earthaccess authentication](https://earthaccess.readthedocs.io/en/stable/user/howto/authenticate/)
