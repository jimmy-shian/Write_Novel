@echo off
rem 本檔必須是 Big5 (cp950) 編碼 + CRLF 換行，否則 cmd 會解析失敗
title AI Novel Factory - 一鍵啟動
cd /d "%~dp0"

echo ==============================================
echo   AI Novel Factory (AI 小說工廠) 一鍵啟動
echo ==============================================
echo.

rem ---------- 1. Python ----------
set "PYTHON=C:\Users\Administrator\venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [!] 找不到專用虛擬環境，改用系統 python
    set "PYTHON=python"
)
"%PYTHON%" --version
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10+。
    pause
    exit /b 1
)

rem ---------- 2. 依賴檢查 ----------
"%PYTHON%" -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo [*] 正在自動安裝 requirements.txt ...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [錯誤] 依賴安裝失敗。
        pause
        exit /b 1
    )
)

rem ---------- 3. 前端 dist 檢查 ----------
if not exist "frontend\dist\index.html" (
    echo [!] 找不到 frontend\dist\index.html，正在自動構建前端 ...
    pushd frontend
    call npm install
    if errorlevel 1 (
        echo [錯誤] npm install 失敗，請確認已安裝 Node.js 18+。
        popd
        pause
        exit /b 1
    )
    call npm run build
    popd
    if not exist "frontend\dist\index.html" (
        echo [錯誤] 前端構建失敗，後端仍可啟動，但首頁會顯示 UI files missing。
        pause
    ) else (
        echo [OK] 前端構建完成。
    )
) else (
    echo [OK] 前端 dist 已就緒。
)

rem ---------- 4. Port 選擇（支援 start.bat 8001 直接指定） ----------
set "PORT=8000"
if not "%~1"=="" (
    set "PORT=%~1"
    goto port_check
)
echo.
echo [?] 5 秒後自動使用 port 8000 啟動，要自訂請按數字鍵。
del "%TEMP%\AI_Novel_port.txt" 2>nul
"%PYTHON%" "scripts\prompt_port.py" > "%TEMP%\AI_Novel_port.txt"
if exist "%TEMP%\AI_Novel_port.txt" ( set /p PORT=<"%TEMP%\AI_Novel_port.txt" ) else ( set "PORT=8000" )
del "%TEMP%\AI_Novel_port.txt" 2>nul
echo.
if "%PORT%"=="" set "PORT=8000"
echo [*] 使用 port %PORT% 啟動。

:port_check
echo %PORT%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo [!] port 輸入無效，已改用 8000。
    set "PORT=8000"
)

rem ---------- 5. 檢查 port 是否被佔用 ----------
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [!] Port %PORT% 已被佔用，可能服務已在執行中。
    echo [*] 直接幫你開啟瀏覽器: http://127.0.0.1:%PORT%/
    start "" "http://127.0.0.1:%PORT%/"
    pause
    exit /b 0
)

echo.
echo [*] 正在啟動後端: backend.app @ http://127.0.0.1:%PORT%/
echo [*] 啟動後會自動開啟瀏覽器，關閉此視窗即停止服務。
echo [*] 按 Ctrl+C 可停止服務。
echo.

rem 延遲 3 秒後自動開瀏覽器（背景執行，不阻塞主服務）
if not "%SKIP_BROWSER%"=="1" (
    start /min powershell -noprofile -command "Start-Sleep 3; Start-Process 'http://127.0.0.1:%PORT%/'"
)

rem ---------- 6. 啟動服務（正式模式，不用 --reload 更穩定） ----------
"%PYTHON%" -m uvicorn backend.app:app --host 127.0.0.1 --port %PORT%

echo.
echo [*] 服務已停止。
pause
