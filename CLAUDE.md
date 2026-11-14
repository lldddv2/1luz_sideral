# CLAUDE.md

@AGENTS.md

## Claude 專則：模型派遣
- 序：`haiku`（effort max）先作 → `opus`（effort low）監審 → `opus`（effort medium）再審或修。
- `opus` effort high：唯頑 bug，前三級皆不能解時。
- 子代理提示用文言極壓；須含：任務、相關檔、`.project/` 所指檔、驗證法、止條件。
- 子代理報告後：主線驗之，記入 `.project/log.md`。
- 任務獨立則並行派。
