# Barricade Trainer

## Current Status: 2026.06.04.09

The production web/API backend still uses the tuned alpha-beta search in
`barricade_trainer.py`. MCTS remains an experimental candidate backend, enabled
only through the backtest tool with `--baseline-engine mcts` or
`--candidate-engine mcts`.

New backtest options:

- `--baseline-engine alpha-beta|mcts`
- `--candidate-engine alpha-beta|mcts`
- `--baseline-simulations`
- `--candidate-simulations`

Version `2026.06.04.07` replaces the old "current hint" area in `ai.html` with
an AI real-time analysis visualization. The `/api/analyze` response now includes
an `analysis` block with engine name, side-to-move perspective, verdict,
strategy notes, and ranked candidate moves with tactical reasons.

Version `2026.06.04.08` adds a loss decision audit tool:
`tools/barricade_backtest/audit_losses.py`. It reads backtest `games.jsonl`
files, audits lost games for a selected engine, compares actual moves against
alpha-beta recommendations, and writes `loss_audit.json` / `loss_audit.md`.

Version `2026.06.04.09` fixes the AI battle UI layout after the realtime
analysis panel was added. The board now stays top-aligned and scales to the
available viewport height, while the analysis rail and candidate list scroll
inside their own containers instead of pushing the board out of view.

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
