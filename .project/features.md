# 自然地物全球目錄（已實作）

## 因
- 用戶厭「Cubierta arbórea」覆蓋率法。欲搜全球名地物（bosques、humedales、desiertos、glaciares…），一 label 一地，點之飛往、可設 AOI。

## 數據
- `backend/app/data/features.json`（211 條，177 KB，8188 點，最多 801）：id（slug）、name、category、lon/lat（bbox 心）、bbox、source、geometry（簡化多邊形）。
- 簡化：NE 以 shapely simplify 0.05° preserve_topology，坐標 3 位。手補大者 OUTLINES 粗環（8–18 點）；餘手補用 bbox 矩形；火山半徑約 15 km 16 點圓。
- 生：`backend/scripts/build_features.py <NE 目錄>`。源 Natural Earth 10m（公域）：geography_regions_polys（Desert、Tundra、Wetlands、Delta；名取 NAME_ES；SKIP 去誤類）、glaciated_areas 有名者；另手補 MANUAL（selvas、bosques、manglares、humedales、glaciares）與 VOLCANOES（點±0.15°）。名同則留首。
- 類：desert 58、glacier 77、volcano 27、wetland 25、jungle 10、forest 9、mangrove 7、tundra 3。NE 冰原名多英。
- pyproject 加 package-data `data/*.json`。

## 後端
- `routers/features.py`：GET /api/features?q=&category=。q 合類詞（西/英、去重音，CATEGORIES 表）則回全類；否則名模糊（前綴>詞首>子串）。GET /api/features/categories 回類計。列表不帶 geometry（輕）；GET /api/features/{id} 帶之，404 無者。POST /api/features/search {q,category,areas:[GeoJSON]}：shapely 真相交（prep）濾，誤幾何 422。測 `tests/test_features.py`。

## 前端
- `features.ts`：fetchFeatures、CATEGORY_PLURAL/COLOR、groupLabel。
- SearchBar：打字 250 ms 去抖請 /api/features；段「{類} (mundo)」：「Mostrar N … en el mapa」列＋各地物列（點則飛往並單 label；＋則加 AOI）。Nominatim 照舊 Enter。
- 地覆列降次：唯有作用區時現，置自然段後。
- MapView：每地物一 Marker label（色點＋名），點則飛往、bbox 虛框；作用者現「+ Área」鈕加 AOI（rectangle＝bbox）。繪時隱。
- CoverChips 增 labels chip「Volcanes 27 ×」清 label。

## AOI 濾
- 後端 `bbox=minx,miny,maxx,maxy` 可重複；地物 bbox 與任一相交則留，誤式 422。
- 後端 bbox 參留作後備。前端 `aoiGeometries(polygons)` 傳 AOI 多邊形至 POST /search；有則段標「(en área)」，AOI 變重取。無果示「Ningún lugar natural en el área seleccionada.」＋「Buscar en todo el mundo」（越濾，query/AOI 數變則復）。
- 圖 labels（多者）亦濾於 AOI（前端仍以 bbox，無 geometry）；單點選者不濾。
- 選地物：先 bbox 預覽，`fetchOutline(id)`（快取）至則換多邊形（虛線＋淡填）。「+ Área」加 kind region 以多邊形；取敗則退 bbox 矩形。

## 遺
- 手補中小者無輪廓（bbox 矩形）。多 labels 前端濾仍 bbox。
