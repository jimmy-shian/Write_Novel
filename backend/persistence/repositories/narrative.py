# -*- coding: utf-8 -*-
"""
Story Engine 2.0 Narrative Reasoning Persistence Layer
管理 setting_systems (設定系統運行態)、conflict_signatures (長程因果簽名)、
narrative_audits (總監診斷記錄) 與 narrative_profile (作品敘事畫像)。
"""

import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.persistence.connection import _to_traditional, get_db_connection


# =============================================================================
# 1. Setting Systems (世界觀運作系統)
# =============================================================================

def upsert_setting_system(
    novel_id: str,
    name: Optional[str] = None,
    setting_type: Optional[str] = None,
    mechanism: Optional[str] = None,
    cost: Optional[str] = None,
    boundary: Optional[str] = None,
    failure_condition: Optional[str] = None,
    stakeholder: Optional[str] = None,
    social_effect: Optional[str] = None,
    theme_link: Optional[str] = None,
    current_state: str = "active",
    **kwargs,
) -> Dict[str, Any]:
    """新增或更新世界觀設定系統實體"""
    name = (name or kwargs.get("system_name") or "未命名設定").strip()
    setting_type = (setting_type or kwargs.get("system_type") or "generic").strip()
    mechanism = (mechanism or kwargs.get("rules") or "運作機制").strip()
    cost = cost or kwargs.get("costs")
    boundary = boundary or kwargs.get("boundaries")
    failure_condition = failure_condition or kwargs.get("failure_conditions") or kwargs.get("vulnerabilities")

    conn = get_db_connection()
    cursor = conn.cursor()
    name_trad = _to_traditional(name)
    existing = cursor.execute(
        "SELECT id, usage_count, last_used_chapter FROM setting_systems WHERE novel_id = ? AND name = ?",
        (novel_id, name_trad),
    ).fetchone()

    now = datetime.utcnow().isoformat()
    if existing:
        sys_id = existing["id"]
        cursor.execute(
            """
            UPDATE setting_systems SET
                type = ?, mechanism = ?, cost = ?, boundary = ?, failure_condition = ?,
                stakeholder = ?, social_effect = ?, theme_link = ?, current_state = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                setting_type, mechanism, cost, boundary, failure_condition,
                stakeholder, social_effect, theme_link, current_state, now, sys_id
            ),
        )
    else:
        sys_id = f"sys_{uuid.uuid4().hex[:12]}"
        cursor.execute(
            """
            INSERT INTO setting_systems (
                id, novel_id, name, type, mechanism, cost, boundary, failure_condition,
                stakeholder, social_effect, theme_link, current_state, usage_count, last_used_chapter, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                sys_id, novel_id, name_trad, setting_type, mechanism, cost, boundary,
                failure_condition, stakeholder, social_effect, theme_link, current_state, now, now
            ),
        )
    conn.commit()
    row = cursor.execute("SELECT * FROM setting_systems WHERE id = ?", (sys_id,)).fetchone()
    return dict(row) if row else {}


def get_setting_systems(novel_id: str, active_only: bool = False) -> List[Dict[str, Any]]:
    """取得該作品所有已登錄之設定系統"""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM setting_systems WHERE novel_id = ?"
    params = [novel_id]
    if active_only:
        query += " AND current_state = 'active'"
    query += " ORDER BY usage_count DESC, created_at ASC"
    rows = cursor.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_setting_system_by_name(novel_id: str, name: str) -> Optional[Dict[str, Any]]:
    """依名稱取得特定世界觀設定系統實體"""
    conn = get_db_connection()
    cursor = conn.cursor()
    name_trad = _to_traditional(name.strip())
    row = cursor.execute(
        "SELECT * FROM setting_systems WHERE novel_id = ? AND name = ?",
        (novel_id, name_trad),
    ).fetchone()
    return dict(row) if row else None



def record_setting_usage(
    novel_id: str,
    name: str,
    chapter_index: int,
    new_state: Optional[str] = None,
) -> bool:
    """記錄設定系統在某章被使用或狀態改變"""
    conn = get_db_connection()
    cursor = conn.cursor()
    name_trad = _to_traditional(name.strip())
    row = cursor.execute(
        "SELECT id, usage_count FROM setting_systems WHERE novel_id = ? AND name = ?",
        (novel_id, name_trad),
    ).fetchone()
    if not row:
        return False

    updates = ["usage_count = usage_count + 1", "last_used_chapter = ?", "updated_at = ?"]
    params: List[Any] = [chapter_index, datetime.utcnow().isoformat()]
    if new_state:
        updates.append("current_state = ?")
        params.append(new_state)
    params.append(row["id"])

    cursor.execute(f"UPDATE setting_systems SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    return True


update_setting_system_usage = record_setting_usage



# =============================================================================
# 2. Conflict Signatures (長程因果簽名帳本)
# =============================================================================

def compute_signature_hash(pressure_type: str, protagonist_strategy: str, outcome: str) -> str:
    """計算因果模式特徵雜湊值，用於快速比對結構相似度"""
    canonical = f"{pressure_type.strip().lower()}|{protagonist_strategy.strip().lower()}|{outcome.strip().lower()}"
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:16]


def add_conflict_signature(
    novel_id_or_data: Any = None,
    chapter_start: Optional[int] = None,
    chapter_end: Optional[int] = None,
    pressure_type: Optional[str] = None,
    protagonist_strategy: Optional[str] = None,
    outcome: Optional[str] = None,
    initiator: Optional[str] = None,
    antagonist_goal: Optional[str] = None,
    power_used: Optional[str] = None,
    twist_mechanism: Optional[str] = None,
    cost: Optional[str] = None,
    emotional_effect: Optional[str] = None,
    setting_used: Optional[str] = None,
    novel_id: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """新增一筆長程衝突因果特徵記錄 (支援 dict 傳入或個別參數傳入)"""
    if novel_id_or_data is None and novel_id is not None:
        novel_id_or_data = novel_id

    if isinstance(novel_id_or_data, dict):
        d = dict(novel_id_or_data)
        novel_id = str(d.get("novel_id", ""))
        ch_s = int(d.get("chapter_start", d.get("chapter_index", 1)))
        ch_e = int(d.get("chapter_end", d.get("chapter_index", ch_s)))
        p_type = str(d.get("pressure_type", d.get("underlying_cause", "oppression")))
        strat = str(d.get("protagonist_strategy", "play_dumb_or_weak"))
        out = str(d.get("outcome", d.get("resolution_archetype", "shock")))
        initiator = d.get("initiator")
        antagonist_goal = d.get("antagonist_goal", d.get("escalation_mechanism"))
        power_used = d.get("power_used", d.get("turning_tactic"))
        twist_mechanism = d.get("twist_mechanism", d.get("turning_tactic"))
        cost = d.get("cost")
        emotional_effect = d.get("emotional_effect")
        setting_used = d.get("setting_used")
    else:
        novel_id = str(novel_id_or_data)
        ch_s = int(chapter_start if chapter_start is not None else 1)
        ch_e = int(chapter_end if chapter_end is not None else ch_s)
        p_type = str(pressure_type or kwargs.get("underlying_cause") or "oppression")
        strat = str(protagonist_strategy or "play_dumb_or_weak")
        out = str(outcome or kwargs.get("resolution_archetype") or "shock")
        initiator = initiator or kwargs.get("initiator")
        antagonist_goal = antagonist_goal or kwargs.get("antagonist_goal") or kwargs.get("escalation_mechanism")
        power_used = power_used or kwargs.get("power_used") or kwargs.get("turning_tactic")
        twist_mechanism = twist_mechanism or kwargs.get("twist_mechanism") or kwargs.get("turning_tactic")
        cost = cost or kwargs.get("cost")
        emotional_effect = emotional_effect or kwargs.get("emotional_effect")
        setting_used = setting_used or kwargs.get("setting_used")

    conn = get_db_connection()
    cursor = conn.cursor()
    sig_id = f"csig_{uuid.uuid4().hex[:12]}"
    sig_hash = compute_signature_hash(p_type, strat, out)

    cursor.execute(
        """
        INSERT INTO conflict_signatures (
            id, novel_id, chapter_start, chapter_end, initiator, antagonist_goal,
            pressure_type, protagonist_strategy, power_used, twist_mechanism, outcome,
            cost, emotional_effect, setting_used, signature_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sig_id, novel_id, ch_s, ch_e, initiator, antagonist_goal,
            p_type, strat, power_used, twist_mechanism, out,
            cost, emotional_effect, setting_used, sig_hash
        ),
    )
    conn.commit()
    row = cursor.execute("SELECT * FROM conflict_signatures WHERE id = ?", (sig_id,)).fetchone()
    return dict(row) if row else {}


def get_conflict_signatures(novel_id: str, limit: int = 40) -> List[Dict[str, Any]]:
    """取得全書或近期衝突因果特徵記錄"""
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT * FROM conflict_signatures WHERE novel_id = ? ORDER BY chapter_start DESC LIMIT ?",
        (novel_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# 3. Narrative Audits (Director 2.0 診斷紀錄)
# =============================================================================

def add_narrative_audit(
    novel_id: str,
    chapter_index: int,
    dimension: str,
    severity: str,
    evidence: str,
    recommendation: str,
    action_required: bool = False,
) -> Dict[str, Any]:
    """新增一條總監敘事診斷紀錄"""
    conn = get_db_connection()
    cursor = conn.cursor()
    audit_id = f"naud_{uuid.uuid4().hex[:12]}"
    cursor.execute(
        """
        INSERT INTO narrative_audits (
            id, novel_id, chapter_index, dimension, severity, evidence,
            recommendation, action_required, resolved
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (audit_id, novel_id, chapter_index, dimension, severity.lower(), evidence, recommendation, 1 if action_required else 0),
    )
    conn.commit()
    row = cursor.execute("SELECT * FROM narrative_audits WHERE id = ?", (audit_id,)).fetchone()
    return dict(row) if row else {}


def get_narrative_audits(
    novel_id: str,
    chapter_index: Optional[int] = None,
    unresolved_only: bool = False,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """查詢小說的敘事診斷歷史"""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM narrative_audits WHERE novel_id = ?"
    params: List[Any] = [novel_id]
    if chapter_index is not None:
        query += " AND chapter_index = ?"
        params.append(chapter_index)
    if unresolved_only:
        query += " AND resolved = 0"
    query += " ORDER BY chapter_index DESC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = cursor.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def resolve_narrative_audit(audit_id: str) -> bool:
    """標記某診斷已被修復或處置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE narrative_audits SET resolved = 1 WHERE id = ?", (audit_id,))
    conn.commit()
    return cursor.rowcount > 0


def delete_narrative_audit(audit_id: str) -> bool:
    """刪除單筆敘事診斷（用於清除誤報，如 self-match 假陽性）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM narrative_audits WHERE id = ?", (audit_id,))
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# 5. Cascade helpers（正文清除連動：單章 / 區間刪章 / 章序平移）
# =============================================================================

def delete_chapter_signatures(novel_id: str, chapter_index: int) -> Dict[str, int]:
    """刪除覆蓋該章的衝突簽名（簽名可橫跨起止章，取重疊即刪）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM conflict_signatures WHERE novel_id = ? AND chapter_start <= ? AND chapter_end >= ?",
        (novel_id, int(chapter_index), int(chapter_index)),
    )
    n = cursor.rowcount
    conn.commit()
    return {"signatures_deleted": n}


def delete_chapter_audits(novel_id: str, chapter_index: int) -> Dict[str, int]:
    """刪除該章的敘事審計記錄。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM narrative_audits WHERE novel_id = ? AND chapter_index = ?",
        (novel_id, int(chapter_index)),
    )
    n = cursor.rowcount
    conn.commit()
    return {"audits_deleted": n}


def delete_narrative_range(novel_id: str, start_del: int, end_del: int) -> Dict[str, int]:
    """刪除章節區間內的簽名與審計（區間刪章時使用）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """DELETE FROM conflict_signatures
           WHERE novel_id = ? AND chapter_start <= ? AND chapter_end >= ?""",
        (novel_id, int(end_del), int(start_del)),
    )
    sigs = cursor.rowcount
    cursor.execute(
        "DELETE FROM narrative_audits WHERE novel_id = ? AND chapter_index >= ? AND chapter_index <= ?",
        (novel_id, int(start_del), int(end_del)),
    )
    audits = cursor.rowcount
    conn.commit()
    return {"signatures_deleted": sigs, "audits_deleted": audits}


def shift_narrative_chapters(novel_id: str, after_chapter: int, delta: int) -> Dict[str, int]:
    """刪章後將後續簽名/審計/設定用量的章序標記平移，保持索引對齊。"""
    after_chapter = int(after_chapter)
    delta = int(delta)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE conflict_signatures SET chapter_start = chapter_start + ?, chapter_end = chapter_end + ?
           WHERE novel_id = ? AND chapter_start > ?""",
        (delta, delta, novel_id, after_chapter),
    )
    sigs = cursor.rowcount
    cursor.execute(
        "UPDATE narrative_audits SET chapter_index = chapter_index + ? WHERE novel_id = ? AND chapter_index > ?",
        (delta, novel_id, after_chapter),
    )
    audits = cursor.rowcount
    # 設定用量：落在被刪區間的 last_used 歸零（delta<0 時被刪區間為 [after+delta+1, after]），
    # 後續章節的 last_used 隨章序平移；usage_count 為累計值予以保留。
    if delta < 0:
        cursor.execute(
            "UPDATE setting_systems SET last_used_chapter = 0 WHERE novel_id = ? AND last_used_chapter >= ? AND last_used_chapter <= ?",
            (novel_id, after_chapter + delta + 1, after_chapter),
        )
    cursor.execute(
        "UPDATE setting_systems SET last_used_chapter = last_used_chapter + ? WHERE novel_id = ? AND last_used_chapter > ?",
        (delta, novel_id, after_chapter),
    )
    systems = cursor.rowcount
    conn.commit()
    return {"signatures_shifted": sigs, "audits_shifted": audits, "systems_shifted": systems}


# =============================================================================
# 4. Narrative Profile (作品專屬敘事畫像)
# =============================================================================

DEFAULT_NARRATIVE_PROFILE = {
    "commercial_positioning": "商業長篇小說",
    "dominant_appeal": "升級智鬥與爽感反轉",
    "tone": "熱血、微諷、懸疑沉浸",
    "humor_level": "medium",
    "power_fantasy_level": "medium_high",
    "emotional_intensity": "medium",
    "pacing_preference": "緊湊推進、有張有弛",
    "narrative_complexity": "multi_faction",
}


def get_narrative_profile(novel_id: str) -> Dict[str, Any]:
    """取得小說專屬的 Narrative Profile"""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT narrative_profile, genre, style FROM novels WHERE id = ?", (novel_id,)).fetchone()
    if not row:
        return dict(DEFAULT_NARRATIVE_PROFILE)
    
    raw = row["narrative_profile"]
    if raw and isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                merged = dict(DEFAULT_NARRATIVE_PROFILE)
                merged.update(parsed)
                return merged
        except Exception:
            pass
            
    # Fallback to genre-inferred profile
    profile = dict(DEFAULT_NARRATIVE_PROFILE)
    genre = str(row["genre"] or "").lower()
    if "無敵" in genre or "爽文" in genre:
        profile["power_fantasy_level"] = "high"
        profile["dominant_appeal"] = "絕對掌控與爽感碾壓"
    elif "懸疑" in genre or "推理" in genre:
        profile["pacing_preference"] = "重伏筆、細推演"
        profile["dominant_appeal"] = "智力博弈與意料之外的真相"
        profile["narrative_complexity"] = "high"
    return profile


def update_narrative_profile(novel_id: str, profile_dict: Dict[str, Any]) -> bool:
    """更新小說專屬的 Narrative Profile"""
    conn = get_db_connection()
    cursor = conn.cursor()
    json_str = json.dumps(profile_dict, ensure_ascii=False)
    cursor.execute("UPDATE novels SET narrative_profile = ? WHERE id = ?", (json_str, novel_id))
    conn.commit()
    return cursor.rowcount > 0
