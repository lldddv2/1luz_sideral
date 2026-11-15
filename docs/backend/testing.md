# Testing

Tests live in `backend/tests/` and use pytest. `pyproject.toml` sets `testpaths = ["tests"]`
and `pythonpath = ["."]`, so run them from `backend/`.

```bash
cd backend
pip install -e ".[dev]"   # or: uv pip install -e ".[dev]"
pytest
```

Run one module or test:

```bash
pytest tests/test_models_api.py
pytest tests/test_samples.py -k preview
```

| Module | Covers |
|---|---|
| `test_api.py` | search and jobs endpoints |
| `test_estimate.py` | size estimation |
| `test_landcover.py` | WorldCover classes, stats and masks |
| `test_dem.py` | DEM endpoints |
| `test_samples.py` | sample scanning, dates, preview and upload |
| `test_scenes.py` | scene query and data reads |
| `test_features.py` | natural features catalog |
| `test_regions.py` | region search (Nominatim mocked through `_fetch`) |
| `test_water.py` | U-Net water model against reference files in `tests/data/water` |
| `test_models_api.py` | external model bridge (input building mocked) |
| `test_nisar_extractor.py` | NISAR extractor |

Most tests do not need network access; external services are mocked.
