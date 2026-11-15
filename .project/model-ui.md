# 前端外模連接（節「Modelo propio」）

- 節 id 留 `water`（tour/rail 不碎），名「Modelo propio」，圖示 Plug。約見 model-api.md。模任意（probability/continuous/classes），水 U-Net 僅例。
- 主視極簡：態列（點＋Conectado: name · label／Desconectado）→無 token 主鈕「Conectar modelo」(Plug，呼 regenerate)；有 token 則 `.model-token-row`（複製＋再生）＋未連時灰字「Usa la guía…」→「Ejecutar modelo」(Play)＋一行提示（未連／區名／選區）→次鈕「Guía de uso」(BookOpen，`.model-guide-btn` 全寬)。
- Guía：modal（`.model-modal-backdrop`/`.model-modal`，居中 max 560，Esc、X、點背閉，aria-modal）內七步 curl 全文：1 token（無則示 Conectar 鈕）2 hello＋PowerShell details 3 Ejecutar 4 jobs/next 5 下載 6 處 7 上傳。命令嵌實 origin/token/job_id（無則 `<TOKEN>`/`<job_id>`，步 2+ `.model-dim`）。末註 30 s、curl.exe。app 前無 modal，新建。
- 不自連：入節不取 token；唯按鈕方 POST /api/models/token。sessionStorage `luzsi.modelToken` 存者復開 SSE。token 敗示「No se pudo generar el token (¿backend actualizado?)」。
- `water.ts` `useWater`：SSE status 存 {name,output,label,units,pols}；job done 存 {output,label,units,stats,legend,png_url,bounds,...}。
- 鈕「Ejecutar modelo」未連禁。結果：Listo: label、Escena、ModelLegend（漸條 viridis min–max+units，或 classes 色塊）、stats 一行、Mostrar resultado、透明度滑桿。
- 碼塊 `.model-code`：複製鈕 `.model-copy` 絕對置右上；`.tall` max-height 320 可 resize。樣在 styles.css 末 `.model-*`。
- 疑：漸條色固 viridis，若後端色表異則需對。POST 返 job_id 前 queued 事或失（無害）。
- 節頂「Water model」鈕（Droplets）：`runBuiltin(bbox)` POST /api/water，共 state（busy/error/ready）與 overlay；無區或忙則禁，title 示由。
