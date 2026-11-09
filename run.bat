@echo off
cd /d "%~dp0"
set PY=py -3.12
%PY% --version >nul 2>&1 || set PY=py
%PY% -m pip install -q -r requirements.txt
%PY% run_screenlink.py
pause
