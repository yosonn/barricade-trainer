@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "ENGINE=expert"
set "NPX_EXE=C:\Program Files\nodejs\npx.cmd"

if not exist "%PYTHON_EXE%" (
  echo Could not find bundled Python:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

echo Starting Barricade.gg live sync assistant...
echo.
echo A browser window will open. Log in or enter a computer/practice game there.
echo This tool prints the recommended move in this terminal.
echo It does not auto-click live human games.
echo.

node -e "const { chromium } = require('playwright'); (async () => { const browser = await chromium.launch({ headless: true }); await browser.close(); })().catch((error) => { console.error(error.message); process.exit(1); });" >nul 2>nul
if errorlevel 1 (
  echo Playwright browser runtime is missing. Installing Chromium now...
  if exist "%NPX_EXE%" (
    "%NPX_EXE%" playwright install chromium
  ) else (
    echo Could not find npx.cmd. Please run:
    echo npm install -D playwright
    echo npx playwright install chromium
    pause
    exit /b 1
  )
)

node tools\barricade_external\barricade_gg_live_bridge.js ^
  --python "%PYTHON_EXE%" ^
  --engine "%ENGINE%" ^
  --copy

echo.
echo Live sync stopped.
pause
