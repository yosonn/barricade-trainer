@echo off
setlocal
cd /d "%~dp0"

set PYTHON_EXE=C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo Starting 20 Expert-vs-Expert Barricade.gg games...
echo This can take a while because every move calls the remote Expert API.
echo.

"%PYTHON_EXE%" tools\barricade_external\collect_expert_selfplay.py --games 20 %*

echo.
echo Finished. Outputs are under backtest_runs\expert-vs-expert-20-YYYYMMDD-HHMMSS.
pause
