@echo off
title AI Novel Factory - 本地編譯工具
cd /d "%~dp0"

:menu
echo.
echo ==================================================
echo   AI Novel Factory - 本地編譯 / 執行選單
echo ==================================================
echo   [1] 編譯 Electron 免安裝版 (獨立視窗 portable EXE)
echo   [2] 編譯 Android APK
echo   [3] 全部編譯 (APK + Electron)
echo   [4] 本地開發啟動 (網頁版)
echo   [5] 直接執行已編好的 Electron 版
echo   [6] 清理暫存 (build_work / win-unpacked)
echo   [0] 離開
echo --------------------------------------------------
set "CHOICE_="
set /p CHOICE_=請輸入選項 [預設 1]:
if "%CHOICE_%"=="" set "CHOICE_=1"

if "%CHOICE_%"=="1" goto build_electron
if "%CHOICE_%"=="2" goto build_apk
if "%CHOICE_%"=="3" goto build_all
if "%CHOICE_%"=="4" goto dev_run
if "%CHOICE_%"=="5" goto run_electron
if "%CHOICE_%"=="6" goto clean
if "%CHOICE_%"=="0" exit /b 0
echo [!] 無效的輸入，請重新選擇。
goto menu

:build_electron
python build_app.py --target electron
if errorlevel 1 ( echo [失敗] Electron 編譯失敗。 & pause & goto menu )
echo [完成] 產物在 dist-packages\
pause
goto menu

:build_apk
python build_app.py --target apk
if errorlevel 1 ( echo [失敗] APK 編譯失敗。 & pause & goto menu )
echo [完成] 產物在 dist-packages\
pause
goto menu

:build_all
python build_app.py --target apk
if errorlevel 1 ( echo [失敗] APK 編譯失敗。 & pause & goto menu )
python build_app.py --target electron
if errorlevel 1 ( echo [失敗] Electron 編譯失敗。 & pause & goto menu )
echo [完成] APK + Electron 皆已編譯。
pause
goto menu

:dev_run
call start.bat
goto menu

:run_electron
set "FOUND="
for %%F in (dist-packages\AI_Novel_Factory_*_Electron_Portable.exe) do (
  set "FOUND=%%F"
)
if not defined FOUND (
  echo [!] 找不到已編好的 Electron 版，請先選 [1] 編譯。
  pause
  goto menu
)
echo [*] 執行 %FOUND%
start "" "%FOUND%"
goto menu

:clean
echo [*] 清理 PyInstaller 暫存與 Electron 輸出...
if exist build_work rmdir /s /q build_work
if exist build rmdir /s /q build
if exist dist-packages\win-unpacked rmdir /s /q dist-packages\win-unpacked
del /q dist-packages\builder-debug.yml dist-packages\builder-effective-config.yaml 2>nul
del /q dist-packages\*.nsis.7z 2>nul
del /q dist-packages\*.blockmap 2>nul
if exist electron\dist rmdir /s /q electron\dist
echo [完成] 下次編譯會重建 (較慢)。
pause
goto menu
