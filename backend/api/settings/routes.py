"""Settings endpoints."""

from fastapi import APIRouter, HTTPException, Body
from typing import Any, Mapping

router = APIRouter()

@router.get("/settings")
def api_get_settings():
    from backend.services.settings.service import build_settings_snapshot
    return build_settings_snapshot()

@router.post("/settings")
def api_save_settings(payload: Mapping[str, Any] = Body(...)):
    from backend.services.settings.service import apply_settings_payload
    try:
        return apply_settings_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/settings/fetch-models")
def api_fetch_models(payload: Mapping[str, Any] = Body(...)):
    from backend.services.settings.service import fetch_available_models
    base_url = payload.get("base_url", "")
    api_key = payload.get("api_key", "")
    try:
        return fetch_available_models(base_url, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/settings/test-llm")
def api_test_llm(payload: Mapping[str, Any] = Body(...)):
    from backend.services.settings.service import test_llm_connection
    base_url = payload.get("base_url", "")
    api_key = payload.get("api_key", "")
    model = payload.get("model", "")
    try:
        return test_llm_connection(base_url, api_key, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/settings/preferences")
def api_get_preferences():
    """取得 UI 與使用者偏好設定 (theme, editor_font_size 等)"""
    from backend.persistence import get_all_app_preferences
    return {"status": "success", "preferences": get_all_app_preferences()}


@router.post("/settings/preferences")
def api_save_preferences(payload: Mapping[str, Any] = Body(...)):
    """儲存 UI 與使用者偏好設定至 SQLite 資料庫"""
    from backend.persistence import set_app_preferences
    prefs = payload.get("preferences", payload)
    if not isinstance(prefs, Mapping):
        raise HTTPException(status_code=422, detail="preferences must be an object")
    updated = set_app_preferences(dict(prefs))
    return {"status": "success", "preferences": updated}

