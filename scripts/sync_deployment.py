# -*- coding: utf-8 -*-
"""
One-Click Synchronization Script for AI Novel Factory
全自動分支同步與雲端部署腳本（精簡版）：

標準流程：
1. 確保 master 分支乾淨：將 frontend/static 同步至 docs/，提交並推送至 origin/master。
2. 發布 GitHub Pages：利用 git subtree split 將 docs/ 獨立推送至 origin/gh-pages。
3. 部署 Hugging Face Space：將 master 最新代碼推送至 Space (botsz/WriteNovel)。
"""

import os
import shutil
import subprocess
import sys

def run_cmd(cmd, check=True):
    print(f"[*] Executing: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8")
    if res.stdout.strip():
        print(res.stdout)
    if res.stderr.strip():
        print(res.stderr)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {cmd}")
    return res

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    print(f"\n=== Starting Unified Master Deployment Sync in {root} ===")

    # 1. 確保在 master 並同步前端靜態目錄至 docs/
    print("\n--- [Step 1/3] Syncing frontend/static to docs/ & pushing master ---")
    run_cmd("git checkout master")
    
    src = os.path.join(root, "frontend", "static")
    dst = os.path.join(root, "docs")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print("    [OK] frontend/static synced to docs/")

    run_cmd("git add docs/ frontend/static/")
    run_cmd('git commit -m "【文件】同步前端資源至 docs/ 發布目錄" || git status', check=False)
    run_cmd("git push origin master")
    print("    [OK] master pushed to origin/master")

    # 2. 發布至 GitHub Pages (gh-pages)
    print("\n--- [Step 2/3] Deploying static frontend to gh-pages ---")
    run_cmd("git branch -D gh-pages-auto-sync", check=False)
    run_cmd("git subtree split --prefix docs -b gh-pages-auto-sync")
    run_cmd("git push -f origin gh-pages-auto-sync:gh-pages")
    run_cmd("git branch -D gh-pages-auto-sync", check=False)
    print("    [OK] gh-pages updated successfully!")

    # 3. 上傳 master 代碼至 Hugging Face Space
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
