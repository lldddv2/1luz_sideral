# 區內地名

- 有 study area 則地名唯限區內；無則如舊。
- 自然地物 label：App `shownLabels` 以 `inShapes`（features.ts）濾。點在真形內，或 bbox 角在形內，或形頂點在 bbox 內，皆算。點在形之判借 geo.ts `inPolygon`，含洞與 MultiPolygon。
- 底圖地名：Esri reference 為 raster，不可逐名濾、不可依多邊形裁。故有區則隱 `basemap-labels` 層，代以 `areaPlaces.ts`：
  - 由 Overpass（overpass-api.de，瀏覽器直 POST，CORS `*`）取諸區 bbox 內 `node[place][name]`。
  - 諸區 bbox 合計 ≤20000 km² 方含 village；否則唯 state|city|town。
  - 以真形濾，序依級（state>city>town>village）再依 population，上限 200。
  - debounce 600 ms，AbortController，依 shapes JSON 為 key 快取（模組級 Map）。
  - 取敗則區內無名，不阻圖。
- 繪：style 無 glyphs，故用 HTML Marker（`.area-place-*`，pointer-events none）。minzoom：state 5、city 6、town 9、village 12（`PLACE_MINZOOM`）。MapView 以整數 `zoomLevel` 態濾，免逐幀重繪。
- 名取 `name:es`，無則 `name`。
