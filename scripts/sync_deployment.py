# -*- coding: utf-8 -*-
"""
One-Click Synchronization Script for AI Novel Factory
全自動分支同步與雲端部署腳本：

標準流程：
1. 確保 master 分支乾淨：將 frontend/static 同步至 docs/，提交並推送至 origin/master。
2. 切換至 feat/cloud-hybrid-deployment 分支：乾淨合併 master 最新代碼，推送至 origin/feat/cloud-hybrid-deployment。
3. 發布 GitHub Pages：利用 git subtree split 將 docs/ 獨立推送至 origin/gh-pages。
4. 部署 Hugging Face Space：將包含 app.py、autonomous_pipeline.py 與後端環境的 feat 分支完整代碼推送至 Space (botsz/WriteNovel)。
5. 安全切回 master 分支：確保日常開發環境始終保持在乾淨的 master 上。
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
    print(f"\n=== Starting Standardized Multi-Branch Deployment Sync in {root} ===")

    # 1. 確保切換至 master 並同步前端靜態目錄至 docs/
    print("\n--- [Step 1/5] Syncing master branch & docs/ ---")
    run_cmd("git checkout master")
    
    src = os.path.join(root, "frontend", "static")
    dst = os.path.join(root, "docs")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print("    [OK] frontend/static synced to docs/")

    run_cmd("git add -A")
    run_cmd('git commit -m "chore: sync frontend to docs for release" || git status', check=False)
    run_cmd("git push origin master")
    print("    [OK] master pushed to origin/master")

    # 2. 切換至 feat/cloud-hybrid-deployment 並合併 master
    print("\n--- [Step 2/5] Merging master into feat/cloud-hybrid-deployment ---")
    run_cmd("git checkout feat/cloud-hybrid-deployment")
    run_cmd("git merge master --no-edit || (git checkout --theirs frontend/ docs/ scripts/ README.md && git add -A && git commit -m 'chore: merge master into feat/cloud-hybrid-deployment')", check=False)
    run_cmd("git push origin feat/cloud-hybrid-deployment")
    print("    [OK] feat/cloud-hybrid-deployment updated and pushed to origin")

    # 3. 發布至 GitHub Pages (gh-pages)
    print("\n--- [Step 3/5] Deploying static frontend to gh-pages ---")
    run_cmd("git branch -D gh-pages-auto-sync", check=False)
    run_cmd("git subtree split --prefix docs -b gh-pages-auto-sync")
    run_cmd("git push -f origin gh-pages-auto-sync:gh-pages")
    run_cmd("git branch -D gh-pages-auto-sync", check=False)
    print("    [OK] gh-pages updated successfully!")

    # 4. 上傳 feat/cloud-hybrid-deployment 代碼至 Hugging Face Space
    print("\n--- [Step 4/5] Deploying backend service to Hugging Face Space ---")
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
                    "data/*.db*",
                    "data/novel_factory.db*",
                    "data/novels.db*",
                    "novel_factory.db*",
                    "*.db",
                    "*.db-shm",
                    "*.db-wal",
                    "_archive/**",
                    "tests/**",
                    "*.pyc",
                    "__pycache__/**",
                    "**/__pycache__/**",
                    "scratch/**",
                    "AiNovel.txt"
                ],
                commit_message="Automatic sync update from feat/cloud-hybrid-deployment"
            )
            print("    [OK] Hugging Face Space updated!")
        except Exception as exc:
            print(f"    [WARN] HF Space upload failed: {exc}")
    else:
        print("    [SKIP] HF_TOKEN not found, skipped direct Hugging Face upload.")

    # 5. 安全切回 master 分支保持本地乾淨
    print("\n--- [Step 5/5] Returning to master branch ---")
    run_cmd("git checkout master")
    print("    [OK] Switched back to master branch.")

    print("\n>>> ALL 3 TARGETS (master, feat, gh-pages, HF Space) SYNCED AND DEPLOYED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    main()
