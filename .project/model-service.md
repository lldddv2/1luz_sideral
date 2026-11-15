# 離模客（model_service/water_unet/）

- 旨：U-Net 水模獨程於用戶本機，守 model-api.md 約。不依 backend 碼。
- 檔：model.py（UNet 複＋predict Hann 拼＋predict_db：dB→功率→predict）、client.py（Client.hello/step/run、infer_tif）、__main__.py、權 .pt/.json 複。
- 跑：`python -m water_unet --url http://localhost:8000 --token <T>`（或 LUZSI_URL/LUZSI_TOKEN）。401 → 止，返 2。工錯記而續；輪錯睡 3 s 再 hello。
- input_url 若相對則接 --url 根。出 GeoTIFF 承 input profile，float32，nodata NaN，deflate。
- 測：`cd model_service; ../backend/.venv/Scripts/python.exe -m pytest -p no:cacheprovider`（pytest.ini pythonpath=.）。對 prediccion_clase >99%；偽 session 驗一輪、204、401。
- 注：backend venv 之 iniconfig 曾壞（唯 __pycache__），已刪重裝 2.3.1。
