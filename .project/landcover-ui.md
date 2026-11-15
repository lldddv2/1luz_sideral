# 地覆濾之介面（前端已實作；後端 /api/landcover 已成）

## 搜欄合一（已實作）
- SearchBar 兼搜地名（Nominatim）與地覆。placeholder：「Buscar lugar o cobertura (p. ej. humedales)…」。
- 下拉二段：上「Coberturas en {作用區名}」（色點、類名、% 自 /stats），下「Lugares」（Nominatim 如舊）。
- 無作用區：地覆段禁，註「Selecciona un área para filtrar coberturas」。
- 作用區同 Descarga 與 timeline 所用（列末區）。

## 同義詞（已實作，`landcover.ts` 之 SYNONYMS）
- wetland：humedal(es)、pantano、ciénaga、turbera、marisma
- tree：bosque(s)、selva、árboles、forestal
- snow_ice：glaciar(es)、hielo、nieve
- water：agua、lago、laguna、río、embalse
- cropland：cultivo(s)、agrícola、agricultura
- built_up：urbano、ciudad、construido
- mangrove：manglar(es)
- grassland：pastizal、pradera、pasto
- shrubland：matorral、arbustos
- bare：desierto、suelo desnudo、árido
- moss：musgo、liquen、tundra
- 比對（matchCover）：小寫、去重音、前綴合；詞內首字亦合（desnudo 合 suelo desnudo）；不足二字不合。key 以後端 /classes 所返為準，上表僅映射。

## 擇類之後（已實作）
- 欄下現 chip（可多）：「● Humedal 12,4 % ×」。chip 即濾態。
- 濾態變：POST /api/landcover/mask（geometry=作用區，classes=chips）得 PNG+bounds，作 MapLibre image source，透明 0.7，置 AOI 框下。
- 區變或刪：清 mask，stats 重請（快取以區 id）。

## Sidebar「Coberturas」節（次，已實作）
- 作用區各類 % 橫條（色同 mask），點條則增/去 chip，與搜欄共態。

## 態（已實作於 `useLandcover.ts`）
- 實作：filter: string[]；stats 以區 id 為鍵之 StatsEntry；mask 以區 id+排序之 classes 為鍵，{url, bounds} | null。
- 新件均已建：`landcover.ts`（types、fetchClasses/fetchStats/fetchMask、SYNONYMS、matchCover）、`useLandcover.ts`（hook）、`components/CoverChips.tsx`。SearchBar 增 props：coverSuggestions、onPickCover。

## 實作異與遺
- 搜欄寬 380→440 px：placeholder 全示，Ctrl K 留。
- 列點擊：增/去 chip，清搜字、收列。Enter 仍只搜地名。
- 錯誤以狀態碼譯西語：422「Área no válida o demasiado grande.」（後限 bbox 2 000 000 km²，大區降解至 STATS_MAX_PX）、502「No se pudo leer la cobertura WorldCover.」。
- 遺：編輯區幾何不刷 stats、mask（同 passes，以區 id 為鍵）；422、502 態與 chip 小轉未實測。

## 後期（若有時；未作）
- 「humedales en Antioquia」：析「X en Y」，Y 走 Nominatim 入區，X 入 chip。示範佳。
- 地覆作 NISAR 掩：每類 σ0 HH/HV 統計，供極化論。
