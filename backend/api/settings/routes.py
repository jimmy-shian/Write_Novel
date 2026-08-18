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