@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "ENGINE=expert"

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

node tools\barricade_external\barricade_gg_live_bridge.js ^
  --python "%PYTHON_EXE%" ^
  --engine "%ENGINE%" ^
  --copy

echo.
echo Live sync stopped.
pause
