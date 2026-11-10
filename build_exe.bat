@echo off
cd /d "%~dp0"
set PY=py -3.12
%PY% --version >nul 2>&1 || set PY=py
%PY% -m pip install -r requirements.txt pyinstaller || goto :fail
%PY% -m PyInstaller --noconfirm --windowed --name DisplayCompanion --icon assets\icon.ico --add-data "assets;assets" --hidden-import pyaudiowpatch --collect-all vosk --hidden-import serial.tools.list_ports run_screenlink.py || goto :fail
echo.
echo Built: dist\DisplayCompanion\DisplayCompanion.exe
if /i not "%1"=="nopause" pause
exit /b 0
:fail
echo.
echo Build failed. Install Python 3.12 from python.org (tick "py launcher") and run again.
if /i not "%1"=="nopause" pause
exit /b 1
