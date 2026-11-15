# 入門導覽
- 庫：driver.js 1.14.0（MIT）。檔 frontend/src/tour.ts：startTour()、autoStartTour()。
- 鍵：localStorage `tour-seen-v2`（v1→v2 令舊用戶再見）；始時方寫（避 StrictMode 雙效）；讀寫包 try/catch，不可讀則不啟。
- 啟：App useEffect 首訪延 800ms 自啟；側欄 rail「Ver guía」（Compass，data-tour=tour-btn）重啟。
- selector 約：`data-tour` = search（SearchBar 根）、rail、rail-{sectionId}、panel、timeline（acq-bar）、map（map-area）、tour-btn。
- 步序：歡迎（居中）→ search → rail（總覽）→ 節步 study→zones→cover→download→water→layers→about（皆指 panel；SECTION_STEPS 陣；Siguiente/Anterior 經 openSectionThen 點 rail-{id} 開次/前節，aria-current 已開則不點）→ timeline（無區則居中）→ map → tour-btn 結語。終留末節開。
- 樣：styles.css 末 `.tour-popover`，用主題變數。
