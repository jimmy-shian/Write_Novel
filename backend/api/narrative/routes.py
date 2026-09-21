# -*- coding: utf-8 -*-
"""
Story Engine 2.0 (Narrative Reasoning System) API Routes
提供世界觀運作庫 (Setting Systems)、長程因果特徵帳本 (Conflict Signatures)、
總監 2.0 審計診斷 (Narrative Audits) 與作品敘事畫像 (Narrative Profile) 的 REST API。
"""

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend import persistence as db
from backend.services.narrative import SettingRegistry, ConflictLedger, NarrativeAuditor


router = APIRouter(tags=["narrative"])


# =============================================================================
# Pydantic Request Models
# =============================================================================

class NarrativeProfileUpdate(BaseModel):
    commercial_positioning: Optional[str] = None
    dominant_appeal: Optional[str] = None
    tone: Optional[str] = None
    humor_level: Optional[str] = None
    power_fantasy_level: Optional[str] = None
    emotional_intensity: Optional[str] = None
    pacing_preference: Optional[str] = None
    narrative_complexity: Optional[str] = None
    custom_notes: Optional[str] = None


class SettingSystemUpsert(BaseModel):
    name: str
    type: Optional[str] = "power_mechanism"
    mechanism: str
    cost: Optional[str] = None
    boundary: Optional[str] = None
    failure_condition: Optional[str] = None
    stakeholder: Optional[str] = None
    social_effect: Optional[str] = None
    theme_link: Optional[str] = None
    current_state: Optional[str] = "active"


class ConflictSignatureCreate(BaseModel):
    chapter_start: int = 1
    chapter_end: Optional[int] = None
    initiator: Optional[str] = None
    antagonist_goal: Optional[str] = None
    pressure_type: str
    protagonist_strategy: str
    power_used: Optional[str] = None
    twist_mechanism: Optional[str] = None
    outcome: str
    cost: Optional[str] = None
    emotional_effect: Optional[str] = None
    setting_used: Optional[str] = None


class ConflictRepetitionCheckRequest(BaseModel):
    candidate_signature: Dict[str, Any]
    window: Optional[int] = 60
    threshold: Optional[float] = 0.70


class NarrativeAuditCreate(BaseModel):
    chapter_index: int
    dimension: str
    severity: str = "warning"
    evidence: str
    recommendation: str
    action_required: bool = False


class NarrativeAuditRunRequest(BaseModel):
    chapter_index: int
    prose_text: Optional[str] = None


class NarrativeFixChapterRequest(BaseModel):
    chapter_index: int
    audit_ids: Optional[List[str]] = None


# =============================================================================
# 1. Narrative Profile Endpoints
# =============================================================================

@router.get("/novels/{novel_id}/narrative-profile")
def get_novel_narrative_profile(novel_id: str):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    profile = db.get_narrative_profile(novel_id)
    return {"novel_id": novel_id, "profile": profile}


@router.put("/novels/{novel_id}/narrative-profile")
def update_novel_narrative_profile(novel_id: str, payload: NarrativeProfileUpdate):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    existing = db.get_narrative_profile(novel_id)
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    existing.update(update_data)

    success = db.update_narrative_profile(novel_id, existing)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update narrative profile")

    return {"status": "success", "profile": existing}


# =============================================================================
# 2. Setting Systems & Registry Endpoints
# =============================================================================

@router.get("/novels/{novel_id}/setting-systems")
def list_setting_systems(novel_id: str, active_only: bool = Query(False)):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    systems = db.get_setting_systems(novel_id, active_only=active_only)
    return {"novel_id": novel_id, "setting_systems": systems, "total": len(systems)}


@router.post("/novels/{novel_id}/setting-systems")
def upsert_setting_system(novel_id: str, payload: SettingSystemUpsert):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="System name is required")
    if not payload.mechanism.strip():
        raise HTTPException(status_code=422, detail="Mechanism is required")

    result = db.upsert_setting_system(
        novel_id=novel_id,
        name=payload.name,
        setting_type=payload.type,
        mechanism=payload.mechanism,
        cost=payload.cost,
        boundary=payload.boundary,
        failure_condition=payload.failure_condition,
        stakeholder=payload.stakeholder,
        social_effect=payload.social_effect,
        theme_link=payload.theme_link,
        current_state=payload.current_state or "active",
    )
    return {"status": "success", "setting_system": result}


@router.post("/novels/{novel_id}/setting-systems/sync")
def sync_setting_systems_from_worldview(novel_id: str):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    synced_count = SettingRegistry.sync_systems_from_worldview(novel_id)
    systems = db.get_setting_systems(novel_id)
    return {
        "status": "success",
        "synced_count": synced_count,
        "total_systems": len(systems),
        "setting_systems": systems,
    }


@router.get("/novels/{novel_id}/setting-systems/health")
def check_setting_systems_health(novel_id: str, current_chapter: Optional[int] = Query(None)):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    health_report = SettingRegistry.audit_setting_health(novel_id, current_chapter=current_chapter)
    return {"novel_id": novel_id, "health": health_report}


# =============================================================================
# 3. Conflict Signatures & Anti-Repetition Endpoints
# =============================================================================

@router.get("/novels/{novel_id}/conflict-signatures")
def list_conflict_signatures(novel_id: str, limit: int = Query(50, ge=1, le=500)):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    signatures = db.get_conflict_signatures(novel_id, limit=limit)
    return {"novel_id": novel_id, "signatures": signatures, "total": len(signatures)}


@router.post("/novels/{novel_id}/conflict-signatures")
def add_conflict_signature(novel_id: str, payload: ConflictSignatureCreate):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    if not payload.pressure_type.strip():
        raise HTTPException(status_code=422, detail="pressure_type is required")
    if not payload.protagonist_strategy.strip():
        raise HTTPException(status_code=422, detail="protagonist_strategy is required")

    result = ConflictLedger.record_signature(
        novel_id=novel_id,
        chapter_start=payload.chapter_start,
        chapter_end=payload.chapter_end or payload.chapter_start,
        initiator=payload.initiator,
        antagonist_goal=payload.antagonist_goal,
        pressure_type=payload.pressure_type,
        protagonist_strategy=payload.protagonist_strategy,
        power_used=payload.power_used,
        twist_mechanism=payload.twist_mechanism,
        outcome=payload.outcome,
        cost=payload.cost,
        emotional_effect=payload.emotional_effect,
        setting_used=payload.setting_used,
    )
    return {"status": "success", "signature": result}


@router.post("/novels/{novel_id}/conflict-signatures/check-repetition")
def check_conflict_repetition(novel_id: str, payload: ConflictRepetitionCheckRequest):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    diagnosis = ConflictLedger.check_long_range_repetition(
        novel_id=novel_id,
        candidate_sig=payload.candidate_signature,
        window=payload.window or 60,
        threshold=payload.threshold or 0.70,
    )
    return {"novel_id": novel_id, "diagnosis": diagnosis}


# =============================================================================
# 4. Narrative Audits & Director 2.0 Diagnostics
# =============================================================================

@router.get("/novels/{novel_id}/narrative-audits")
def list_narrative_audits(
    novel_id: str,
    chapter_index: Optional[int] = Query(None),
    unresolved_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    audits = db.get_narrative_audits(
        novel_id=novel_id,
        chapter_index=chapter_index,
        unresolved_only=unresolved_only,
        limit=limit,
    )
    return {"novel_id": novel_id, "audits": audits, "total": len(audits)}


@router.post("/novels/{novel_id}/narrative-audits")
def create_narrative_audit(novel_id: str, payload: NarrativeAuditCreate):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    audit = db.add_narrative_audit(
        novel_id=novel_id,
        chapter_index=payload.chapter_index,
        dimension=payload.dimension,
        severity=payload.severity,
        evidence=payload.evidence,
        recommendation=payload.recommendation,
        action_required=payload.action_required,
    )
    return {"status": "success", "audit": audit}


@router.post("/novels/{novel_id}/narrative-audits/run")
def run_narrative_audit_for_chapter(novel_id: str, payload: NarrativeAuditRunRequest):
    """即時對指定章節的正文執行 NarrativeAuditor 長程診斷並自動持久化問題記錄。"""
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    chapter_idx = payload.chapter_index
    prose_text = payload.prose_text

    # 若未直接傳入正文，嘗試從資料庫讀取最新章節內容
    if not prose_text or not prose_text.strip():
        ch_row = db.get_latest_chapter(novel_id, chapter_idx)
        if ch_row and ch_row.get("content"):
            prose_text = ch_row["content"]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"第 {chapter_idx} 章尚無正文內容，請先撰寫章節或傳入 prose_text"
            )

    # 嘗試尋找該章對應的 conflict_signature 作為因果比對參考
    signatures = db.get_conflict_signatures(novel_id, limit=30)
    matched_sig = None
    for s in signatures:
        if s.get("chapter_start", 0) <= chapter_idx <= s.get("chapter_end", s.get("chapter_start", 0)):
            matched_sig = s
            break

    # 嘗試讀取章節大綱
    outline = None
    try:
        from backend.services import narrative_memory
        outline = narrative_memory.get_chapter_outline(novel_id, chapter_idx)
    except Exception:
        outline = None

    audit_result = NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id,
        chapter_index=chapter_idx,
        prose_text=prose_text,
        current_outline=outline,
        candidate_conflict_sig=matched_sig,
    )

    # 重新獲取本章持久化後的最新 audits
    persisted_audits = db.get_narrative_audits(novel_id, chapter_index=chapter_idx, limit=20)

    return {
        "status": "success",
        "result": audit_result,
        "audits": persisted_audits,
    }


@router.post("/narrative-audits/{audit_id}/resolve")
def resolve_audit(audit_id: str):
    success = db.resolve_narrative_audit(audit_id)
    if not success:
        raise HTTPException(status_code=404, detail="Narrative audit not found or already resolved")
    return {"status": "success", "audit_id": audit_id, "resolved": True}


@router.post("/novels/{novel_id}/narrative-audits/fix-chapter")
def fix_chapter_from_audits_api(novel_id: str, payload: NarrativeFixChapterRequest):
    """閉環修正（單章輔助用）：把該章未處置診斷拼成編輯指示，呼叫 Editor 重寫正文。

    Editor 存下新版後，自動 resolve 本次餵入的診斷，並對新正文重跑一次
    離線審計回報殘留問題。已寫好的舊版保留在 chapters 版本歷史與提案中。
    全自動流水線走同一條服務（services.narrative.fix），判 REVISE 即自動修。
    """
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    from backend.services.narrative.fix import fix_chapter_from_audits as _fix
    try:
        result = _fix(novel_id, payload.chapter_index, audit_ids=payload.audit_ids)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Editor 修正失敗: {exc}")
    return {"status": result["status"], **result}


class NarrativeBackfillRequest(BaseModel):
    max_chapters: Optional[int] = None


@router.post("/novels/{novel_id}/narrative/backfill")
def backfill_novel_narrative_api(novel_id: str, payload: Optional[NarrativeBackfillRequest] = Body(default=None)):
    """為已完結/舊作品回填 Story Engine 2.0 數據（冪等，可重複呼叫）。"""
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    from backend.services.narrative.backfill import backfill_novel_narrative
    max_ch = (payload.max_chapters if payload and payload.max_chapters else None)
    try:
        stats = backfill_novel_narrative(novel_id, max_chapters=max_ch)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backfill failed: {exc}")
    return {"status": "success", **stats}
