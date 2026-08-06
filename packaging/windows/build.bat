@echo off
setlocal enabledelayedexpansion

rem Build the self-contained "SC RS Scanner" app folder for Windows.
rem Run this from anywhere -- it locates the project by its own path.
rem
rem Prerequisites (one-time, on the machine doing the BUILDING -- not
rem needed by end users of the finished app):
rem   1. Python 3.9+ installed and on PATH.
rem   2. A Tesseract-OCR install, copied into packaging\windows\tesseract_bundle\
rem      (see README.md in this folder for exact steps).

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..\..

echo === SC RS Scanner - Windows build ===
echo.

if not exist "%SCRIPT_DIR%tesseract_bundle\tesseract.exe" (
    echo ERROR: tesseract_bundle\tesseract.exe not found.
    echo.
    echo Before building, copy your Tesseract-OCR install folder into:
    echo   %SCRIPT_DIR%tesseract_bundle\
    echo so that this file exists:
    echo   %SCRIPT_DIR%tesseract_bundle\tesseract.exe
    echo.
    echo See README.md in this folder for the exact steps.
    exit /b 1
)

if not exist "%SCRIPT_DIR%tesseract_bundle\tessdata\eng.traineddata" (
    echo ERROR: tesseract_bundle\tessdata\eng.traineddata not found.
    echo Make sure you copied the whole Tesseract-OCR folder, tessdata included.
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: python not found on PATH. Install Python 3.9+ from python.org
    echo and make sure "Add python.exe to PATH" was checked during install.
    exit /b 1
)

echo Creating build virtual environment...
python -m venv "%SCRIPT_DIR%build_venv"
if errorlevel 1 (
    echo ERROR: failed to create virtual environment.
    exit /b 1
)

call "%SCRIPT_DIR%build_venv\Scripts\activate.bat"

echo Installing dependencies...
pip install --upgrade pip >nul
pip install -r "%PROJECT_ROOT%\requirements.txt"
if errorlevel 1 (
    echo ERROR: failed to install requirements.txt
    exit /b 1
)

pip install pyinstaller
if errorlevel 1 (
    echo ERROR: failed to install pyinstaller
    exit /b 1
)

echo.
echo Running PyInstaller...
pushd "%SCRIPT_DIR%"
pyinstaller sc_rs_scanner.spec --distpath dist --workpath build --noconfirm
set BUILD_RESULT=%errorlevel%
popd

call "%SCRIPT_DIR%build_venv\Scripts\deactivate.bat"

if not "%BUILD_RESULT%"=="0" (
    echo.
    echo ERROR: PyInstaller build failed. See output above.
    exit /b 1
)

echo.
echo === Build complete ===
echo Output folder: %SCRIPT_DIR%dist\SC RS Scanner\
echo.
echo Test it by running:
echo   "%SCRIPT_DIR%dist\SC RS Scanner\SC RS Scanner.exe"
echo.
echo To build a proper one-click installer from this folder, see the
echo Inno Setup steps in README.md.
