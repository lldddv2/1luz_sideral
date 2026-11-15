# Water and context layers

Source: `notebooks/santiago/` (benchmarks in `bench/`, results in
`bench_output/`). All tests ran on 2026-11-14 and 2026-11-15.

## Displaying the NISAR raster

Data: real GCOV HH GeoTIFFs over Boulder, CO (10 m, EPSG:32613). Script:
`bench/bench_overlay.py`.

- **A**: one image reprojected to EPSG:3857, served to a MapLibre `image` source.
- **B**: COG + `rio-tiler` (TiTiler style) as an XYZ `raster` source.

| Area | A: WebP q80 | A: PNG | A: server time | B: initial view | B: 3 zoom levels |
|---|---|---|---|---|---|
| 1.5 km | 9 KB | 30 KB | 13 ms | 38 KB (9 tiles) | 176 KB |
| 5 km | 95 KB | 314 KB | 58 ms | 271 KB | 1.2 MB |
| 10 km | 381 KB | 1.2 MB | 220 ms | 449 KB | 3.1 MB |
| 20 km | 1.5 MB | 4.9 MB | 880 ms | 474 KB | 6.6 MB |

For a 6-date time slider at 10 km, A loads 2.3 MB WebP once and switches
instantly; B needs 2.7 MB for the first view alone and flickers on each change.
Skipping reprojection would cause at most 6.6 m error at 20 km (under one pixel),
but reprojection costs only about 150 ms. Images over about 40 km must be reduced
to 4096 px or less (GPU texture limit).

**Decision: A.** Simpler (one endpoint), better for the slider, enough for areas
up to 2500 km².

## Context layers tested

Requests used `Origin: http://localhost:5173`. "Pixels" counts tiles with any
non-transparent alpha. No layer needs an API key; all returned CORS `*`.

| Layer | Use | Verdict |
|---|---|---|
| OPERA DSWx-S1 (GIBS) | C-band water, 30 m, same dates as NISAR | Best direct flood comparison |
| NISAR GCOV (GIBS) | L-band preview without backend | Preview only, inconsistent coverage |
| JRC GSW occurrence / change | Historical water 1984 to 2021 | Fastest (about 340 ms); separates permanent water from new flooding |
| VIIRS / MODIS Combined Flood 3-Day | Daily regional flood | Coarse (375 m / 250 m), max zoom 9 |
| OPERA DSWx-HLS | Optical water validation | Works on clear days |
| OPERA RTC-S1 | C-band backscatter | No pass over Kruger on the test day |
| OPERA DIST-ANN / DIST-ALERT | Fire and deforestation | Use for vegetation changes |
| Hansen GFC loss | Historical forest loss | Use |
| Esri World Imagery / Hillshade | Optical base, relief | Use |
| GLDAS soil moisture | Context only (about 25 km, months of lag) | Use as context |
| GRACE LWE mascon | Groundwater | Discarded: ends 2022-07 |
| USGS fdsnws | Earthquakes by bbox | Use the bbox query, not the full feed |

The first run hit `ConnectionError` on several GIBS layers; with retries all
responded. The frontend should retry or tolerate missing tiles.

GIBS template (EPSG:3857):

```text
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{LAYER}/default/{YYYY-MM-DD}/{TileMatrixSet}/{z}/{y}/{x}.png
```

Corrections found against GetCapabilities: NISAR GCOV on GIBS has five date
ranges from 2025-10-29 to 2026-11-13 (not only from 2026-08-10); DSWx-S1 and
DSWx-HLS have many earlier ranges; NISAR orbit tracks are MVT only.

## Layers by change type

| Change | Context layers |
|---|---|
| Wetlands / flooding | OPERA DSWx, JRC Surface Water, HLS |
| Fire / deforestation | OPERA DIST, Hansen GFC, HLS |
| Earthquake / subsidence | USGS earthquakes, Hillshade |
| Glaciers | Hillshade, HLS |
| Agriculture | HLS, Esri World Imagery |

For subsidence (Mexico City) no tile layer shows the aquifer; that needs OPERA
DISP-S1 (Earthdata login) or NISAR's own InSAR.

## Study areas

Published NISAR cases tested:

- **Kruger / Limpopo flood**, 2026-01-12, bbox `[30.9, -25.5, 33.0, -22.3]`.
- **Mexico City subsidence**, bbox `[-99.30, 19.20, -98.90, 19.60]`.

Colombia check (39 tiles, all HTTP 200, NISAR dates every 12 days back from
2026-11-13):

| Region | bbox (W, S, E, N) | NISAR date with data | Verdict |
|---|---|---|---|
| La Mojana (Sucre/Bolívar) | -75.2, 8.2, -74.4, 9.0 | 2026-11-01 | OK |
| Ciénaga Grande de Santa Marta | -74.6, 10.6, -74.2, 11.1 | 2026-11-01 | OK |
| Depresión Momposina | -74.8, 8.9, -74.2, 9.4 | 2026-11-01 | OK |
| Llanos (Arauca/Casanare) | -71.5, 5.5, -70.0, 6.8 | none | NISAR unavailable |

The 2026-11-13 date had no NISAR pixels in any region. The check confirms pixels
exist, not that colors are useful.

**Recommended demo:** La Mojana, bbox `[-75.2, 8.2, -74.4, 9.0]`, date
`2026-11-01` for NISAR GCOV and DSWx-S1, with JRC occurrence/change as
background. Center `[-74.8, 8.6]`, zoom 9.

## Limits

- Browser rendering (FPS, GPU memory) was not measured.
- Latency comes from few requests on one network; some GIBS services take about
  4 s with a cold cache.
