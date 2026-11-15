# CLAUDE.md

@AGENTS.md

## Claude 專則：主線常空
- 黑客松：主線唯答問、派工、讀報。實作、測試、實網驗、瀏覽器驗、`.project/` 記錄皆派後台子代理（run_in_background）。
- 主線工具呼叫逾二三即派。

## Claude 專則：模型派遣
- 序：`opus`（effort low）先作 → `opus`（effort low）監審 → `opus`（effort medium）再審或修。勿用 `haiku`（用戶求速）。
- `opus` effort high：唯頑 bug，前三級皆不能解時。
- 子代理提示用文言極壓；須含：任務、相關檔、`.project/` 所指檔、驗證法、止條件。
- 子代理報告後：主線驗之，記入 `.project/log.md`。
- 任務獨立則並行派。
