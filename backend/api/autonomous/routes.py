# -*- coding: utf-8 -*-
"""Autonomous Pipeline API routes."""

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Optional

from backend.services.autonomous_pipeline import autonomous_manager

router = APIRouter()


class AutoRunRequest(BaseModel):
    novel_id: str
    prompt: Optional[str] = ""
    max_chapters: Optional[int] = 5


@router.post("/pipeline/auto-run")
def api_start_auto_pipeline(req: AutoRunRequest):
    res = autonomous_manager.start_pipeline(
        novel_id=req.novel_id,
        prompt=req.prompt or "",
        max_chapters=req.max_chapters or 5
    )
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.get("/pipeline/auto-status")
def api_get_auto_pipeline_status():
    return autonomous_manager.get_status()


@router.post("/pipeline/auto-stop")
def api_stop_auto_pipeline():
    return autonomous_manager.stop_pipeline()
