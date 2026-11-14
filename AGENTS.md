# AGENTS.md — 1luz_sideral（NASA Space Apps 2026 · Dancing with the SARs）

## 啟
- 每會話首讀 `.project/INDEX.md`，依需讀所指之檔。勿全讀。
- 支援代理唯三：Claude Code、Codex、Antigravity。他者不設。

## 題
- 建互動應用：用 NISAR（NASA-ISRO SAR）雷達數據，追蹤並視覺化地表變化（濕地、火、震、農、冰川、沉降等，擇一或多）。
- 須：選研究區、下載 NISAR 免費數據、互動呈現（變化圖、時序動畫、儀表板、滑桿）、假說物理驅因、論極化。
- 開源、易用。詳見 `.project/challenge.md`。
- 結構：`backend/`、`frontend/`。

## 速
- 黑客松：速為先。勿過建。最小可示即止。
- 先測後報完成。

## 記憶法（`.project/`）
- `INDEX.md`：索引，一行一檔：`- [題](檔.md) — 鉤`。
- 每檔一事，文言極壓（wenyan-ultra）。新事則新檔，舊事則改檔，勿重複。誤則刪。
- `log.md`：決策紀錄，倒序，一行一條：`YYYY-MM-DD 代理: 事。因。`
- 每完一階段：更新相關檔與 `log.md`、`INDEX.md`。
- 勿存代碼可得之事（結構、git 史）。

## 語
- 後台（`.project/`、代理提示、AGENTS.md、CLAUDE.md）：文言極壓。
- 人讀之檔（代碼註釋、文檔、commit、PR、README）：常文，保原語。
- 用戶語：西語。回覆 caveman ultra，保西語。

## 提交
- 格式：`prefix: short description`，英文小寫，無句末點。前綴唯 `feat`、`fix`、`chore`、`docs`。
- 絕不歸功 AI：無 `Co-Authored-By`、無 "Generated with"，不提任何 AI 名。
- 用戶不請則不 commit。

<!-- caveman-begin -->
Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Answer first: Answer, then reason, then next step.
- Kill ceremony: No greeting, hedging, pleasantries, recap, or closer.
- Short word: "fix" not "implement a solution for".
- Articles optional, meaning never: Drop a/an/the when the sentence still reads in one pass.
- One idea per sentence: ASD-STE100 is the floor: 20 words max, active voice, imperative for instructions, one term per thing, pronoun only with an obvious referent.
- Payload verbatim: Code blocks unchanged.
- Tool runs: bounded status: No text between routine calls.
- User's language: Compress the style, not the language.
- Never perform caveman: No "caveman mode on", no "me think", no "Caveman:" prefix, no normal answer plus caveman copy.

Switch: /caveman (default), /ultracave (fragments, each fact once), /megacave (Classical Chinese 文言文)
Stop: "stop caveman" or "normal mode"

Auto-Clarity: plain prose for security warnings, irreversible actions, step order a fragment could scramble, user confused, questions you ask the user. Resume after.

Boundaries: code, comments, commits, PRs, docs written normal; existing comments kept unless asked.
Floor: code, commands, paths, numbers and error strings verbatim; never drop not/never/no/only.
<!-- caveman-end -->
