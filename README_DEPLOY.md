# Barricade Trainer Deployment

This project has a Python backend, so GitHub Pages alone is not enough.
Recommended setup:

1. Push this folder to GitHub.
2. Create a Python Web Service on Render.
3. Open the Render public URL on your phone or any computer.

## Local Run

```powershell
cd "C:\Yoson\BarricadeTrainer"
python barricade_web.py --port 8765
```

Open:

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/ai.html
```

## GitHub

```powershell
cd "C:\Yoson\BarricadeTrainer"
git init
git add .
git commit -m "Initial Barricade trainer"
```

Create a new GitHub repository, then run the remote commands GitHub gives you.
Example:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/barricade-trainer.git
git branch -M main
git push -u origin main
```

## Render

Create a new Web Service from your GitHub repository.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
python barricade_web.py
```

The app supports Render's `PORT` environment variable and binds to `0.0.0.0`
when deployed.

## Public URLs

Trainer:

```text
https://YOUR_RENDER_URL/
```

AI battle:

```text
https://YOUR_RENDER_URL/ai.html
```
