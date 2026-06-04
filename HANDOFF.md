# Barricade Trainer / AI 對戰系統交接紀錄

版本：2026.06.04.03

最新 commit：`1a55844 Add depth-gated corridor race synthesis`

GitHub：<https://github.com/yosonn/barricade-trainer>

主要專案位置：`C:\Yoson\BarricadeTrainer`

## 專案目標

這是一套 Barricade / Quoridor 類型遊戲的輔助、AI 對戰與回測系統。目標是讓使用者可以：

- 在訓練器輸入實戰棋譜，取得下一步推薦。
- 使用圖形棋盤點擊移動、拖曳放牆。
- 查看雙方最短路、剩餘牆、勝率估計、局勢判斷。
- 使用獨立 AI 對戰頁進行玩家對電腦、上方玩家模式、雙電腦互玩。
- 分別設定紅方與藍方搜尋秒數、最大深度。
- 賽後回放到任何一步，不重新搜尋。
- 使用回測工具比較不同參數與歷代演算法版本。

所有介面文字預設使用繁體中文。

## 目前檔案結構

- `README.md`：GitHub 首頁與主要使用說明。
- `README_barricade_trainer.md`：舊 README 入口，指向 `README.md`。
- `README_DEPLOY.md`：部署說明。
- `HANDOFF.md`：交接紀錄與目前狀態。
- `barricade_trainer.py`：核心規則、路徑計算、搜尋演算法、評估函數。
- `barricade_web.py`：本機 HTTP server 與 `/api/analyze` API。
- `test_barricade_trainer.py`：回歸測試，目前 22 個測試。
- `barricade_frontend/index.html`：訓練器頁面。
- `barricade_frontend/app.js`：訓練器互動邏輯。
- `barricade_frontend/ai.html`：獨立 AI 對戰頁面。
- `barricade_frontend/ai.js`：AI 對戰、雙電腦、回放邏輯。
- `barricade_frontend/app.css`：共用樣式。
- `tools/barricade_backtest/backtest_loop.py`：回測工具。
- `tools/barricade_backtest/README.md`：回測工具說明。

## 啟動方式

PowerShell：

```powershell
cd C:\Yoson\BarricadeTrainer
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' barricade_web.py --port 8765
```

開啟：

- 訓練器：`http://127.0.0.1:8765/`
- AI 對戰：`http://127.0.0.1:8765/ai.html`

## 核心演算法目前狀態

目前 AI 使用：

- BFS / shortest path 計算雙方到終點距離。
- `movement_path` 把跳棋與斜跳納入路徑距離。
- Alpha-beta Negamax 搜尋。
- Iterative deepening：逐層加深直到時間到。
- Transposition table：避免重複局面計算。
- Killer move / history heuristic：改善剪枝排序。
- Focused wall generation：主要產生阻擋雙方路徑附近的牆。
- Quiescence extension：接近終局或有立即威脅時額外延伸一層。

評估與策略包含：

- 雙方最短路差距。
- 剩餘牆價值與牆資源保留。
- 終局 tempo。
- 合法移動數與路徑彈性。
- 路徑控制與卡位價值。
- 避免立即來回無效移動。
- 優勢收官策略。
- 大幅領先時優先衝刺，不浪費最後牆。
- 低牆落後時避免低效延遲牆。
- 深度 3 以上 opening book：標準開局後藍方採 `hd4`。
- 深度 4 以上 low-wall corridor sprint：低牆、明顯落後、長廊競速時優先縮短自己的路徑。

## 最近重要修正

### 2026.06.04.03

整合歷代模型策略，新增 depth-gated corridor race synthesis。

原因：歷代 round-robin 顯示 `587be6e` 的 endgame corridor 版本在高設定下對目前版有優勢。分析後發現它在低牆長廊競速中較不容易被低效牆或繞路拖走。

修正：

- 新增 `should_simplify_corridor_race()`。
- 在 `max_depth >= 4` 且雙方低牆、自己明顯落後、對手尚非立即一手勝時，只保留能縮短自己路徑的 pawn sprint 作為根節點候選。
- 新增 `test_deeper_search_simplifies_losing_low_wall_corridor_race` 回歸測試。

驗證：

- 22 個 Python 測試全部通過。
- `node --check barricade_frontend\ai.js` 通過。
- `node --check barricade_frontend\app.js` 通過。
- 新整合版對 8 個歷史版本，高設定 `depth=4 time=0.12`，16 局 11 勝 5 敗，勝率 68.75%。
- 一般 local baseline `depth3 vs depth2`，30 局勝率 80%，errors 0。

### 2026.06.04.02

針對使用者提供敗局：

```text
e2 e8 e3 e7 e4 e6 he2 he6 hd5 vc4 e5 d6 vc6 hf5 f5 hh5 hd7 vd3 ve7 e6 hg6 f6 e5 g6 hc2 hd4 f5 h6 f4 i6 hb1 i7 g4 h7 g3 hg2 h3 vh3 h4 hg4 g4 h8 vg8 h7 f4 g7 f5 g8 vf8 g7 g5 f7 h5 f8 i5 f9 i4 e9 i3 d9 i2 c9 h2 b9 g2 b8 f2 b7 e2 b6 d2 b5 c2 vb2 d2 b4 d1 b3 c1 b2 b1 a2 a1
```

敗因：紅方低牆且落後時，仍把牆用在只能拖慢藍方 2 步的低效防守牆上。修正後第 43 手附近優先 `f4`，第 49 手附近優先 `g5`。

驗證：

- 21 個 Python 測試全部通過。
- 30 局本機回測 candidate 96.67%，baseline 3.33%，errors 0。

### 2026.06.04.01

新增 depth-gated opening book。標準開局 `e2 e8 e3 e7 e4` 後，`max_depth >= 3` 時藍方固定採用較深搜尋偏好的 `hd4`。

驗證：

- 19 個 Python 測試全部通過。
- 30 局複驗 candidate 80%，baseline 16.67%，draw/no result 3.33%，errors 0。

### 2026.06.03.12

新增 race conversion 策略。當自己已大幅領先且接近終點時，優先衝刺，不再浪費最後牆。

## 回測工具狀態

目前 `tools/barricade_backtest/backtest_loop.py` 支援：

- `--mode local`：直接 import 本機 engine，速度穩定，不依賴 Render。
- `--mode api`：打部署後的 `/api/analyze`。
- baseline/candidate 互換紅藍。
- 輸出 `games.jsonl`、`summary.json`、`summary.md`。
- `--fail-on-errors` 與 `--fail-under-candidate-rate` 可做 CI gate。

## 常用檢查指令

```powershell
cd C:\Yoson\BarricadeTrainer
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest -v
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check barricade_frontend\ai.js
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check barricade_frontend\app.js
```

## 維護規則

- 每次演算法優化完成後，一律更新版本號、commit、push 到 GitHub。
- 版本號需同步更新：
  - `barricade_web.py` 的 `APP_VERSION`
  - `barricade_frontend/index.html`
  - `barricade_frontend/ai.html`
- 每次輸局都保留棋譜，找出關鍵局面並加入回歸測試。
- 回測數據需記錄在 `backtest_runs/`，但該資料夾不進 git。

## 後續優化方向

- 建立固定 opening suite，降低單一起始局面造成的紅藍偏差。
- 將歷代版本 round-robin 工具正式加入 `tools/barricade_backtest`。
- 針對 `587be6e` 類 corridor endgame 建立更多回歸局面。
- 對零牆終局加入更嚴格的 pawn-race solver。
- 調整勝率估計，目前仍是 heuristic score 映射，不是嚴格勝率。
## 2026.06.04.04 MCTS-lite Segment

Current segment implemented the first practical AlphaGo/AlphaZero-inspired
piece: an experimental MCTS-lite backend. It does not replace the production
alpha-beta AI yet. It gives the project a measurable playground for policy
priors, value estimates, rollout strategy, and future self-play data.

Changes:

- Added `barricade_mcts.py`.
- Added backtest engine switches: `--baseline-engine`, `--candidate-engine`,
  `--baseline-simulations`, and `--candidate-simulations`.
- Added MCTS unit coverage for legal opening selection and immediate win.

Verification:

- 24 Python unit tests passed.
- MCTS-lite smoke tournament passed with errors 0.
- Smoke result: alpha-beta depth 3 vs MCTS-lite 80 simulations, 6 games,
  candidate 50%, baseline 50%.

Next recommended segment: improve MCTS priors with tactical/race features,
add rollout/value calibration, then rerun larger cross-model tournaments before
promoting it over alpha-beta.

## 2026.06.04.05 MCTS v2 Segment

Production backend clarification: the web/API backend still uses the tuned
alpha-beta engine in `barricade_trainer.py`. MCTS is still an experimental
candidate backend used by the local backtest runner only.

Changes:

- Added tactical MCTS policy priors through `action_prior_score()`.
- Added short deterministic rollout value before backpropagation.
- Connected root `avoid_actions` to MCTS and added fallback when all root moves
  are avoided.
- Added tests for MCTS avoid-action behavior and fallback.

Verification:

- 26 Python unit tests passed.
- MCTS v2 smoke: alpha-beta depth 3 vs MCTS 80 simulations, 6 games, candidate
  83.33%, baseline 16.67%, errors 0.

## 2026.06.04.06 Tournament Diagnostics Segment

Production backend remains alpha-beta. This segment focused on making MCTS
optimization harder to fool with short samples.

Changes:

- Backtest summary now includes `engine_side_results`.
- Backtest markdown now prints engine kind, simulations, max actions, and
  rollout depth.
- CLI now exposes MCTS tuning controls for baseline and candidate engines:
  `--baseline-max-actions`, `--candidate-max-actions`,
  `--baseline-rollout-depth`, `--candidate-rollout-depth`,
  `--baseline-mcts-exploration`, and `--candidate-mcts-exploration`.

Results:

- 20-game extended test, alpha-beta depth 3 vs MCTS 80 simulations: candidate
  50%, baseline 50%, errors 0.
- Four short 6-game sweep configs ranged from 66.67% to 100% candidate win rate.
- Best short config was rollout depth 2, max actions 20, simulations 120, but a
  12-game confirmation returned to 50% / 50%.

Decision:

- Do not promote MCTS to production yet.
- Next useful step is a larger automated tuning harness or game-position audit
  that explains where MCTS diverges from alpha-beta in its losses.
