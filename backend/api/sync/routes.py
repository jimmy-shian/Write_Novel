# -*- coding: utf-8 -*-
from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.services.hf_sync import (
    get_sync_status,
    backup_database,
    restore_database,
    async_backup,
    is_hf_sync_available,
)

router = APIRouter(prefix="/sync", tags=["Cloud Sync"])


@router.get("/status")
def api_get_sync_status():
    """取得當前 Hugging Face Dataset 雲端資料庫同步狀態。"""
    return get_sync_status()


@router.post("/backup")
def api_trigger_backup(background_tasks: BackgroundTasks, force: bool = False):
    """手動觸發立即備份至 Hugging Face 私有 Dataset。"""
    if not is_hf_sync_available():
        raise HTTPException(
            status_code=400,
            detail="Hugging Face 同步功能未就緒（請確認環境變數 HF_TOKEN 與 HF_DATASET_REPO 是否已設定）",
        )
    background_tasks.add_task(backup_database, reason="manual_request", force=force)
    return {"status": "triggered", "message": "雲端備份已於背景開始執行"}


@router.post("/restore")
def api_trigger_restore(force: bool = False):
    """手動觸發從 Hugging Face 私有 Dataset 還原資料庫。"""
    if not is_hf_sync_available():
        raise HTTPException(
            status_code=400,
            detail="Hugging Face 同步功能未就緒（請確認環境變數 HF_TOKEN 與 HF_DATASET_REPO 是否已設定）",
        )
    success = restore_database(force=force)
    if success:
        return {"status": "success", "message": "資料庫已成功從雲端還原"}
    else:
        status_info = get_sync_status()
        raise HTTPException(
            status_code=500,
            detail=f"資料庫還原失敗: {status_info.get('last_error', '未知錯誤')}",
        )
