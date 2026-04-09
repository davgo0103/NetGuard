@echo off
echo ====================================
echo   NetGuard Build Tool
echo ====================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

:: Build
echo.
echo [2/3] Building with PyInstaller...
pyinstaller --noconfirm --onefile --windowed ^
    --name NetGuard ^
    --add-data "config.json;." ^
    --add-data "logo.png;." ^
    --icon logo.ico ^
    --uac-admin ^
    --collect-data customtkinter ^
    net_guard.py

if errorlevel 1 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

:: Copy assets to output directory
echo.
echo [3/3] Copying assets...
copy /Y config.json dist\config.json >nul
copy /Y logo.png dist\logo.png >nul

echo.
echo ====================================
echo   Build complete!
echo   Output: dist\NetGuard.exe
echo   Config: dist\config.json
echo ====================================
echo.
echo Usage:
echo   1. Run dist\NetGuard.exe as Administrator
echo   2. Program will stay in system tray
echo   3. Right-click tray icon for options
echo.
pause
