# -*- coding: utf-8 -*-
"""
Story Engine 2.0 回填工具（Backfill）
將「已生成完成但敘事推理引擎全空」的舊作品，從既有世界觀 + 卷大綱 +
章節正文反推補登 setting_systems / conflict_signatures / narrative_audits。

冪等設計：已存在的同章簽名不再重插；同章已有 audits 不再重審。
全離線啟發式，不呼叫 LLM。
"""

from typing import Any, Dict, List, Optional

from backend import persistence as db
from backend.services.narrative.conflict_ledger import ConflictLedger
from backend.services.narrative.narrative_auditor import NarrativeAuditor
from backend.services.narrative.setting_registry import SettingRegistry
from backend.services.narrative.story_canon import (
    ensure_timeline_anchors,
    iter_outline_chapters,
    validate_timeline,
)


def _iter_setting_names(su: Any):
    if su is None:
        return
    if isinstance(su, str):
        if su.strip():
            yield su.strip()
        return
    if isinstance(su, dict):
        nm = su.get("system_name") or su.get("name")
        if nm and str(nm).strip():
            yield str(nm).strip()
        return
    if isinstance(su, list):
        for item in su:
            if isinstance(item, dict):
                nm = item.get("system_name") or item.get("name")
                if nm and str(nm).strip():
                    yield str(nm).strip()
            elif isinstance(item, str) and item.strip():
                yield item.strip()


def _collect_outlines(novel_id: str) -> List[Dict[str, Any]]:
    outlines: List[Dict[str, Any]] = []
    try:
        vols = db.get_volumes(novel_id) or []
    except Exception:
        return outlines
    for v in vols:
        ch_list = v.get("chapters_outline") or []
        if isinstance(ch_list, str):
            try:
                import json as _json
                ch_list = _json.loads(ch_list)
            except Exception:
                continue
        if not isinstance(ch_list, list):
            continue
        for c in ch_list:
            if isinstance(c, dict) and c.get("chapter_index"):
                try:
                    c = dict(c)
                    c["chapter_index"] = int(c["chapter_index"])
                    outlines.append(c)
                except Exception:
                    continue
    outlines.sort(key=lambda c: int(c.get("chapter_index") or 0))
    return outlines


def backfill_novel_narrative(
    novel_id: str,
    max_chapters: Optional[int] = None,
) -> Dict[str, Any]:
    """回填單一作品的 Story Engine 2.0 數據，回傳統計 dict。"""
    novel = db.get_novel(novel_id)
    if not novel:
        raise ValueError(f"Novel not found: {novel_id}")

    # 1. 世界觀同步（修過 fallback，文字型世界觀至少產出 1~2 筆）
    try:
        synced_count = SettingRegistry.sync_systems_from_worldview(novel_id)
    except Exception:
        synced_count = 0

    # 1.5 清除 self-match 誤報：審計證據引用本章自己（如「與 第 1-1 章」且
    # audit.chapter_index == 1）者為修復前的假陽性，直接刪除。
    import re as _re
    self_match_removed = 0
    try:
        _all_audits = db.get_narrative_audits(novel_id, limit=500) or []
        for _a in _all_audits:
            if _a.get("dimension") != "conflict_novelty":
                continue
            _ev = str(_a.get("evidence") or "")
            _m = _re.search(r"與\s*第\s*(\d+)(?:\s*-\s*(\d+))?\s*章", _ev)
            if not _m:
                continue
            try:
                _rs, _re_ = int(_m.group(1)), int(_m.group(2) or _m.group(1))
                _ch = int(_a.get("chapter_index") or 0)
            except Exception:
                continue
            if _rs <= _ch <= _re_:
                try:
                    if db.delete_narrative_audit(_a["id"]):
                        self_match_removed += 1
                except Exception:
                    continue
    except Exception:
        pass

    outlines = _collect_outlines(novel_id)
    if max_chapters:
        outlines = outlines[:max_chapters]

    try:
        existing_sigs = db.get_conflict_signatures(novel_id, limit=500)
    except Exception:
        existing_sigs = []
    covered = set()
    for s in existing_sigs:
        try:
            cs, ce = int(s.get("chapter_start") or 0), int(s.get("chapter_end") or s.get("chapter_start") or 0)
            for i in range(cs, ce + 1):
                covered.add(i)
        except Exception:
            continue

    sig_added = 0
    usage_marked = 0
    audits_new = 0
    chapters_seen = 0

    for ol in outlines:
        try:
            ch_idx = int(ol.get("chapter_index") or 0)
        except Exception:
            continue
        if ch_idx <= 0:
            continue
        chapters_seen += 1

        # 正文（沒有也照樣從大綱建簽名，保證帳本不空）
        prose = ""
        try:
            ch_row = db.get_latest_chapter(novel_id, ch_idx)
            if ch_row and ch_row.get("content"):
                prose = ch_row["content"]
        except Exception:
            prose = ""

        hint = ol.get("conflict_signature_hint")
        if not isinstance(hint, dict) or not hint:
            hint = ol
        try:
            sig_dict = ConflictLedger.extract_signature_from_chapter(
                novel_id=novel_id,
                chapter_index=ch_idx,
                outline_hint=hint,
                prose_text=prose,
                outline=ol,
            )
        except Exception:
            continue

        sig_row = None
        if ch_idx not in covered:
            try:
                sig_row = ConflictLedger.record_signature(
                    novel_id=novel_id,
                    chapter_start=sig_dict["chapter_start"],
                    chapter_end=sig_dict["chapter_end"],
                    pressure_type=sig_dict["pressure_type"],
                    protagonist_strategy=sig_dict["protagonist_strategy"],
                    outcome=sig_dict["outcome"],
                    initiator=sig_dict.get("initiator"),
                    antagonist_goal=sig_dict.get("antagonist_goal"),
                    power_used=sig_dict.get("power_used"),
                    twist_mechanism=sig_dict.get("twist_mechanism"),
                    cost=sig_dict.get("cost"),
                    emotional_effect=sig_dict.get("emotional_effect"),
                    setting_used=sig_dict.get("setting_used"),
                )
                sig_added += 1
                covered.add(ch_idx)
            except Exception:
                continue
        else:
            sig_row = next(
                (s for s in existing_sigs if int(s.get("chapter_start") or 0) <= ch_idx <= int(s.get("chapter_end") or s.get("chapter_start") or 0)),
                sig_dict,
            )

        # 設定使用：大綱點名 + 簽名 setting_used 都記
        names = list(_iter_setting_names(ol.get("setting_usage")))
        if sig_row and sig_row.get("setting_used"):
            names.append(str(sig_row["setting_used"]))
        for nm in names:
            try:
                ok = SettingRegistry.record_system_usage(novel_id, nm, ch_idx)
                if not ok:
                    db.upsert_setting_system(
                        novel_id=novel_id,
                        name=nm,
                        setting_type="generic",
                        mechanism=f"第 {ch_idx} 章劇情調用之世界觀設定（回填補登）",
                        cost="動用該設定須承擔相應代價",
                        boundary="受世界法則與環境條件約束",
                    )
                    SettingRegistry.record_system_usage(novel_id, nm, ch_idx)
                usage_marked += 1
            except Exception:
                continue

        # 審計：同章已有記錄就跳過（冪等）；無正文也跳過審計但保留簽名
        if prose and len(prose.strip()) > 50:
            try:
                prior = db.get_narrative_audits(novel_id, chapter_index=ch_idx, limit=1)
            except Exception:
                prior = []
            if not prior:
                try:
                    before = len(db.get_narrative_audits(novel_id, chapter_index=ch_idx, limit=200))
                    NarrativeAuditor.audit_chapter_prose(
                        novel_id=novel_id,
                        chapter_index=ch_idx,
                        prose_text=prose,
                        current_outline=ol,
                        candidate_conflict_sig=sig_row or sig_dict,
                    )
                    after = len(db.get_narrative_audits(novel_id, chapter_index=ch_idx, limit=200))
                    audits_new += max(0, after - before)
                except Exception:
                    continue

    try:
        total_systems = len(db.get_setting_systems(novel_id))
    except Exception:
        total_systems = 0
    try:
        total_sigs = len(db.get_conflict_signatures(novel_id, limit=500))
    except Exception:
        total_sigs = 0
    try:
        total_audits = len(db.get_narrative_audits(novel_id, limit=500))
    except Exception:
        total_audits = 0

    return {
        "novel_id": novel_id,
        "synced_count": synced_count,
        "self_match_removed": self_match_removed,
        "chapters_seen": chapters_seen,
        "signatures_added": sig_added,
        "usages_marked": usage_marked,
        "audits_new": audits_new,
        "total_systems": total_systems,
        "total_signatures": total_sigs,
        "total_audits": total_audits,
    }


def backfill_story_canon(novel_id: str, apply: bool = False) -> Dict[str, Any]:
    """Audit and optionally fill legacy timeline/event canon without rewriting prose."""
    volumes = db.get_volumes(novel_id) or []
    before_issues = validate_timeline(volumes)
    chapters_before = iter_outline_chapters(volumes)
    scheduled = 0
    event_count = 0
    previous_anchor = None
    updated_volumes = []

    for volume in sorted(volumes, key=lambda item: int(item.get("volume_index") or 0)):
        raw = volume.get("chapters_outline") or []
        if isinstance(raw, str):
            try:
                import json
                raw = json.loads(raw)
            except Exception:
                raw = []
        chapters = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if not chapters:
            continue
        normalized = ensure_timeline_anchors(chapters, previous_anchor=previous_anchor)
        volume_scheduled = sum(
            1
            for old, new in zip(
                sorted(chapters, key=lambda c: int(c.get("chapter_index") or 0)),
                normalized,
            )
            if old.get("timeline_anchor") != new.get("timeline_anchor")
        )
        scheduled += volume_scheduled
        previous_anchor = normalized[-1].get("timeline_anchor")
        if apply and volume_scheduled:
            db.update_volume_outline(novel_id, int(volume.get("volume_index") or 0), normalized)
            updated_volumes.append(int(volume.get("volume_index") or 0))
        try:
            from backend.persistence.repositories.story_events import sync_planned_story_events
            if apply:
                event_count += sync_planned_story_events(novel_id, normalized)
            else:
                # Dry-run must be side-effect free.  Count candidate events
                # without creating rows or changing the canon.
                for item in normalized:
                    for key in ("planned_events", "story_events", "life_events", "character_events", "events"):
                        values = item.get(key)
                        if isinstance(values, list):
                            event_count += sum(
                                1 for event in values
                                if isinstance(event, dict) and (event.get("event_type") or event.get("type"))
                            )
        except Exception:
            pass

    after_volumes = db.get_volumes(novel_id) if apply else volumes
    after_issues = validate_timeline(after_volumes)
    statuses = [
        {"name": item.get("name"), "life_status": item.get("life_status"), "updated_chapter": item.get("updated_chapter")}
        for item in db.get_entities(novel_id)
        if item.get("entity_type") == "character" and item.get("life_status")
    ]
    observed_events = []
    try:
        observed_events = db.get_story_events(novel_id, status="occurred")
    except Exception:
        pass
    return {
        "novel_id": novel_id,
        "apply": bool(apply),
        "chapters_scanned": len(chapters_before),
        "timeline_anchors_added": scheduled,
        "planned_events_synced": event_count,
        "timeline_issues_before": before_issues,
        "timeline_issues_after": after_issues,
        "updated_volumes": updated_volumes,
        "character_life_statuses": statuses,
        "occurred_events": observed_events,
    }
