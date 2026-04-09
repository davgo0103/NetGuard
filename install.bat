@echo off
chcp 65001 >nul
echo ====================================
echo   NetGuard 快速安裝
echo ====================================
echo.

:: 檢查管理員權限
net session >nul 2>&1
if errorlevel 1 (
    echo 需要管理員權限，正在請求...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 檢查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10+
    pause
    exit /b 1
)

echo [1/2] 安裝 Python 依賴...
pip install -r requirements.txt
if errorlevel 1 (
    echo [錯誤] 安裝依賴失敗
    pause
    exit /b 1
)

echo.
echo [2/2] 安裝完成！
echo.
echo 啟動方式：
echo   python net_guard.py
echo.
echo 或執行 build.bat 打包成 exe
echo.
pause
