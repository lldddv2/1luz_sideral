# 外模後台（/api/models）

- 檔：`backend/app/models_api/store.py`（Store：sessions、jobs、每 token 二 asyncio.Queue：pending 予模、events 予 SSE；TTL 2h；connected ≤30 s）、`raster.py`（build_input、render_result）、`routers/models.py`；main.py 註 router，`app.state.models_dir = data/models`。
- 端依 model-api.md。jobs/next 長輪 25 s（每 10 s 更 last_seen）。SSE 每 10 s：連態變則 status，否則 `: ping`。
- input：raster._read_pols（仿 service._read_power，任 HH/HV/VV/VH，一讀多帶，缺極化 NoScene）；重用 service.search、RemoteFile、_chunk_blocks；擇景（前三，有效 ≥0.5）→ 10log10 → GTiff float32 deflate，tag scene_id/datetime。快取 data/models/<sha(bbox,date,pols)>.{tif,json}。service.py 未改。實網 Okavango 16 km：冷 20.7 s，快取 0.01 s。
- result：驗 shape、CRS、transform 同 input；依 job.output 繪（probability 用 service.prob_png；continuous/classes 於 raster.py）；回 stats、legend；fraction = p≥0.5。png data/models/<job_id>.png。Job 建時抄 session 之 pols/output/label/units。
- 錯：hello pols 非法 400；401 無/過期 token；400 bbox >60 km 或 result 格異（job error）；404 無景（job error）；502 Earthdata 他誤（job error）；409 未取 input 而送 result。
- 測：tests/test_models_api.py（mock build_input）。test_dem 二敗與此無關。
