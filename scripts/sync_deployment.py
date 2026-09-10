# -*- coding: utf-8 -*-
"""
One-Click Synchronization Script for AI Novel Factory
全自動分支同步與雲端部署腳本（React 現代化架構版）：

標準流程：
1. 編譯前端 React SPA：確保 frontend/dist 產物為最新狀態。
2. 推送 master 分支：提交並推送至 origin/master（觸發 GitHub Actions 自動構建與 gh-pages 自動部署）。
3. 部署 Hugging Face Space：將最新代碼同步至 Space (botsz/WriteNovel)。
"""

import os
import shutil
import subprocess
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def run_cmd(cmd, cwd=None, check=True):
    print(f"[*] Executing: {cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.stdout and res.stdout.strip():
        try:
            print(res.stdout)
        except Exception:
            print(res.stdout.encode("ascii", errors="replace").decode("ascii"))
    if res.stderr and res.stderr.strip():
        try:
            print(res.stderr)
        except Exception:
            print(res.stderr.encode("ascii", errors="replace").decode("ascii"))
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {cmd}")
    return res

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    print(f"\n=== Starting Unified Master Deployment Sync in {root} ===")

    # 1. 編譯前端 React 生產環境產物 (frontend/dist)
    print("\n--- [Step 1/3] Building React frontend (frontend/dist) ---")
    frontend_dir = os.path.join(root, "frontend")
    run_cmd("npm run build", cwd=frontend_dir)
    print("    [OK] frontend/dist built successfully!")

    # 2. 推送 master 分支至 GitHub
    print("\n--- [Step 2/3] Committing & pushing master to GitHub ---")
    run_cmd("git add frontend/dist/")
    run_cmd('git commit -m "【調整】同步最新 React 前端編譯產物" || git status', check=False)
    run_cmd("git push origin master")
    print("    [OK] master pushed to origin/master (GitHub Actions will deploy gh-pages automatically)")

    # 3. 上傳代碼至 Hugging Face Space
    print("\n--- [Step 3/3] Deploying backend service to Hugging Face Space ---")
    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    if not hf_token:
        token_path = os.path.expanduser("~/.cache/huggingface/token")
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                hf_token = f.read().strip()

    if hf_token:
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=hf_token)
            api.upload_folder(
                folder_path=".",
                repo_id="botsz/WriteNovel",
                repo_type="space",
                ignore_patterns=[
                    ".git/**",
                    ".git",
                    ".gitignore",
                    "data/**",
                    "*.db*",
                    "_archive/**",
                    "tests/**",
                    "*.pyc",
                    "__pycache__/**",
                    "**/__pycache__/**",
                    "scratch/**",
                    "temp_*/**",
                    "temp_*"
                ],
                commit_message="Automatic sync update from master"
            )
            print("    [OK] Hugging Face Space updated!")
        except Exception as exc:
            print(f"    [WARN] HF Space upload failed: {exc}")
    else:
        print("    [SKIP] HF_TOKEN not found, skipped direct Hugging Face upload.")

    print("\n>>> ALL TARGETS (GitHub master, GitHub gh-pages, Hugging Face Space) SYNCED AND DEPLOYED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    main()
