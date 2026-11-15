# 景（/api/scenes）

- 景＝一過境；source=samples（data/samples）或 nisar（S3 COG，見 aws-pipeline.md；data 須同給 source、polarization）。無伺服態。
- POST /query：{regions: FC｜Feature｜Polygon/MultiPolygon（WGS84；id 取 properties.id，缺則 r1…）, date?, window_days=15（0–365）, start?, end?（與 date 互斥，並給 422）, source}。區 ≤10，頂點總 ≤5000，否 422。回 FC：geometry＝bounds_wgs84 框；properties：scene_id、source、acquired_at、time_source、days_from_date（有 date）、regions[{id,coverage_pct}]（唯 >0，WGS84 面積比）、native_res_m、crs、count、dtype、assets.data。序：date 則 |days| 升，否 acquired_at 升，null 殿後。無日之景遇時濾則棄。
- POST /{id}/data：{geometry, format png（預）|geotiff|json, width?/height?（16–2048；缺一依長寬比；皆缺原生，長邊 >2048 降之）, fit pad（預，置中，餘 nodata/alpha0）|stretch, resampling average（預）|bilinear|nearest, mask=true}。總像素 ≤4194304。景缺 404；不交 422。
- 法：區轉景 CRS；區 bbox∩景界 為窗，from_bounds＋out_shape 讀；geometry_mask 遮。不重投（png 亦然，X-Note）。SAR 當於線性功率域 average（碼註）。
- 頭：X-Bounds-WGS84（bbox∩景）、X-Pixel-Size-M、X-Out-Size、X-CRS，皆 expose。geotiff deflate、原 dtype、nodata（無則 float NaN／int 0）。png 用 samples._stretch（2–98）。json：width、height、bands[min,max,mean,std,valid_pct]、bounds_wgs84、pixel_size_m、crs。
- 碼：services/scenes.py、routers/scenes.py、tests/test_scenes.py。
