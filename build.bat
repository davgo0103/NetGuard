@echo off
chcp 65001 >nul
echo ====================================
echo   NetGuard 打包工具
echo ====================================
echo.

:: 檢查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10+
    pause
    exit /b 1
)

:: 安裝依賴
echo [1/3] 安裝依賴套件...
pip install -r requirements.txt
if errorlevel 1 (
    echo [錯誤] 安裝依賴失敗
    pause
    exit /b 1
)

:: 打包
echo.
echo [2/3] 使用 PyInstaller 打包...
pyinstaller --noconfirm --onefile --windowed ^
    --name NetGuard ^
    --add-data "config.json;." ^
    --icon NONE ^
    --uac-admin ^
    net_guard.py

if errorlevel 1 (
    echo [錯誤] 打包失敗
    pause
    exit /b 1
)

:: 複製設定檔到輸出目錄
echo.
echo [3/3] 複製設定檔...
copy /Y config.json dist\config.json >nul

echo.
echo ====================================
echo   打包完成！
echo   輸出: dist\NetGuard.exe
echo   設定: dist\config.json
echo ====================================
echo.
echo 使用方式：
echo   1. 以管理員身份執行 dist\NetGuard.exe
echo   2. 程式會常駐在系統托盤
echo   3. 右鍵托盤圖示可操作
echo.
pause
