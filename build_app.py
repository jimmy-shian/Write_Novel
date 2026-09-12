# -*- coding: utf-8 -*-
"""
AI Novel Factory - Unified Local Packaging & Build Tool
小說工廠一鍵打包編譯控制腳本 (Android APK / Windows EXE / NSIS 安裝包)

功能：
1. 支援終端互動式 input() 提示選擇編譯目標
2. 支援 CLI 參數 non-interactive 批次打包 (--target apk|exe|installer|all|web)
3. 採用 mykey / 123456 永久固定簽名金鑰封裝 Android APK
4. 呼叫 NSIS (makensis) 產出單一 Setup 安裝程式 (.exe)
5. 輸出編譯完成產物至 dist-packages/ 目錄
"""

import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import shutil
import subprocess
import argparse
import time
import json
import glob

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
ANDROID_DIR = os.path.join(FRONTEND_DIR, "android")
ELECTRON_DIR = os.path.join(PROJECT_ROOT, "electron")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "dist-packages")


def clean_build_intermediates(verbose: bool = True) -> None:
    """包裝成功後自動清理中間產物，只保留最終成品。

    刪除：
    - build_work/、build/ (PyInstaller 暫存)
    - dist-packages/win-unpacked/ (electron-builder 未壓縮目錄，~400MB)
    - dist-packages/builder-debug.yml、builder-effective-config.yaml
    - dist-packages/*.blockmap、*.nsis.7z (electron-builder 附帶檔)
    - electron/dist/ (electron-builder 舊版輸出)

    保留：
    - dist-packages/AI_Novel_Factory_*_Electron_Portable.exe
    - dist-packages/AI_Novel_Factory_signed.apk
    - dist-packages/AI_Novel_Factory_Backend/ (下次加速用，不重打 PyInstaller)
    """
    def _log(msg: str):
        if verbose:
            print(msg)

    _log("[*] 正在自動清理中間產物（只保留成品）...")

    dirs_to_remove = [
        os.path.join(PROJECT_ROOT, "build_work"),
        os.path.join(PROJECT_ROOT, "build"),
        os.path.join(OUTPUT_DIR, "win-unpacked"),
        os.path.join(ELECTRON_DIR, "dist"),
    ]
    for d in dirs_to_remove:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            _log(f"    [-] 已刪除資料夾: {d}")
        elif os.path.exists(d):
            try:
                os.remove(d)
                _log(f"    [-] 已刪除檔案: {d}")
            except OSError as e:
                _log(f"    [!] 無法刪除 {d}: {e}")

    files_to_remove = [
        os.path.join(OUTPUT_DIR, "builder-debug.yml"),
        os.path.join(OUTPUT_DIR, "builder-effective-config.yaml"),
    ]
    patterns_to_remove = [
        os.path.join(OUTPUT_DIR, "*.blockmap"),
        os.path.join(OUTPUT_DIR, "*.nsis.7z"),
    ]
    for pattern in patterns_to_remove:
        try:
            files_to_remove.extend(glob.glob(pattern))
        except Exception:
            pass

    for f in files_to_remove:
        if os.path.isfile(f):
            try:
                os.remove(f)
                _log(f"    [-] 已刪除檔案: {f}")
            except OSError as e:
                _log(f"    [!] 無法刪除 {f}: {e}")

    _log("[SUCCESS] 中間產物已清理，dist-packages/ 僅保留成品。")
def get_project_version() -> str:
    """Read the app version from root version.json (Single Source of Truth)."""
    version_file = os.path.join(PROJECT_ROOT, "version.json")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            return str(json.load(f).get("version", "0.0.0"))
    except Exception as e:
        raise RuntimeError(f"Failed to read version.json SSOT: {e}")

PYTHON_EXE = sys.executable or r"C:\Users\Administrator\venv\Scripts\python.exe"

def ensure_env_vars():
    """自動偵測並設定 Android SDK 與 JDK 環境變數"""
    local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Administrator\AppData\Local")
    default_sdk = os.path.join(local_app_data, "Android", "Sdk")
    if os.path.exists(default_sdk):
        os.environ["ANDROID_HOME"] = default_sdk
        os.environ["ANDROID_SDK_ROOT"] = default_sdk
        print(f"[+] ANDROID_HOME configured: {default_sdk}")
    
    # 檢查 keytool
    default_jdk = r"C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot"
    if os.path.exists(default_jdk):
        os.environ["JAVA_HOME"] = default_jdk
        jdk_bin = os.path.join(default_jdk, "bin")
        if jdk_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = jdk_bin + os.pathsep + os.environ.get("PATH", "")
        print(f"[+] JAVA_HOME configured: {default_jdk}")

def run_cmd(cmd, cwd=None, check=True):
    print(f"[*] Executing in [{cwd or os.getcwd()}]: {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=False)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {cmd}")
    return res.returncode

def ensure_no_running_app(timeout_sec: int = 30):
    """編譯前關閉正在執行的 App，避免輸出 EXE 被鎖定導致 NSIS/PyInstaller
    出現 "Can't open output file" 而失敗。

    只關閉自家行程 (Electron portable / unpacked / 後端 sidecar)，
    不影響其他程式。非 Windows 平台直接略過。
    """
    if sys.platform != "win32":
        return
    list_cmd = (
        "powershell -NoProfile -Command \""
        "Get-Process | Where-Object { $_.ProcessName -like 'AI_Novel_Factory_*' "
        "-or $_.ProcessName -eq 'AI Novel Factory' } | "
        "Select-Object -ExpandProperty Id\""
    )
    try:
        out = subprocess.run(list_cmd, shell=True, capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f"[!] 無法檢查執行中行程（略過）: {e}")
        return
    pids = [p.strip() for p in (out.stdout or "").split() if p.strip().isdigit()]
    if not pids:
        return
    print(f"[*] 發現正在執行的 App 行程 {pids}，先關閉以釋放輸出檔案...")
    kill_cmd = (
        "powershell -NoProfile -Command \""
        "Get-Process | Where-Object { $_.ProcessName -like 'AI_Novel_Factory_*' "
        "-or $_.ProcessName -eq 'AI Novel Factory' } | Stop-Process -Force\""
    )
    subprocess.run(kill_cmd, shell=True, capture_output=True, timeout=30)
    import time
    for _ in range(timeout_sec * 2):
        time.sleep(0.5)
        out = subprocess.run(list_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if not [p for p in (out.stdout or "").split() if p.strip().isdigit()]:
            print("[+] 已關閉舊 App，輸出檔案已釋放。")
            return
    raise RuntimeError(
        "仍有關不掉的 App 行程，請手動關閉「AI Novel Factory」視窗後再重新編譯。"
    )

def build_web_dist():
    print("\n" + "="*50)
    print("  [Step] 構建前端 Web 發布包 (Vite + React SPA)")
    print("="*50)
    run_cmd("npm run build", cwd=FRONTEND_DIR)
    dist_dir = os.path.join(FRONTEND_DIR, "dist")
    if os.path.exists(dist_dir) and os.path.exists(os.path.join(dist_dir, "index.html")):
        print(f"[SUCCESS] 前端靜態發布包已生成: {dist_dir}")
        return True
    else:
        raise RuntimeError("前端構建完成但未找到 dist/index.html")

def ensure_keystore():
    """確保 release 簽名金鑰庫存在 (Alias: mykey, 密碼: 123456)"""
    keystore_path = os.path.join(ANDROID_DIR, "app", "mykey.keystore")
    if os.path.exists(keystore_path):
        print(f"[+] 找到固定簽名金鑰庫: {keystore_path}")
        return keystore_path
    
    print("[*] 正在生成永久簽名金鑰庫 mykey.keystore (Alias: mykey, 密碼: 123456)...")
    os.makedirs(os.path.dirname(keystore_path), exist_ok=True)
    cmd = (
        f'keytool -genkeypair -v -keystore "{keystore_path}" '
        '-alias mykey -keyalg RSA -keysize 2048 -validity 10000 '
        '-storepass 123456 -keypass 123456 '
        '-dname "CN=AI Novel Factory, OU=Mobile, O=NovelFactory, L=Taipei, ST=Taiwan, C=TW"'
    )
    run_cmd(cmd, cwd=PROJECT_ROOT)
    print(f"[SUCCESS] 簽名金鑰庫建立成功: {keystore_path}")
    return keystore_path

def build_android_apk():
    print("\n" + "="*50)
    print("  [Step] 打包 Android APK (使用 mykey / 123456 簽名)")
    print("="*50)
    ensure_env_vars()
    
    build_web_dist()
    
    print("\n[*] 正在同步 Capacitor 原生工程資源...")
    run_cmd("npx cap sync android", cwd=FRONTEND_DIR)
    
    ensure_keystore()
    
    print("\n[*] 正在呼叫 Gradle 進行 Release APK 編譯與簽名封裝...")
    gradlew_cmd = r".\gradlew.bat assembleRelease" if sys.platform == "win32" else "./gradlew assembleRelease"
    run_cmd(gradlew_cmd, cwd=ANDROID_DIR)
    
    candidate_apk = os.path.join(ANDROID_DIR, "app", "build", "outputs", "apk", "release", "app-release.apk")
    if not os.path.exists(candidate_apk):
        raise FileNotFoundError(f"未找到產出的 APK: {candidate_apk}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    target_apk = os.path.join(OUTPUT_DIR, "AI_Novel_Factory_signed.apk")
    shutil.copyfile(candidate_apk, target_apk)
    
    size_mb = os.path.getsize(target_apk) / (1024 * 1024)
    print("\n" + "*"*60)
    print("  >>> ANDROID APK 打包成功！ <<<")
    print(f"  檔案路徑: {target_apk}")
    print(f"  檔案大小: {size_mb:.2f} MB")
    print("  簽名金鑰: mykey (Password: 123456)")
    print("  升級保證: 本 APK 使用固定金鑰簽署，手機可直接覆蓋升級安裝！")
    print("*"*60 + "\n")
    return target_apk

def build_windows_backend_sidecar():
    """打包 Electron 用無頭後端 sidecar (PyInstaller onedir, 有 console 供 Electron 收集 log)。

    僅包裝用：dev / start.bat / HF 完全不受影響。
    """
    print("\n" + "="*50)
    print("  [Step] 打包 Electron 無頭後端 sidecar (onedir)")
    print("="*50)
    ensure_no_running_app()
    build_web_dist()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("[*] 正在透過 PyInstaller 封裝後端 sidecar...")

    dist_dir_abs = os.path.join(FRONTEND_DIR, "dist")
    data_arg = f"{dist_dir_abs};frontend/dist"

    pyinstaller_cmd = (
        f'"{PYTHON_EXE}" -m PyInstaller '
        f'--noconfirm --clean --onedir --console '
        f'--name "AI_Novel_Factory_Backend" '
        f'--add-data "{data_arg}" '
        f'--hidden-import backend.generation '
        f'--hidden-import backend.persistence '
        f'--distpath "{OUTPUT_DIR}" '
        f'--workpath "{os.path.join(PROJECT_ROOT, "build_work")}" '
        f'"{os.path.join(PROJECT_ROOT, "electron_backend.py")}"'
    )

    run_cmd(pyinstaller_cmd, cwd=PROJECT_ROOT)

    exe_path = os.path.join(OUTPUT_DIR, "AI_Novel_Factory_Backend", "AI_Novel_Factory_Backend.exe")
    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"後端 sidecar 打包失敗，未找到產物: {exe_path}")
    print(f"[SUCCESS] 後端 sidecar 已生成: {exe_path}")
    return exe_path

def sync_electron_version():
    """將 version.json (SSOT) 版本同步至 electron/package.json。"""
    project_version = get_project_version()
    pkg_path = os.path.join(ELECTRON_DIR, "package.json")
    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)
    if pkg.get("version") != project_version:
        pkg["version"] = project_version
        with open(pkg_path, "w", encoding="utf-8") as f:
            json.dump(pkg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[*] electron/package.json 版本已同步為 v{project_version}")
    else:
        print(f"[*] electron/package.json 版本已是 v{project_version}")
    return project_version

def build_electron_portable(clean_after: bool = True):
    """打包 Electron 免安裝獨立視窗版 (portable 單檔 EXE)。

    流程：前端 dist -> 後端 sidecar -> electron-builder portable。
    使用者資料一律落在 %USERPROFILE%\\.ai-novel-factory，與 EXE 位置無關。
    成功後預設自動清理中間產物（win-unpacked 等），僅保留成品。
    """
    print("\n" + "="*50)
    print("  [Step] 打包 Electron 免安裝獨立視窗版 (portable)")
    print("="*50)

    # 0. 先關閉正在跑的 App，否則 NSIS 無法覆寫輸出 EXE ("Can't open output file")
    ensure_no_running_app()

    # 1. 確保後端 sidecar 已存在
    sidecar_exe = os.path.join(OUTPUT_DIR, "AI_Novel_Factory_Backend", "AI_Novel_Factory_Backend.exe")
    if not os.path.exists(sidecar_exe):
        print("[*] 尚未找到後端 sidecar，先執行 PyInstaller 打包...")
        build_windows_backend_sidecar()
    else:
        print(f"[+] 找到後端 sidecar: {sidecar_exe}")

    # 2. 同步版本號
    project_version = sync_electron_version()

    # 3. 安裝 Electron 依賴
    print("[*] 正在安裝 Electron 依賴 (electron / electron-builder)...")
    if os.path.exists(os.path.join(ELECTRON_DIR, "package-lock.json")):
        run_cmd("npm ci", cwd=ELECTRON_DIR)
    else:
        run_cmd("npm install", cwd=ELECTRON_DIR)

    # 4. electron-builder 打包 portable
    print("[*] 正在透過 electron-builder 打包 portable EXE...")
    run_cmd("npx electron-builder --win portable", cwd=ELECTRON_DIR)

    # 5. 檢驗產物 (electron-builder 輸出統一至 dist-packages/)
    candidate = os.path.join(OUTPUT_DIR, f"AI_Novel_Factory_{project_version}_Electron_Portable.exe")
    if os.path.exists(candidate):
        size_mb = os.path.getsize(candidate) / (1024 * 1024)
        print("\n" + "*"*60)
        print("  >>> ELECTRON 免安裝獨立視窗版打包成功！ <<<")
        print(f"  檔案路徑: {candidate}")
        print(f"  檔案大小: {size_mb:.2f} MB")
        print("  使用方式: 雙擊即用，不需安裝、不開瀏覽器")
        print("  資料目錄: %USERPROFILE%\\.ai-novel-factory\\ (novel_factory.db)")
        print("*"*60 + "\n")
        if clean_after:
            try:
                clean_build_intermediates()
            except Exception as e:
                print(f"[!] 自動清理中間產物失敗（不影響成品）: {e}")
        else:
            print("[*] 已依 --no-clean 保留中間產物（win-unpacked 等）。")
        return candidate
    else:
        raise FileNotFoundError(f"electron-builder 執行完成但未找到產物: {candidate}")

def show_interactive_menu():
    while True:
        print("\n" + "="*54)
        print("    小說工廠 (AI Novel Factory) 本地打包工具")
        print("="*54)
        print("  請輸入選項編號以決定編譯目標：")
        print("  [1] 打包 Android APK (使用 mykey/123456 固定金鑰簽名)")
        print("  [2] 打包 Electron 免安裝獨立視窗版 (portable, 不開瀏覽器)")
        print("  [3] 同步編譯全部 (Android APK + Electron)")
        print("  [4] 僅編譯前端 Web 資源包 (frontend/dist)")
        print("  [0] 退出程式")
        print("-" * 54)
        
        try:
            choice = input("請輸入您的選擇 [預設 2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消操作。")
            break
        
        if not choice:
            choice = "2"
        
        if choice == "1":
            build_android_apk()
            break
        elif choice == "2":
            build_electron_portable()
            break
        elif choice == "3":
            build_android_apk()
            build_electron_portable()
            break
        elif choice == "4":
            build_web_dist()
            break
        elif choice == "0":
            print("[*] 退出打包工具。")
            break
        else:
            print("[!] 無效的輸入，請重新選擇 (0 - 4)")

def main():
    parser = argparse.ArgumentParser(description="AI Novel Factory Unified Packaging Tool")
    parser.add_argument(
        "--target",
        choices=["apk", "all", "web", "electron-backend", "electron"],
        default=None,
        help="直接指定打包目標 (非互動模式)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="保留中間產物（win-unpacked、builder-*.yml、build_work 等），預設成功後自動清理",
    )
    args = parser.parse_args()
    clean_after = not args.no_clean

    if args.target:
        if args.target == "apk":
            build_android_apk()
        elif args.target == "all":
            build_android_apk()
            build_electron_portable(clean_after=clean_after)
        elif args.target == "web":
            build_web_dist()
        elif args.target == "electron-backend":
            build_windows_backend_sidecar()
        elif args.target == "electron":
            build_electron_portable(clean_after=clean_after)
    else:
        show_interactive_menu()

if __name__ == "__main__":
    main()
