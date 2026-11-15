# 水 U-Net（/api/water）

- 模：NISAR_UNET_MODELO_V1（UNet in1 out1 base16 depth3，訓唯 Okavango）。淨權 `backend/app/water/unet_water_v1.pt`（唯 state_dict，weights_only=True 載）+ `.json` 元（mean −10.8395、std 2.4847、閾 0.97、patch 64、overlap 32）。原 ckpt 含 PosixPath，勿直載。
- 端：POST /api/water {bbox:[w,s,e,n], date?} → 搜 CMR NISAR_L2_GCOV_V1/BETA 最新（≤date）；取前三景，擇有效覆 ≥0.5 者（幀沿軌切，最新或僅邊角）。HTTP 範圍讀 HHHH+mask（4MB 塊並行預取）→ mask 1–254 → average 至 30m（景之 UTM）→ 10log10 → z → Hann 拼。返 JSON {id, scene_id, datetime, bounds, threshold, water_fraction, valid_fraction, read_mb, timings, png_url}；GET /api/water/{id}.png（3857，藍漸，p≤0.05 透明）。邊 >60 km 400；無景 404；他 502。快取 data/water/<sha(bbox,景)>.{json,png}。
- 時：45 km 冷 ~22–40 s（讀 50–110 MB 為主，推理 ~2 s），快取 ~1 s。
- 依：torch（CPU index，pyproject 有 uv 源）、h5py。backend venv 無 pip：`python -m pip --python <abs venv python> install ...`。
- 前：Sidebar「Agua (U-Net)」節；區＝最後之 study area bbox，否則所選興趣點方。MapView `waterOverlay` image 層，透明度滑桿。
- 測：tests/test_water.py（例檔 tests/data/water，對 prediccion_clase 一致 >99%）。
