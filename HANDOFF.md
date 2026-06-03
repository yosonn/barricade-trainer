# Barricade Trainer / AI 對戰系統交接紀錄

版本：2026.06.03.12  
GitHub：<https://github.com/yosonn/barricade-trainer>  
主要專案位置：`C:\Yoson\BarricadeTrainer`

## 專案目標

這是一套 Barricade / Quoridor 類型遊戲的輔助與 AI 對戰系統。目標是讓使用者可以：

- 在訓練器輸入實戰棋譜，取得下一步推薦。
- 使用圖形棋盤點擊移動、拖曳放牆。
- 查看雙方最短路、剩餘牆、勝率估計、局勢判斷。
- 使用獨立 AI 對戰頁進行玩家對電腦、上方玩家模式、雙電腦互玩。
- 雙電腦模式可分別設定紅方與藍方搜尋秒數、最大深度。
- 賽後回放支援回到起始、播放、倒回、快轉、回到最新局面。

所有介面文字預設使用繁體中文。

## 目前檔案結構重點

- `barricade_trainer.py`：核心規則、路徑計算、搜尋演算法、評估函數。
- `barricade_web.py`：本機 HTTP server 與 `/api/analyze` API。
- `test_barricade_trainer.py`：回歸測試，目前 18 個測試。
- `barricade_frontend/index.html`：訓練器頁面。
- `barricade_frontend/app.js`：訓練器互動邏輯。
- `barricade_frontend/ai.html`：獨立 AI 對戰頁面。
- `barricade_frontend/ai.js`：AI 對戰、雙電腦、回放邏輯。
- `barricade_frontend/app.css`：共用樣式。

## 啟動方式

PowerShell：

```powershell
cd C:\Yoson\BarricadeTrainer
python barricade_web.py --port 8765
```

開啟：

- 訓練器：`http://127.0.0.1:8765/`
- AI 對戰：`http://127.0.0.1:8765/ai.html`

## 搜尋參數意義

搜尋秒數：AI 每次決策最多可以思考多久。數字越大通常越穩，但會更慢。  
最大深度：AI 往後預判幾層半手。例如深度 3 約等於「我走、對手走、我再走」。

數值越大不保證一定越強，因為如果評估函數有盲點，深搜可能只是更深地重複錯誤。實戰建議：

- 手機或快速測試：0.2 到 0.5 秒，深度 3。
- 一般分析：0.5 到 1 秒，深度 4。
- 較強測試：1 到 3 秒，深度 4 或 5。

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

評估函數包含：

- 雙方最短路差距。
- 剩餘牆價值。
- 牆資源保留。
- 終局 tempo。
- 合法移動數與路徑彈性。
- 路徑控制與卡位價值。
- 避免立即來回無效移動。
- 優勢收官策略。

## 重要修正紀錄

### 1. 前端訓練器

完成項目：

- 棋盤顯示優化，棋子大小、牆顯示、代碼標籤更清楚。
- 全介面改成繁體中文。
- 顯示雙方剩餘牆、最短步數、勝率估計、局勢判斷。
- 支援點棋盤移動。
- 支援拖曳橫牆、直牆放置。
- 輸入錯誤不會寫進棋譜，避免卡死。
- 放牆超過 10 面會阻止寫入並提示。
- 支援上一步。
- 系統推薦會在棋盤上顯示淺色預覽。
- 右側新增採用推薦按鈕。
- 版本號顯示在介面上，避免 Render/快取造成混淆。

### 2. AI 對戰頁

完成項目：

- 新增獨立 `ai.html`，不混入原本訓練器。
- 模式包含玩家對電腦、上方玩家、雙電腦互玩。
- 上方玩家模式維持左下角是 `a1`，使用者看到的代碼與實際輸入一致。
- 上方玩家模式可選玩家先手或電腦先手。
- 電腦移動後會顯示移動箭頭。
- 最新放置的牆會用不同顏色提示。
- 雙電腦模式可分別調紅方與藍方搜尋秒數、最大深度。
- 回放支援回到起始、倒回、播放、快轉、回到最新局面。
- 回放不再重新執行 AI 搜尋，只照棋譜快速重建局面。
- 自動對戰等待時會顯示目前是哪一方在思考，避免誤以為紅藍參數反了。

### 3. 後端與演算法

已針對多盤敗局做回歸修正：

- 避免對手剩一步到終點時沒有防守。
- 避免中後期來回無效移動。
- 強化牆資源管理，尤其是最後幾面牆。
- 如果自己已經領先，不再用低效牆浪費資源。
- 如果對手剩很多牆、自己剩很少牆，會更保守。
- 新增優勢收官策略：自己 4 步內到終點且對手至少慢 6 步時，優先直接前進，不再繼續蓋迷宮。

最新一次關鍵修正：

使用者提供敗局：

```text
e2 e8 e3 e7 e4 e6 he2 he7 hd5 hd4 d4 f6 c4 f5 c5 hb5 hf4 e5 hb4 f5 vf5 e5 vc5 f5 vf7 f6 vc7 va6 b5 va3 a5 e6 hd6 f6 vb8 f7 a6 e7 a7 ha7 a6 d7 a5 d8 a4 e8 a3 f8 a2 f9 b2 g9 c2 g8 c3 vg6 d3 g7 e3 vh6 f3 g6 g3 g5 g4 h5 h4 h3 h5 h2 h6
```

敗因分析：紅方第 33、35 手附近已經大幅領先，紅方距離終點只剩 4 步，藍方還要 14 到 16 步，但 AI 仍建議紅方消耗最後兩面牆，導致後期沒有防守資源。已加入 `race_conversion_adjustment` 與 `should_convert_race_by_sprinting` 修正。

回測結果：

- 原本第 33 手推薦 `hd6`，現在推薦 `a6`。
- 原本第 35 手推薦 `vb8`，現在推薦 `a6`。

## 測試狀態

目前測試：18 個，全部通過。

常用檢查指令：

```powershell
cd C:\Yoson\BarricadeTrainer
python -m unittest -v
node --check barricade_frontend\ai.js
node --check barricade_frontend\app.js
```

最後確認結果：

- `python -m unittest -v`：18 passed。
- `node --check barricade_frontend\ai.js`：通過。
- `node --check barricade_frontend\app.js`：通過。

## 已知注意事項

- PowerShell 有時會把繁體中文顯示成亂碼，但檔案本身是 UTF-8。檢查中文內容時可用 Python `unicode_escape` 或直接在瀏覽器確認。
- 修改 UI 文字時，若在 PowerShell 腳本中寫中文，容易造成亂碼。建議用 UTF-8 編輯器、`apply_patch`，或使用 Unicode escape / HTML entity。
- 每次推新版都要同步更新：
  - `barricade_web.py` 的 `APP_VERSION`
  - `index.html` 顯示版本與 cache busting query
  - `ai.html` 顯示版本與 cache busting query
- 使用者非常重視實戰勝率。每次輸局都應該保留棋譜，找出關鍵局面並加入回歸測試。

## 後續可優化方向

建議下一階段：

- 加入自我對弈 benchmark，統計不同參數與策略版本勝率。
- 加入 opening book，避免開局重複進入容易失衡的局面。
- 對低牆終局加入更深的 pawn-race solver。
- 針對「洞口僵持」與「對手長廊衝刺」建立更多回歸局面。
- 調整勝率估計，目前只是由 heuristic score 轉換，不是嚴格勝率。
- 若要追求更強，可研究 Monte Carlo Tree Search、Proof Number Search、強化學習或自我對弈資料調參。

## 最新 Git 狀態

最新已推送版本：`2026.06.03.12`  
最新 commit：`a3575dc Improve race conversion strategy`
