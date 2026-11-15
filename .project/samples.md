# 樣影像（/api/samples）

- 目：`backend/data/samples/`。投 .tif/.tiff；git 忽 tif，留 README、.gitkeep、json。種：cop90_N19_W100（旁檔，日示例 2021-01-01）、RGB.byte（無日）。
- 時取序：旁檔 `<stem>.json`.datetime → tags（TIFFTAG_DATETIME、ACQUISITION_DATE、DATE_TIME，次遍諸 ns 似日之 key）→ 檔名（YYYYMMDDTHHMMSS、YYYY-MM-DD、YYYYMMDD）→ null。記 time_source：sidecar／tag:<ns>:<key>／filename／none。年限 1900–2100。
- 旁檔式：{datetime, label?, sensor?, polarization?, notes?}；後四原樣回。
- id：stem 之 slug（小寫，非 [A-Za-z0-9_-] 為 -）。唯掃得之 id 映檔，防穿越。掃依 mtime（含旁檔）快取。
- 端：GET 列（bbox、start、end 濾；日升序，null 殿後；無 tags）；GET /{id} 全元含 tags；/{id}/file；/{id}/preview.png（重投 3857，因 MapLibre image source 於墨卡托線性；長邊 ≤1024；單波 2–98 百分位灰，三波 RGB；nodata、NaN、RGB 全零透明；頭 X-Bounds-WGS84）；POST multipart file＋datetime、label 選 → 201；非 tif 或 rasterio 不能開或無 CRS 422；重名 409；>200 MB 413。
- 依：python-multipart 入 pyproject。
- 碼：services/samples.py、routers/samples.py、tests/test_samples.py。
