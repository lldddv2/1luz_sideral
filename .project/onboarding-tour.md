# 入門導覽
- 庫：driver.js 1.14.0（MIT）。檔 frontend/src/tour.ts：startTour()、autoStartTour()。
- 鍵：localStorage `tour-seen-v1`；始時方寫（避 StrictMode 雙效）；讀寫包 try/catch，不可讀則不啟。
- 啟：App useEffect 首訪延 800ms 自啟；側欄 rail「Ver guía」（Compass，data-tour=tour-btn）重啟。
- selector 約：`data-tour` = search（SearchBar 根）、rail、rail-{sectionId}、panel、timeline（acq-bar）、map（map-area）、tour-btn。
- 步序：歡迎（居中）→ search → rail（Siguiente 先點 rail-layers 開圖層）→ panel（Capas）→ timeline（無區則不在 DOM，driver 居中示）→ map → tour-btn 結語。
- 樣：styles.css 末 `.tour-popover`，用主題變數。
