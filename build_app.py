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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
ANDROID_DIR = os.path.join(FRONTEND_DIR, "android")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "dist-packages")
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

def build_windows_exe():
    print("\n" + "="*50)
    print("  [Step] 打包 Windows 本地桌面免安裝程式 (.EXE)")
    print("="*50)
    build_web_dist()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("[*] 正在透過 PyInstaller 封裝獨立可執行程式...")
    
    dist_dir_abs = os.path.join(FRONTEND_DIR, "dist")
    data_arg = f"{dist_dir_abs};frontend/dist"
    
    pyinstaller_cmd = (
        f'"{PYTHON_EXE}" -m PyInstaller '
        f'--noconfirm --onedir --windowed '
        f'--name "AI_Novel_Factory" '
        f'--add-data "{data_arg}" '
        f'--distpath "{OUTPUT_DIR}" '
        f'--workpath "{os.path.join(PROJECT_ROOT, "build_work")}" '
        f'"{os.path.join(PROJECT_ROOT, "app.py")}"'
    )
    
    run_cmd(pyinstaller_cmd, cwd=PROJECT_ROOT)
    
    exe_path = os.path.join(OUTPUT_DIR, "AI_Novel_Factory", "AI_Novel_Factory.exe")
    if os.path.exists(exe_path):
        print("\n" + "*"*60)
        print("  >>> WINDOWS EXE (免安裝綠色版) 打包成功！ <<<")
        print(f"  程式路徑: {exe_path}")
        print("*"*60 + "\n")
        return exe_path
    else:
        print(f"[!] PyInstaller 已執行完成，輸出目錄: {os.path.join(OUTPUT_DIR, 'AI_Novel_Factory')}")
        return OUTPUT_DIR

def build_nsis_installer():
    print("\n" + "="*50)
    print("  [Step] 編譯 Windows NSIS 單一安裝導引包 (Setup.exe)")
    print("="*50)
    
    # 1. 確保免安裝資料夾已存在
    exe_path = os.path.join(OUTPUT_DIR, "AI_Novel_Factory", "AI_Novel_Factory.exe")
    if not os.path.exists(exe_path):
        print("[*] 尚未找到已編譯的綠色版目錄，先執行 PyInstaller 打包...")
        build_windows_exe()
        
    # 2. 尋找 makensis
    makensis_candidates = [
        "makensis",
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
    ]
    makensis_bin = None
    for cand in makensis_candidates:
        if shutil.which(cand) or os.path.exists(cand):
            makensis_bin = cand
            break
            
    if not makensis_bin:
        raise RuntimeError("未在系統中找到 makensis (NSIS)。請安裝 NSIS 或透過 winget install NSIS.NSIS 進行安裝。")
        
    nsi_script = os.path.join(PROJECT_ROOT, "installer.nsi")
    if not os.path.exists(nsi_script):
        raise FileNotFoundError(f"未找到 NSIS 腳本: {nsi_script}")
        
    print(f"[*] 使用 NSIS 編譯器: {makensis_bin}")
    run_cmd(f'"{makensis_bin}" "{nsi_script}"', cwd=PROJECT_ROOT)
    
    # 檢驗產物
    candidate_setup = os.path.join(OUTPUT_DIR, "AI_Novel_Factory_v4.0.0_Setup.exe")
    if os.path.exists(candidate_setup):
        size_mb = os.path.getsize(candidate_setup) / (1024 * 1024)
        print("\n" + "*"*60)
        print("  >>> NSIS SETUP 安裝包編譯成功！ <<<")
        print(f"  安裝包路徑: {candidate_setup}")
        print(f"  安裝包大小: {size_mb:.2f} MB (LZMA Solid 高壓縮)")
        print("  功能特性: 內建引導精靈、桌面與開始功能表捷徑、完整反安裝器")
        print("*"*60 + "\n")
        return candidate_setup
    else:
        raise FileNotFoundError(f"NSIS 執行完成但未找到產物: {candidate_setup}")

def show_interactive_menu():
    while True:
        print("\n" + "="*54)
        print("    小說工廠 (AI Novel Factory) 本地打包工具")
        print("="*54)
        print("  請輸入選項編號以決定編譯目標：")
        print("  [1] 打包 Android APK (使用 mykey/123456 固定金鑰簽名)")
        print("  [2] 打包 Windows 本地桌面免安裝程式 (.EXE)")
        print("  [3] 打包 Windows NSIS 單一安裝導引包 (Setup.exe)")
        print("  [4] 同步編譯全部 (Android APK + Windows EXE + NSIS 安裝包)")
        print("  [5] 僅編譯前端 Web 資源包 (frontend/dist)")
        print("  [0] 退出程式")
        print("-" * 54)
        
        try:
            choice = input("請輸入您的選擇 [預設 3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消操作。")
            break
        
        if not choice:
            choice = "3"
        
        if choice == "1":
            build_android_apk()
            break
        elif choice == "2":
            build_windows_exe()
            break
        elif choice == "3":
            build_nsis_installer()
            break
        elif choice == "4":
            build_android_apk()
            build_windows_exe()
            build_nsis_installer()
            break
        elif choice == "5":
            build_web_dist()
            break
        elif choice == "0":
            print("[*] 退出打包工具。")
            break
        else:
            print("[!] 無效的輸入，請重新選擇 (0 - 5)")

def main():
    parser = argparse.ArgumentParser(description="AI Novel Factory Unified Packaging Tool")
    parser.add_argument(
        "--target",
        choices=["apk", "exe", "installer", "all", "web"],
        default=None,
        help="直接指定打包目標 (非互動模式)",
    )
    args = parser.parse_args()
    
    if args.target:
        if args.target == "apk":
            build_android_apk()
        elif args.target == "exe":
            build_windows_exe()
        elif args.target == "installer":
            build_nsis_installer()
        elif args.target == "all":
            build_android_apk()
            build_windows_exe()
            build_nsis_installer()
        elif args.target == "web":
            build_web_dist()
    else:
        show_interactive_menu()

if __name__ == "__main__":
    main()
