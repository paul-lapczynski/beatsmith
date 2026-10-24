@echo off
rem Builds the BeatSmith app and its installers:
rem   dist\BeatSmith\BeatSmith.exe          the app, runnable as-is
rem   dist\BeatSmith-<version>.msi        the MSI installer
rem   dist\BeatSmith-setup-<version>.exe  an .exe installer too, if Inno Setup is installed
rem It installs what it needs to build (Python, the .NET SDK, WiX) with winget if missing.
rem See BUILD.md.
setlocal
cd /d "%~dp0"
if "%BEATSMITH_VERSION%"=="" set BEATSMITH_VERSION=0.0.1

rem ---- build tools --------------------------------------------------------
where py >nul 2>nul || (
  echo Installing Python...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements || goto :fail
  set "PATH=%LOCALAPPDATA%\Programs\Python\Launcher;%PATH%"
)
where dotnet >nul 2>nul || (
  echo Installing the .NET SDK, needed for WiX...
  winget install -e --id Microsoft.DotNet.SDK.8 --accept-package-agreements --accept-source-agreements || goto :fail
  set "PATH=%ProgramFiles%\dotnet;%PATH%"
)
set "PATH=%USERPROFILE%\.dotnet\tools;%PATH%"
where wix >nul 2>nul || (
  echo Installing WiX 5...
  dotnet tool install --global wix --version 5.0.2 || goto :fail
)
wix extension add -g WixToolset.UI.wixext/5.0.2 >nul || goto :fail

rem ---- the app ------------------------------------------------------------
if not exist .venv (
  py -3 -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r ..\requirements.txt -r ..\requirements-app.txt pyinstaller || goto :fail

if not exist ffmpeg\ffmpeg.exe (
  echo Fetching ffmpeg for .wma/.m4a support...
  powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip -OutFile ffmpeg.zip; Expand-Archive ffmpeg.zip ffmpeg-tmp -Force; New-Item -ItemType Directory ffmpeg -Force | Out-Null; Get-ChildItem ffmpeg-tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1 | Copy-Item -Destination ffmpeg\ffmpeg.exe; Remove-Item ffmpeg.zip; Remove-Item ffmpeg-tmp -Recurse"
  if not exist ffmpeg\ffmpeg.exe echo   (couldn't fetch ffmpeg; the app still works for mp3/ogg/wav/flac)
)

pyinstaller --noconfirm --clean --distpath dist --workpath build beatsmith.spec || goto :fail

rem ---- installers ---------------------------------------------------------
python harvest.py dist\BeatSmith files.wxs || goto :fail
wix build beatsmith.wxs files.wxs -arch x64 -ext WixToolset.UI.wixext -d Version=%BEATSMITH_VERSION% -o dist\BeatSmith-%BEATSMITH_VERSION%.msi || goto :fail
rem a real build is well over 100 MB; a tiny MSI means the app files didn't go in
for %%F in (dist\BeatSmith-%BEATSMITH_VERSION%.msi) do if %%~zF LSS 50000000 (
  echo The MSI is only %%~zF bytes, so the app files are missing from it.
  goto :fail
)

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
rem BEATSMITH_SKIP_EXE=1 skips it (test builds only need the MSI)
if not "%BEATSMITH_SKIP_EXE%"=="1" if exist %ISCC% %ISCC% installer.iss

echo.
echo Done. Installer: %~dp0dist\BeatSmith-%BEATSMITH_VERSION%.msi
exit /b 0

:fail
echo.
echo Build failed (see the error above).
exit /b 1
