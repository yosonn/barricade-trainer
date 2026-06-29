# Barricade Trainer

## Current Status: 2026.06.30.07

The production web/API backend now defaults to a hybrid engine. It routes to
MCTS for general midgame planning, and switches to alpha-beta for tactical
endgames, immediate goal threats, low-wall races, and close-contact wall-trap
openings. The API and frontend now support explicit model selection through
`engine: "hybrid"`, `engine: "mcts"`, `engine: "alpha-beta"`, or
`engine: "expert"`.

New backtest options:

- `--baseline-engine alpha-beta|mcts`
- `--candidate-engine alpha-beta|mcts`
- `--baseline-simulations`
- `--candidate-simulations`

Version `2026.06.30.07` improves Expert-mode UI responsiveness in the AI battle
page. Player moves are now validated and rendered immediately with a fast local
no-recommendation analysis, then the slower Expert API recommendation is fetched
only if the next side to move is the computer. Human turns no longer request or
display an Expert recommendation, preventing confusing states where the page
shows an AI move while it is actually the player's turn.

Version `2026.06.30.06` adds the first safe Barricade.gg live-practice
synchronizer. `tools/barricade_external/live_sync_assistant.py` can read a
pasted move history or raw page/network text, reconstruct the longest legal
game history, infer red-first vs blue-first when possible, and ask
Hybrid/MCTS/Alpha-Beta/Expert for the next move. The optional browser bridge
`tools/barricade_external/barricade_gg_live_bridge.js` opens Barricade.gg in a
persistent headed browser profile, watches page text, storage, fetch responses,
and WebSocket frames, then prints the current recommendation. It defaults to
assist-only mode and intentionally does not auto-click live human games.

Quick CLI check:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_external\live_sync_assistant.py `
  --history "e2 e8 e3 e7" `
  --engine hybrid
```

Browser bridge, after installing Playwright for Node:

```powershell
npm install -D playwright
node tools\barricade_external\barricade_gg_live_bridge.js `
  --python "C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" `
  --engine expert `
  --copy
```

Simplest local launch after dependencies are installed:

```powershell
cd C:\Yoson\BarricadeTrainer
.\start_live_sync.cmd
```

This opens a browser window. Log in or open a Barricade.gg computer/practice
game there, then watch this terminal for `recommend=...`. With `--copy` enabled
by the launcher, the latest recommendation is copied to your clipboard.

Version `2026.06.30.05` fixes Expert mode when the top player/blue side starts
first. The Barricade.gg Expert API uses the standard red-first coordinate view,
so blue-first histories are now mirrored before the API call and mirrored back
before local validation. This fixes the previous `Illegal pawn move for blue:
e2` opening error by converting the Expert opening to local `e8`. The trainer
and AI battle pages also now warn when the full move-history textarea was
edited manually and require `重新分析` before using a recommendation, preventing
stale recommendations after correcting a real-game transcription mistake.

Version `2026.06.30.04` integrates Barricade.gg Expert as a selectable live
engine in the trainer and AI battle UI. Selecting `Barricade.gg Expert` sends
the current full move history to the public Barricade.gg AI Socket.IO endpoint
and uses the returned move after validating it against the local rules. This
works in player-vs-computer and computer-vs-computer modes, so either side can
be driven by Hybrid, MCTS, Alpha-Beta, or the external Expert. Because Expert
depends on the remote service, the frontend gives Expert requests a longer
40-second timeout and the backend rejects illegal API-returned moves instead of
applying them. Verification: 49 Python unit tests passed; Python `py_compile`
passed for backend, MCTS, Expert client, and external harness; frontend
`node --check` passed for both JS files.

Version `2026.06.30.03` adds an external Barricade.gg Expert test harness and
improves the backend against next-turn wall traps. The new tool calls the same
public Socket.IO move flow used by `barricade.gg/computer` and can play our
local model against the online Expert bot without manual browser input:

```powershell
python tools\barricade_external\play_barricade_gg.py `
  --difficulty expert `
  --local-side red `
  --local-engine hybrid
```

Two Expert games were captured before tuning: local hybrid lost as red in 52
plies and as blue in 73 plies. The repeated failure pattern was clear: our
model overvalued immediate pawn progress and allowed the Expert bot to use the
next wall to add 4-6 path steps. The engine now scores this next-turn wall
threat directly in alpha-beta ordering, alpha-beta root adjustment, and MCTS
priors. It also has a low-wall safety valve that can spend a final wall when it
defuses a severe next-turn trap without increasing the engine's own route.
Verification: 47 unit tests passed; `py_compile` passed for the backend,
MCTS, backtest, and external Expert harness; frontend `node --check` passed.
After the first tuning pass, a repeat red-side Expert run lasted 62 plies
instead of the previous 52, but still lost, so Barricade.gg Expert remains the
next target opponent rather than a solved benchmark. Local sanity checks:
hybrid vs MCTS, 4 games, 50% / 50%, errors 0; hybrid vs alpha-beta depth 3,
2 games, 100% / 0%, errors 0.

Version `2026.06.30.02` improves the reported strong-computer matchup failure.
The reviewed game showed current hybrid exactly following red's losing choices
while MCTS controlled the early wall fight. Hybrid now routes close pawn-contact
openings with many walls to alpha-beta, which chooses the stronger `hd4` plan
instead of the previous `he2` branch. Local backtests also now use the same
repeat-state avoidance as the live API.

Version `2026.06.30.01` hardens live play against "thinking forever" stalls and
recent-position loops. The frontend now aborts stuck analyze requests and
surfaces a clear timeout error instead of leaving the UI in a permanent loading
state. The backend also adds a recent-state repetition filter so the root move
selection avoids stepping directly back into a board state seen in the last few
plies.

Version `2026.06.06.04` adds the hybrid model and frontend model toggle. The
hybrid engine keeps MCTS 120 as the normal planner, but hands tactical
late-goal and low-wall positions to alpha-beta. This directly targets the loss
pattern from the reviewed game: strong models agreed on path-first recovery
choices, while the real losing line kept bleeding tempo after the first mistake.

Verification: 39 unit tests passed; `py_compile` passed for the web,
alpha-beta, MCTS, and backtest modules; `node --check` passed for the frontend.
Hybrid vs MCTS over 8 local games finished 50% / 50%, and hybrid vs alpha-beta
depth 3 finished 62.5% / 37.5%. HTTP smoke confirmed default `engine=hybrid`
plus explicit `mcts` and `alpha-beta` requests all work.

Version `2026.06.06.03` promotes MCTS 120 to the production web/API default
after promotion testing showed it consistently outperforming alpha-beta depth 3
in local and API-mode checks. The API now accepts `engine: "mcts"` or
`engine: "alpha-beta"`, and the analysis payload reports the active engine so
tooling can verify which model made the recommendation.

Version `2026.06.06.02` improves the production alpha-beta backend in two
audited race positions. First, early/midgame tempo now prefers direct pawn
progress over weak or self-slowing delay walls when both sides are still close
in path distance and the engine has plenty of walls. Second, low-wall trailing
races now treat a no-self-delay wall that adds 2 opponent path steps as a valid
resource spend when the opponent has no walls left. These changes target the
audited `hd3`/`hc7` vs `e6` opening-tempo mistakes and the low-wall `c2` vs
`va3` delay-wall mistake.

Local verification: 37 unit tests passed; `py_compile` passed for
`barricade_web.py`, `barricade_trainer.py`, and `barricade_mcts.py`; alpha-beta
depth 3 vs alpha-beta depth 2 scored candidate 75%, baseline 25%, errors 0.
MCTS 120 simulations remains a strong experimental candidate: an 8-game local
check versus alpha-beta depth 3 scored MCTS 62.5%, alpha-beta 37.5%, errors 0,
so MCTS should stay under evaluation before production promotion.

Version `2026.06.06.01` improves the production alpha-beta backend for
late-goal wall threats. When the side to move is within 4 path steps of the
goal and both players still have walls, root search now checks the opponent's
largest next-turn wall delay. It rewards nearby defensive walls that reduce a
severe future detour threat, even if that wall adds a small amount of own travel
distance. The guard is root-only and gated to severe threats so it behaves like
an endgame safety valve instead of slowing or distorting the whole search tree.

Local verification: 34 unit tests passed; `py_compile` passed for
`barricade_web.py`, `barricade_trainer.py`, and `barricade_mcts.py`; a 4-game
local alpha-beta smoke scored candidate 75%, baseline 25%, errors 0. Production
web/API move selection remains alpha-beta.

Version `2026.06.04.13` improves the experimental MCTS backend by reusing the
alpha-beta race sprint logic inside MCTS candidate filtering, priors, and
rollouts. Low-wall shortest-path progress can override reversal avoidance, which
removes the repeated `f5` vs `f7` step-away failure from the top loss-audit
suspects. Production web/API move selection still remains alpha-beta unless the
backtest tool explicitly selects `--candidate-engine mcts`.

Version `2026.06.04.12` improves the production alpha-beta backend for pure
no-wall pawn races. When both sides have no walls and the side to move is not
behind, root search now focuses on safe pawn moves that shorten the path to the
goal, reducing lateral drift in winning endgames. Local verification: 30 unit
tests passed, the known screenshot loss position still recommends `g5`, and an
8-game depth3-vs-depth2 local smoke scored candidate 75%, baseline 25%,
errors 0.

Version `2026.06.04.11` restores the original AI battle page layout and removes
the realtime analysis panel from the visible UI. The right board rail is back to
the simpler "current hint" panel, and the board/control layout no longer uses
the compressed analysis-specific CSS from versions `.09`/`.10`.

Version `2026.06.04.07` added an AI real-time analysis visualization. The
`/api/analyze` response still includes an `analysis` block for tooling, but the
production `ai.html` interface no longer displays that panel as of
`2026.06.04.11`.

Version `2026.06.04.08` adds a loss decision audit tool:
`tools/barricade_backtest/audit_losses.py`. It reads backtest `games.jsonl`
files, audits lost games for a selected engine, compares actual moves against
alpha-beta recommendations, and writes `loss_audit.json` / `loss_audit.md`.

Version `2026.06.04.09` fixes the AI battle UI layout after the realtime
analysis panel was added. The board now stays top-aligned and scales to the
available viewport height, while the analysis rail and candidate list scroll
inside their own containers instead of pushing the board out of view.

Version `2026.06.04.10` tightens the AI page responsive breakpoint for browser
windows around 1400px wide and allows AI pages to scroll vertically, fixing the
remaining issue where the lower half of the board could be clipped.

Latest extended result: alpha-beta depth 3 vs MCTS 80 simulations, 20 games,
candidate 50%, baseline 50%, errors 0. A parameter sweep found promising
6-game settings, but the best-looking candidate also returned to 50% over a
12-game confirmation run. Conclusion: MCTS is stable as an experimental backend,
but alpha-beta remains the production backend.

版本：2026.06.04.03

GitHub：<https://github.com/yosonn/barricade-trainer>

這是一套 Barricade / Quoridor 類型遊戲的訓練器與 AI 對戰系統。它可以輸入棋譜做局面分析，也可以在網頁棋盤上對戰、雙電腦互玩、回放棋局，並用回測工具比較不同 AI 版本的強度。

## 功能

- 訓練器：輸入實戰棋譜，取得目前局面、合法手、最短路、勝率估計與下一步推薦。
- 圖形棋盤：支援點擊移動、拖曳橫牆/直牆、顯示牆與棋子位置。
- AI 對戰頁：支援玩家對電腦、上方玩家為藍方、雙電腦互玩。
- 搜尋設定：可分別設定紅方與藍方搜尋秒數、最大深度。
- 回放：支援回到起始、倒回、播放、快轉、回到最新局面。
- 回測：支援本機 engine 自我對戰、部署 API 對戰、版本勝率比較。

## 檔案結構

- `barricade_trainer.py`：核心規則、合法手、路徑計算、評估函數、搜尋演算法。
- `barricade_web.py`：HTTP server 與 `/api/analyze` API。
- `test_barricade_trainer.py`：演算法與規則回歸測試，目前 22 個測試。
- `barricade_frontend/index.html`：訓練器頁面。
- `barricade_frontend/ai.html`：AI 對戰頁面。
- `barricade_frontend/app.js`：訓練器互動邏輯。
- `barricade_frontend/ai.js`：AI 對戰、雙電腦、回放邏輯。
- `barricade_frontend/app.css`：共用樣式。
- `tools/barricade_backtest/backtest_loop.py`：回測工具。
- `HANDOFF.md`：專案交接與目前狀態。
- `README_DEPLOY.md`：部署說明。

## 本機啟動

在一般 Python 已加入 PATH 的環境：

```powershell
cd C:\Yoson\BarricadeTrainer
python barricade_web.py --port 8765
```

在目前 Codex 工作環境可用內建 Python：

```powershell
cd C:\Yoson\BarricadeTrainer
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' barricade_web.py --port 8765
```

開啟：

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/ai.html
```

## 棋譜格式

棋子移動使用座標，例如：

```text
e2
f6
```

放牆使用方向加座標：

```text
hd5
ve4
```

- `h`：橫牆。
- `v`：直牆。
- 棋盤座標為 `a1` 到 `i9`。
- 紅方起點為 `e1`，目標列為第 9 列。
- 藍方起點為 `e9`，目標列為第 1 列。

## 命令列分析

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  barricade_trainer.py `
  --history "e2 e8 e3 e7 e4 e6" `
  --time 0.5 `
  --depth 3
```

## 搜尋參數

- 搜尋秒數：AI 每次決策最多思考多久。數字越大通常越穩，但越慢。
- 最大深度：往後預判幾層半手。深度 3 約等於「我走、對手走、我再走」。

建議：

- 快速測試：`time=0.05` 到 `0.2`，`depth=3`。
- 一般對戰：`time=0.3` 到 `1.0`，`depth=3` 或 `4`。
- 強度測試：`time=1.0` 到 `3.0`，`depth=4` 或 `5`。

## 目前 AI 邏輯

目前後端 AI 使用：

- BFS / shortest path 計算雙方到終點距離。
- `movement_path` 納入跳棋與斜跳後的實際移動距離。
- Iterative deepening alpha-beta / negamax 搜尋。
- Transposition table、killer move、history heuristic。
- Focused wall generation，只優先生成路徑附近較可能有效的牆。
- Quiescence extension，在接近終局或立即威脅時額外延伸。
- 牆資源管理，避免低牆時浪費最後防守資源。
- 大幅領先時的 race conversion，優先衝刺而非繼續蓋牆。
- 深度 3 以上的 opening book，標準開局後採用較深搜尋偏好的 `hd4`。
- 深度 4 以上的 low-wall corridor sprint，在低牆且明顯落後的長廊競速中優先縮短自己的路徑。

## 回測

本機快速回測：

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_backtest\backtest_loop.py `
  --mode local `
  --games 30 `
  --time 0.05 `
  --baseline-depth 2 `
  --candidate-depth 3 `
  --fail-on-errors
```

輸出會寫入 `backtest_runs/<timestamp>/`，包含：

- `games.jsonl`
- `summary.json`
- `summary.md`

最近驗證：

- 單元測試：22 個全部通過。
- `node --check barricade_frontend\ai.js`：通過。
- `node --check barricade_frontend\app.js`：通過。
- 版本整合高設定回測：新整合版對 8 個歷史版本 16 局，11 勝 5 敗，勝率 68.75%。
- 一般 local baseline：depth 3 candidate 對 depth 2 baseline，30 局勝率 80%，errors 0。

## 部署

這個專案有 Python 後端，不能只用 GitHub Pages。建議使用 Render Python Web Service。

- Build command：`pip install -r requirements.txt`
- Start command：`python barricade_web.py`

部署後：

```text
https://YOUR_RENDER_URL/
https://YOUR_RENDER_URL/ai.html
```

## 維護規則

- 每次演算法優化完成後，必須更新版本號。
- 同步更新：
  - `barricade_web.py` 的 `APP_VERSION`
  - `barricade_frontend/index.html` 的顯示版本與 cache busting query
  - `barricade_frontend/ai.html` 的顯示版本與 cache busting query
- 每次敗局都保留棋譜，找出關鍵局面並加入回歸測試。
- 完成驗證後 commit 並 push 到 GitHub。
