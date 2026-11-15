# 行政區搜（已實作）
- 後端 `routers/regions.py`：GET /api/regions?q=（≥2 字）。代理 Nominatim jsonv2 polygon_geojson，UA "1luz-sideral/0.1"，鎖保 1 req/s，記憶 LRU 256（鍵小寫去空）。addresstype 映西語（País、Departamento / Estado、Provincia、Municipio、Ciudad…）；有多邊形者先，行政 class（boundary/place）優。shapely simplify 容差＝bbox 跨 0.3%，坐標 4 位（Perú 約 4 KB）。測 `tests/test_regions.py`（mock `_fetch`）。
- 前端 `nominatim.ts` searchPlaces 改呼 /api/regions（形同 PlaceResult）。SearchBar 打字 450 ms 去抖自搜（Enter 亦可，新請廢舊），段名「Lugares (en el área / mundo)」，與自然地物段並存。點則 onPreview 飛往畫輪廓；+ 則 onAdd 以多邊形設 AOI（舊邏輯）。
- 限 study area（2026-11-15）：後端 /api/regions 加可選 `viewbox=w,s,e,n`，傳 Nominatim viewbox+bounded=1；快取鍵含 viewbox（3 位）；非法 422。前端以諸 areaShapes 之併 bbox 為 viewbox，返後 `placeInAreas` 再濾：無輪廓者心須在區形內（ray-casting，nominatim.ts），有輪廓者 bbox 交區 bbox。空則「Ningún lugar en el área seleccionada」；末一鈕「Buscar en todo el mundo」共用 `worldwide`，令地名與自然地物皆全球。區變（boxKey）則重搜。
- 境注：此沙箱中 Python requests 經 IPv6 連 Nominatim 掛起（curl 可）；強 IPv4 則通。非碼之過。
