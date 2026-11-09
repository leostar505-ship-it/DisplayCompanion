@echo off
cd /d "%~dp0"
call build_exe.bat nopause || goto :fail
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
  echo Installing Inno Setup...
  winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
  if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
  if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
)
if "%ISCC%"=="" goto :fail
"%ISCC%" installer.iss || goto :fail
echo.
echo Installer: %~dp0installer_output\DisplayCompanion-Setup.exe
pause
exit /b 0
:fail
echo.
echo Installer build failed. Install Inno Setup 6 from jrsoftware.org and run again.
pause
exit /b 1
