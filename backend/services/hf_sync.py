# -*- coding: utf-8 -*-
"""
Hugging Face 雲端資料庫持久化同步服務
支援 Hugging Face Storage Buckets（物件儲存，零 Git Commit 歷史、原地覆蓋）
與 Hugging Face 私有 Dataset 備援機制。
"""

import os
import time
import shutil
import sqlite3
import threading
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from huggingface_hub import HfApi, hf_hub_download, HfFileSystem
    HAS_HF_HUB = True
except ImportError:
    HAS_HF_HUB = False

# 專案路徑與環境變數設定
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.getenv("DB_PATH", os.path.join(PROJECT_ROOT, "data", "novel_factory.db"))
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN", "")
HF_STORAGE_BUCKET = os.getenv("HF_STORAGE_BUCKET", "botsz/writenovel-storage-bucket")
HF_DATASET_REPO = os.getenv("HF_DATASET_REPO", "botsz/writenovel-storage")

_sync_lock = threading.Lock()
_last_backup_time: Optional[float] = None
_last_backup_status: str = "never"
_last_restore_time: Optional[float] = None
_last_restore_status: str = "never"
_last_error_message: str = ""
_MIN_BACKUP_INTERVAL = float(os.getenv("HF_BACKUP_MIN_INTERVAL", "1800.0"))  # 兩次自動備份之間最小間隔秒數 (預設 30 分鐘)


def is_hf_sync_available() -> bool:
    """檢查環境是否具備 HF 雲端同步條件。"""
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or HF_TOKEN
    return HAS_HF_HUB and bool(token) and (bool(HF_STORAGE_BUCKET) or bool(HF_DATASET_REPO))


def get_sync_status() -> Dict[str, Any]:
    """取得當前雲端同步狀態。"""
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or HF_TOKEN
    return {
        "available": is_hf_sync_available(),
        "has_token": bool(token),
        "storage_bucket": HF_STORAGE_BUCKET,
        "dataset_repo": HF_DATASET_REPO,
        "db_path": DB_PATH,
        "db_exists": os.path.exists(DB_PATH),
        "db_size_mb": round(os.path.getsize(DB_PATH) / (1024 * 1024), 2) if os.path.exists(DB_PATH) else 0,
        "last_backup_time": datetime.fromtimestamp(_last_backup_time).strftime("%Y-%m-%d %H:%M:%S") if _last_backup_time else None,
        "last_backup_status": _last_backup_status,
        "last_restore_time": datetime.fromtimestamp(_last_restore_time).strftime("%Y-%m-%d %H:%M:%S") if _last_restore_time else None,
        "last_restore_status": _last_restore_status,
        "last_error": _last_error_message,
    }


def restore_database(force: bool = False) -> bool:
    """
    從 Hugging Face Storage Bucket（優先）或私有 Dataset 下載並還原 SQLite 資料庫。
    適用於 Space 重新啟動或冷啟動時自動拉取最新歷史資料。
    """
    global _last_restore_time, _last_restore_status, _last_error_message

    if not is_hf_sync_available():
        _last_restore_status = "skipped_no_config"
        print("[HF-SYNC] Cloud restore skipped: HF_TOKEN or target storage not configured.")
        return False

    # 若本地已有 DB 且非強制還原，則略過
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0 and not force:
        _last_restore_status = "skipped_local_exists"
        print("[HF-SYNC] Local database already exists. Skipping cloud restore.")
        return True

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or HF_TOKEN

    with _sync_lock:
        # 1. 優先嘗試從 Storage Bucket 還原 (無 Git 歷史，速度快)
        if HF_STORAGE_BUCKET:
            try:
                print(f"[HF-SYNC] Restoring database from Storage Bucket '{HF_STORAGE_BUCKET}'...")
                fs = HfFileSystem(token=token)
                bucket_file_uri = f"hf://buckets/{HF_STORAGE_BUCKET}/novel_factory.db"
                
                os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                fs.get_file(bucket_file_uri, DB_PATH)

                _last_restore_time = time.time()
                _last_restore_status = "success_bucket"
                _last_error_message = ""
                db_mb = round(os.path.getsize(DB_PATH)/(1024*1024), 2)
                print(f"[HF-SYNC] Database restored successfully from Bucket ({db_mb} MB).")
                return True
            except Exception as bucket_err:
                print(f"[HF-SYNC] Bucket restore failed/unavailable: {bucket_err}, falling back to Dataset...")

        # 2. 備援：從 Dataset 下載
        if HF_DATASET_REPO:
            try:
                print(f"[HF-SYNC] Restoring database from Dataset '{HF_DATASET_REPO}'...")
                downloaded_file = hf_hub_download(
                    repo_id=HF_DATASET_REPO,
                    filename="novel_factory.db",
                    repo_type="dataset",
                    token=token,
                    force_download=True,
                )

                os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                shutil.copy2(downloaded_file, DB_PATH)

                _last_restore_time = time.time()
                _last_restore_status = "success_dataset"
                _last_error_message = ""
                db_mb = round(os.path.getsize(DB_PATH)/(1024*1024), 2)
                print(f"[HF-SYNC] Database restored successfully from Dataset ({db_mb} MB).")
                return True
            except Exception as ds_err:
                _last_restore_status = "failed"
                _last_error_message = str(ds_err)
                print(f"[HF-SYNC] Cloud restore failed from all sources: {ds_err}")
                return False

        return False


def backup_database(reason: str = "auto", force: bool = False) -> bool:
    """
    將本地 SQLite 資料庫安全備份並上傳至 Hugging Face。
    優先使用 Storage Bucket 進行原地物件覆蓋（零 Git Commit、不累積歷史容量）；
    若 Bucket 不可用則回退至 Dataset 備援。
    """
    global _last_backup_time, _last_backup_status, _last_error_message

    if not is_hf_sync_available():
        _last_backup_status = "skipped_no_config"
        return False

    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        _last_backup_status = "skipped_db_empty"
        return False

    now = time.time()
    if not force and _last_backup_time and (now - _last_backup_time) < _MIN_BACKUP_INTERVAL:
        _last_backup_status = "throttled"
        return False

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or HF_TOKEN

    with _sync_lock:
        temp_dir = tempfile.mkdtemp(prefix="hf_db_backup_")
        temp_db_path = os.path.join(temp_dir, "novel_factory.db")

        try:
            # 優先使用 VACUUM INTO 生成原子且壓縮過的小型 SQLite 快照
            try:
                conn = sqlite3.connect(DB_PATH, timeout=10.0)
                conn.execute(f"VACUUM INTO '{temp_db_path}'")
                conn.close()
            except Exception as vac_err:
                print(f"[HF-SYNC] VACUUM INTO fallback to direct copy: {vac_err}")
                shutil.copy2(DB_PATH, temp_db_path)

            file_size_mb = round(os.path.getsize(temp_db_path) / (1024 * 1024), 2)
            commit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. 優先使用 Storage Bucket 上傳 (原地物件覆蓋，零 Git 歷史，不佔額外容量)
            if HF_STORAGE_BUCKET:
                try:
                    print(f"[HF-SYNC] Uploading snapshot ({file_size_mb} MB) to Bucket '{HF_STORAGE_BUCKET}'...")
                    fs = HfFileSystem(token=token)
                    bucket_dest = f"hf://buckets/{HF_STORAGE_BUCKET}/novel_factory.db"
                    fs.put_file(temp_db_path, bucket_dest)

                    _last_backup_time = time.time()
                    _last_backup_status = "success_bucket"
                    _last_error_message = ""
                    print(f"[HF-SYNC] Bucket backup completed successfully at {commit_time} ({reason}).")
                    return True
                except Exception as bucket_err:
                    print(f"[HF-SYNC] Bucket upload failed: {bucket_err}, falling back to Dataset...")

            # 2. 備援：上傳至 Dataset 倉庫
            if HF_DATASET_REPO:
                try:
                    print(f"[HF-SYNC] Uploading snapshot ({file_size_mb} MB) to Dataset '{HF_DATASET_REPO}'...")
                    api = HfApi(token=token)
                    commit_msg = f"Auto-backup novel_factory.db ({reason}) [{commit_time}]"
                    api.upload_file(
                        path_or_fileobj=temp_db_path,
                        path_in_repo="novel_factory.db",
                        repo_id=HF_DATASET_REPO,
                        repo_type="dataset",
                        commit_message=commit_msg,
                    )

                    _last_backup_time = time.time()
                    _last_backup_status = "success_dataset"
                    _last_error_message = ""
                    print(f"[HF-SYNC] Dataset backup completed successfully at {commit_time}.")
                    return True
                except Exception as ds_err:
                    _last_backup_status = "failed"
                    _last_error_message = str(ds_err)
                    print(f"[HF-SYNC] Backup failed: {ds_err}")
                    return False

            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def async_backup(reason: str = "auto", force: bool = False):
    """在背景執行緒中異步執行備份，不阻塞主 API 響應。"""
    t = threading.Thread(target=backup_database, args=(reason, force), daemon=True)
    t.start()
