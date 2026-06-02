# Barricade 離線訓練器

這是一個 Barricade / Quoridor 類型棋局的離線訓練、AI 模式、自我對弈與賽後復盤工具。

重要：barricade.gg 條款禁止正式線上對局中使用外部程式或 AI 給步。請把這個工具用在離線練習、私下自測、AI 模式、開局研究或賽後分析。

## 怎麼開啟前端

在 PowerShell 進入這個資料夾：

```powershell
cd "C:\Users\user\OneDrive - 國立東華大學\文件\New project"
```

啟動網頁工具：

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' barricade_web.py
```

看到這行代表成功：

```text
Barricade Trainer running at http://127.0.0.1:8765
```

接著用瀏覽器打開：

```text
http://127.0.0.1:8765
```

如果 8765 被占用，可以換埠：

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' barricade_web.py --port 8899
```

然後打開 `http://127.0.0.1:8899`。

要停止工具，在啟動它的 PowerShell 視窗按 `Ctrl+C`。

## 前端怎麼操作

1. 先選擇你的陣營：
   - `我先手 紅`：你從 `e1` 往第 9 排走。
   - `我後手 藍`：你從 `e9` 往第 1 排走。

2. 如果輪到你：
   - 看「目前推薦」。
   - 想照推薦走，按 `採用推薦`。
   - 如果你自己走了別步，在輸入框填你的走法，按 `我這步自己動了`。

3. 如果輪到對手：
   - 在輸入框填對手剛走的那一步。
   - 按 `對手剛剛走了`。
   - 系統會更新局面；如果接下來輪到你，就重新算推薦。

4. 如果你有完整棋譜：
   - 直接貼到「整段棋譜」。
   - 按 `重新分析`。

5. 進階設定：
   - `每次搜尋秒數`：建議 0.3 到 1.0 秒。
   - `最大深度`：建議 3；越高越慢。

## 走法與牆的輸入格式

棋子移動只填目的地：

```text
e2
f6
```

障礙物用方向加錨點：

```text
hd5
ve4
```

也可以把方向放後面，例如 `d5h`。

目前定義：

- `hd5`：橫牆，擋住第 5 排與第 6 排之間，跨 `d`、`e` 兩欄。
- `ve4`：直牆，擋住 `e`、`f` 兩欄之間，跨第 4、5 兩排。

## 命令列用法

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' barricade_trainer.py --history "1. e2 e8 2. e3 e7 3. e4 e6 4. hd5 ve4" --time 0.5 --depth 3
```

輸出會包含目前輪到誰、雙方位置、剩餘牆數、最短路徑，以及離線訓練推薦。

## 已建模規則

- 9x9 棋盤，座標 `a1` 到 `i9`。
- 紅方從 `e1` 開始，到第 `9` 排勝。
- 藍方從 `e9` 開始，到第 `1` 排勝。
- 每回合只能走棋子或放一面牆。
- 每方開局 10 面牆。
- 牆長度為 2，分橫牆和直牆。
- 放牆後雙方都必須仍有路能到終點。
- 棋子可上下左右移動，不能穿牆。
- 與對手相鄰時，使用 Quoridor 類跳躍/斜跳規則。

## 目前演算法

- BFS 計算雙方最短路。
- 只優先產生雙方最短路附近的候選牆，降低耗時。
- 使用 iterative deepening alpha-beta / negamax 搜尋。
- 評分依據包含：你和對手最短路差距、剩餘牆數、推進程度。

下一步可以加強：更好的牆候選排序、開局庫、局面快取編碼、自我對弈調參。
