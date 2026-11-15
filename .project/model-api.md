# 外模接口（約；三代理共守）

- 枝：proyecto-nasa-app-2026-2。旨：模離後台，獨程於用戶本機，以 HTTP 拉式連。後台唯備數、收果、繪、推前端。
- 式：HTTP 拉 + 工隊 + SSE。無 WebSocket。模可以 curl 試。
- 權：token = secrets.token_urlsafe(24)，存記憶，TTL 2h，一 token 一網頁會話。模呼皆 `Authorization: Bearer <token>`。SSE 以 `?token=`（EventSource 不能設頭）。無效/過期 → 401。
- 連態：模 last_seen（hello 或 jobs/next 時更）≤ 30 s 則 connected。

## 端（前綴 /api/models）
- `POST /token` → `{token, expires_at}`（網頁）。
- `POST /hello` Bearer `{name, output:"probability"|"continuous"|"classes", pols?:["HH",...], label?, units?}` → `{ok:true}`（模）。pols 預 ["HH"]，唯 HH/HV/VV/VH，他 → 400。舊 `kind:"water_prob"`（無 output）→ probability。
- `GET /status` Bearer → `{connected, name, output, label, units, pols, last_seen}`。
- `POST /jobs` Bearer `{bbox:[w,s,e,n], date?}` → `{job_id}`（網頁）。邊 >60 km 400。
- `GET /jobs/next` Bearer，長輪 ≤25 s → 200 `{job_id, bbox, date, pols, input_url}` 或 204（模）。取則態 running。
- `GET /jobs/{id}/input.tif` Bearer → GeoTIFF float32，帶依 job pols 序（pols 取自建 job 時之 hello），各帶 description = 極化名，dB，30 m，景之 UTM，nodata NaN。tag：scene_id、datetime、pols、units=dB。擇景、讀、mask、average、10log10 同 water/service.py 法。首取則備（冷 22–40 s），後快取（鍵含 pols）。無景或景缺極化 → job error 404（言缺何、有何）。
- `POST /jobs/{id}/result` Bearer multipart `file`=1 帶 GeoTIFF float32，同 input 格 → 後台繪 PNG 3857，job done。繪依 output：probability→藍漸，≤0.05 透明；continuous→p2–p98 viridis，NaN 透明；classes→整數類（非 0 ≤12 類，逾 → 400），Tableau 調色依值升序，0/NaN 透明。
- `GET /jobs/{id}.png` → PNG（無權，id 難猜可）。
- `GET /events?token=` SSE：`event: status` data `{connected, name, output, label, units, pols}`；`event: job` data `{job_id, state: queued|running|done|error, output, label, units, pols, scene_id?, datetime?, bounds?, stats?:{min,max,mean,fraction?}, legend?:{min,max}|{classes:[{value,color}]}, png_url?, error?}`。fraction 唯 probability（p≥0.5 佔有效比）。water_fraction 已去。

## 分工
- 後台（backend/）：新 router `routers/models.py` + `app/models_api/`（記憶庫、工隊）。重用 water/service.py 之預處理，勿改其行為；/api/water 暫存。
- 離模（model_service/water_unet/）：獨立 Python 客：載 unet_water_v1.pt（複製，勿動 backend），循 hello → jobs/next → input.tif → 推理 → result。參：`--url`、`--token`（或環境 LUZSI_URL、LUZSI_TOKEN）。
- 前端（frontend/）：「Agua (U-Net)」節改「Modelo propio」連接設計。
