@echo off
cd /d "%~dp0"
py -3.13 -c "import PyQt5" >nul 2>&1
if not errorlevel 1 (
    py -3.13 main.py %*
) else (
    python main.py %*
)
