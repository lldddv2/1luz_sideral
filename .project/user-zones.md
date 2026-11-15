# 用戶興趣點

- 多點：`UserZone {id, center:[lon,lat], halfSizeKm, name?, note?}`（types.ts）。App 態 `zones[]`、`selectedZoneId`，重載則失。刪選中者則清選。
- 語義：興趣點之方為下載區；Área de estudio（polygons）唯限搜（passes、landcover、NISAR scenes、features、timeline）。不入 polygons。
- 下載：App 以選中點造 `DownloadTarget {id,name,sideKm,geometry,outsideStudy}`（types.ts），入 `useDownload`。geometry 由 `zoneGeometry`（zone.ts）以 id+center+halfSizeKm memo，改名不重置 run，移/改範圍則重置。無選中點則禁「Descargar」並示提示。有 study areas 而方全在其外（bbox 交判）則黃警「El punto está fuera del área de estudio」，不禁。名以 `zoneLabel`。pickNisarDemo 未改（S3 棄）。
- 算：`frontend/src/zone.ts`。km 換度：緯 111.32，經除 cos(lat)。預設邊 10 km；邊限 1–100 km。拖角取較大軸距為 halfSize。
- 置：Sidebar「Puntos de interés」段鈕「Marcar punto」入置點態；點圖一下增一新點（10 km）並選之，即出態。Esc 取消。置點態外點圖不生點。
- 調：各心為 draggable Marker（移其方），四角 Marker 唯選中且方態者有（改範圍，心不動）；置點態中 draggable 關。點心或 pin 則選中。Sidebar 列各點（名或「Punto N」、坐標 3 位），點項選中/收；選中者展 ZoneEditor：坐標（5 位）、「Rango (lado)」滑桿與數入、名、註、Ir a、Eliminar。
- 圖：源 `user-zone` 含諸方（properties id、selected），層 `zone-fill`、`zone-outline`，粉 #db2777；選中者填 0.3、邊 #9d174d 粗 3。名置心右。層序 aoi 上、labels 下。
- 與 DrawMode 互斥：入一則出他。
- 縮示：方屏上邊（map.project 取 bbox 西南東北，取短軸）小則化為 pin（粉，可拖移心，點則 fitBounds 至方，padding 60）；隱方層與角把手。滯回：大於 44 px 現方，小於 36 px 化 pin（`ZONE_SQUARE_SHOW_PX`/`ZONE_SQUARE_HIDE_PX`，MapView.tsx）。每點各算，態為 `zoneExpanded: Set<id>`。onMove、onLoad、zones 變時重算。拖後之 click 以 ref 略之（onDragEnd setTimeout 清）。
