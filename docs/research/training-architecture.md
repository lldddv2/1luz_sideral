# Training dataset architecture

Source: `notebooks/pablo/`. **Status: proposal.** A full training dataset has not
been generated yet; only a pilot sample exists.

## Goal

Build a reproducible collection of geographic chips that pairs NISAR GCOV
observations with OPERA DIST-ALERT-HLS labels. The first task is to detect
vegetation disturbance observed by OPERA and compare its date with the NISAR
acquisition. OPERA alone does not identify the cause of a disturbance.

The dataset keeps original layers and provenance. Training labels are derived
with versioned rules, so filters, polarizations and time windows can change
without losing source data.

## Pipeline scripts

| Script | Role |
|---|---|
| `catalog_sync.py` | Queries NASA CMR metadata only and builds NISAR-OPERA candidate pairs by time and footprint overlap. Downloads nothing. |
| `extract_sample.py` | Downloads `VEG-DIST-STATUS` (8 MiB cap) and checks a NISAR `frequencyA/HHHH` subset from Harmony. |
| `find_positive_aoi.py` | Scans the downloaded OPERA TIFF for windows with positive labels fully inside the NISAR footprint. |
| `sync_training_pilot.py` | Builds one aligned training sample from the best positive window. |
| `audit_temporal_windows.py` | Compares retrospective time windows on aligned TIFFs. |

```bash
python catalog_sync.py --start 2026-10-21 --stop 2026-11-14 --tolerance-days 3
PYTHONPATH=../jose .venv/bin/python sync_training_pilot.py \
  --nisar-variable /science/LSAR/GCOV/grids/frequencyA/HHHH \
  --nisar-variable /science/LSAR/GCOV/grids/frequencyA/HVHV
```

The default AOI is a small provisional rectangle in Central Valley, California
(`config/central_valley_candidate.json`). The default time tolerance is six
days. Pair offsets are signed: positive means OPERA is later than NISAR.

## Proposed layout

```text
data/datasets/<dataset_version>/
  dataset.json                    # version, goal, grid and rules
  manifest.jsonl                  # one row per chip
  splits.jsonl                    # train/valid/test by region/event
  samples/<sample_id>/
    features_frequencyA.tif
    features_frequencyB.tif       # optional, own grid
    labels_status.tif             # original VEG-DIST-STATUS
    labels_event_day.tif          # original VEG-DIST-DATE
    labels_event_delta_days.tif   # anomaly date minus NISAR date
    labels_target.tif             # derived class, versioned rule
    masks.tif                     # validity per channel, label and target
    sample.json                   # sources, times, grids, processing
  source_cache/<product_id>/      # shared sources, deduplicated by granule
```

Each GeoTIFF stores CRS, transform, resolution, `nodata`, band names and units.

## Inputs (NISAR)

- Frequency A: `HHHH` and `HVHV` tested.
- Frequency B: `HHHH` and `HVHV` when available, on their own grid; never
  resampled to 30 m as if it were real detail.
- Quality: keep `mask` and `numberOfLooks` per frequency.
- Store linear gamma-0 power; derive dB during preprocessing.

## Labels (OPERA)

- `VEG-DIST-STATUS` original codes: `0` no disturbance; `1-2` and `4-5`
  provisional; `3`, `6`, `7`, `8` confirmed; `255` nodata.
- `VEG-DIST-DATE`: first detection day, counted from 2020-12-31 (daily precision).
- Missing channels are never filled as valid zeros.
- Cause classes (fire, logging, landslide) would require an external event
  inventory; cause is never inferred from `VEG-DIST-STATUS`.

Splits must be done by region, event or spatial block, not by random pixels, to
avoid leaking near-identical areas between training and evaluation.

## Pilot results

- Best positive window: `[-120.2412837, 36.2694577, -120.2301769, 36.2802780]`,
  39 x 32 pixels at 30 m, EPSG:32611.
- 1,243 disturbed pixels, 1,240 confirmed (1,156 class 3, 84 class 6); full NISAR
  coverage.
- NISAR 10 m power was area-averaged to the OPERA 30 m grid (one OPERA pixel =
  3 x 3 NISAR pixels). Dates and categorical classes are not interpolated.
- Pair: NISAR 2026-10-26 13:08:57 UTC, OPERA 2026-10-27 18:54:18 UTC
  (+29.76 h). Per-pixel event offsets range from -108 to +1 days.
- Total download 3.46 MB; aligned rasters about 16 KB.

### Temporal window audit (single window)

Keeps positive labels whose first anomaly date falls in `[-N, -1]` days before
NISAR.

| Window before NISAR | Positives kept | Confirmed | Share of 1,243 |
|---:|---:|---:|---:|
| 7 days | 0 | 0 | 0 % |
| 14 days | 0 | 0 | 0 % |
| 30 days | 7 | 6 | 0.56 % |
| 45 days | 333 | 332 | 26.79 % |
| 60 days | 705 | 704 | 56.72 % |
| 90 days | 1,106 | 1,105 | 88.98 % |
| 120 days | 1,241 | 1,240 | 99.84 % |

The window has only five undisturbed pixels, so class balance and a final
threshold cannot be set from it.

## Size estimates (uncompressed)

- 128 x 128 chip, four float32 channels plus labels and mask: about 0.34 MiB;
  10,000 chips about 3.4 GiB.
- 256 x 256: about 1.38 MiB per chip; 13.4 GiB per 10,000.
- With two channels: 2.1 and 8.5 GiB per 10,000.

## Pending work

Repeat the temporal audit across several positive and background zones; fix the
label and sampling policy; decide on frequency B; agree on chip size and grid;
create spatial splits.

## References

- [NISAR GCOV user guide](https://nisar-docs.asf.alaska.edu/gcov/)
- [NISAR HDF5 format](https://nisar-docs.asf.alaska.edu/data-format/)
- [OPERA DIST-HLS v1 specification](https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DIST_HLS_Product_Specification_V1.pdf)
