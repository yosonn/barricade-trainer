# Barricade Trainer Deployment

版本：2026.06.04.03

這個專案有 Python 後端，所以 GitHub Pages 不能完整部署。建議使用 Render Python Web Service。

## Local Run

一般環境：

```powershell
cd C:\Yoson\BarricadeTrainer
python barricade_web.py --port 8765
```

目前 Codex 工作環境：

```powershell
cd C:\Yoson\BarricadeTrainer
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' barricade_web.py --port 8765
```

Open:

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/ai.html
```

## GitHub

Repository:

```text
https://github.com/yosonn/barricade-trainer
```

推送流程：

```powershell
cd C:\Yoson\BarricadeTrainer
git status --short --branch
git add <changed-files>
git commit -m "Describe change"
git push origin main
```

## Render

建立 Python Web Service，連到 GitHub repository。

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
python barricade_web.py
```

專案會讀取 Render 的 `PORT` 環境變數；部署時會綁定 `0.0.0.0`。

## Public URLs

Trainer:

```text
https://YOUR_RENDER_URL/
```

AI battle:

```text
https://YOUR_RENDER_URL/ai.html
```

API:

```text
POST https://YOUR_RENDER_URL/api/analyze
```

## Version Checklist

每次演算法或前端行為更新後，部署前確認：

- `barricade_web.py` 的 `APP_VERSION` 已更新。
- `barricade_frontend/index.html` 的版本顯示與 query string 已更新。
- `barricade_frontend/ai.html` 的版本顯示與 query string 已更新。
- `python -m unittest -v` 通過。
- `node --check barricade_frontend\ai.js` 通過。
- `node --check barricade_frontend\app.js` 通過。
