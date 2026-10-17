@echo off
rem Double-click to start NOOR on Windows.
rem First time: creates a private Python environment in .venv and installs numpy, pandas and
rem matplotlib (needs internet once). After that it starts straight away, offline.
setlocal
cd /d "%~dp0"
title NOOR - Climate Intelligence

if exist ".venv\Scripts\pythonw.exe" goto run

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython
%PY% -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul || goto nopython

echo Setting up NOOR for the first time (about a minute)...
%PY% -m venv .venv || goto failed
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements.txt || goto failed
".venv\Scripts\python.exe" app.py --init || goto failed

:run
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:nopython
echo.
echo NOOR needs Python 3.12 or newer (with Tkinter, which the normal installer includes).
echo Download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then double-click "Start NOOR.bat" again.
echo.
pause
exit /b 1

:failed
echo.
echo Setup did not finish. Check the internet connection and try again.
echo To start over, delete the .venv folder next to this file.
echo.
if exist ".venv" rmdir /s /q ".venv"
pause
exit /b 1
