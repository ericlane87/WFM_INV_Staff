@echo off
setlocal
cd /d "%~dp0"
python update_dashboard.py
if errorlevel 1 (
  echo.
  echo Dashboard update failed.
  pause
  exit /b 1
)
echo.
echo Dashboard data updated. Open dashboard.html to view it.
pause
