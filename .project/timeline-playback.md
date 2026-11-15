# 時序播放（先預載後速播）
- 幀：layers.ts buildFrames 以 mosaic 瓦合成每過境日一 PNG（OffscreenCanvas→objectURL），MapView 以單 image Source 換 url。prefetchKey（AOI box+passDays）變則棄重建；不變則留（同 AOI+範圍再播不重載）。
- 態：App `play` = off|loading|on。按 play→loading（必開 NISAR），MapView `onFramesReady` 報有幀之日（建畢方報，建中 null）→ on；<2 幀則 off。
- 播：FRAME_MS=450，唯行 readyDays（無幀日略）。passDays 變→off。
- UI：AcquisitionTimeline `loading` prop：鈕成 Loader2 spin（按則取消），文「Preparando animación… Teselas/ N/M」。
- 換幀：Source url 釘首幀；後幀解為 ImageBitmap 以 updateImage({image}) 推（避 maplibre 圖隊飢）。
- 未覆：取消唯止播，後台建幀續行（為快取）；未逐幀 img.decode；未瀏覽器實驗。
