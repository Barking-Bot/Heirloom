@echo off
REM Double-click to start Heirloom on Windows.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 start_heirloom.py) else (python start_heirloom.py)
if errorlevel 1 (
  echo.
  echo Heirloom needs Python 3. Get it free from https://www.python.org/downloads/
  echo During install, tick "Add python.exe to PATH".
)
pause
