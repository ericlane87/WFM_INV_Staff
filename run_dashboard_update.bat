@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set RUN_DATE=%%d-%%b-%%c
for /f "tokens=1-3 delims=:." %%a in ("%time%") do set RUN_TIME=%%a%%b%%c
set RUN_TIME=%RUN_TIME: =0%
set LOG_FILE=logs\dashboard_update_%RUN_DATE%_%RUN_TIME%.log

echo Writing log to %LOG_FILE%
where py >nul 2>&1
if not errorlevel 1 (
  py -3 update_dashboard.py > "%LOG_FILE%" 2>&1
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Neither py nor python was found. > "%LOG_FILE%"
    echo Install Python from python.org and select "Add python.exe to PATH", or install the Windows Python launcher. >> "%LOG_FILE%"
    cmd /c exit /b 1
  ) else (
    python update_dashboard.py > "%LOG_FILE%" 2>&1
  )
)
if errorlevel 1 (
  echo.
  echo Dashboard update failed.
  echo See log: %LOG_FILE%
  type "%LOG_FILE%"
  pause
  exit /b 1
)
echo.
echo Dashboard data updated. Open dashboard.html to view it.
echo See log: %LOG_FILE%
pause
