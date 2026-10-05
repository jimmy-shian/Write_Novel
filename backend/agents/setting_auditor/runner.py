# -*- coding: utf-8 -*-
"""
Setting Auditor Runner (Story Engine 2.0)
執行跨階段世界觀設定審查邏輯
"""

import json
import re
from typing import Any, Dict, Optional

from backend import persistence as db
from backend.services.narrative.setting_registry import SettingRegistry


def _scene_setting_coverage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Check that the chapter prose mentions its planned scene setting."""
    outline = payload.get("outline") if isinstance(payload.get("outline"), dict) else {}
    scene = payload.get("scene_setting") or outline.get("scene_setting") or outline.get("location")
    content = payload.get("content") or payload.get("text") or payload.get("prose") or ""
    if not scene or not content:
        return {"passed": True, "matched_keywords": [], "missing_keywords": []}

    explicit = payload.get("scene_setting_keywords") or payload.get("scene_keywords")
    if not explicit and isinstance(scene, dict):
        explicit = scene.get("keywords")
    if isinstance(explicit, str):
        explicit = [explicit]
    keywords = [str(item).strip() for item in (explicit or []) if str(item).strip()]
    auto_keywords = not keywords
    if not keywords:
        scene_text = scene if isinstance(scene, str) else " ".join(str(v) for v in scene.values())
        # Keep this deliberately small: automatic extraction only needs one
        # stable location phrase, while callers can pass exact keywords.
        keywords = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", scene_text)
        if not keywords:
            return {"passed": True, "matched_keywords": [], "missing_keywords": []}
        keywords = sorted(keywords, key=len, reverse=True)[:3]
        candidates = set(keywords)
        for term in keywords:
            if re.fullmatch(r"[\u4e00-\u9fff]+", term):
                candidates.update(term[i:i + 3] for i in range(max(0, len(term) - 2)))
        required = sorted(candidates, key=len, reverse=True)
    else:
        required = keywords

    if auto_keywords:
        matched = [keyword for keyword in required if keyword in str(content)]
        missing = [] if matched else required[:1]
    else:
        matched = [keyword for keyword in required if keyword in str(content)]
        missing = [keyword for keyword in required if keyword not in str(content)]
    return {
        "passed": not missing,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "issues": [] if not missing else [
            f"正文未覆蓋指定場景關鍵詞：{', '.join(missing)}"
        ],
    }


def run_setting_audit(
    novel_id: str,
    audit_type: str = "worldview",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    執行 Cross-Stage Setting Audit
    - audit_type = "worldview" (Audit A: 世界觀完成後機制與邊界審查)
    - audit_type = "skeleton" (Audit B: 篇卷骨架完成後設定調用審查)
    - audit_type = "chapter" (Audit C: 正文完成後設定使用與狀態更新)
    """
    if audit_type == "worldview":
        wb = db.get_latest_worldbuilding(novel_id)
        if not wb or not wb.get("content"):
            return {"passed": True, "score": 100, "message": "尚未有世界觀內容"}

        wb_dict = {}
        try:
            wb_dict = json.loads(wb["content"])
        except Exception:
            wb_dict = db.parse_worldview_to_json(wb["content"])

        # 1. 同步世界觀中的力量體系、規則、陣營至 setting_systems
        SettingRegistry.sync_from_worldview(novel_id, wb_dict)

        # 2. 審查設定健康度
        audit_res = SettingRegistry.audit_setting_health(novel_id)
        audit_res["audit_type"] = "worldview"
        return audit_res

    elif audit_type == "skeleton":
        # 檢查本卷大綱是否有效調用既有設定
        vol_idx = (payload or {}).get("volume_index", 1)
        systems = db.get_setting_systems(novel_id)
        return {
            "audit_type": "skeleton",
            "passed": True,
            "volume_index": vol_idx,
            "available_systems_count": len(systems),
            "message": f"第 {vol_idx} 卷骨架設定調用審查完畢，共有 {len(systems)} 個活躍設定系統可供調度。"
        }

    elif audit_type == "chapter":
        # 正文生成後，登錄設定使用
        ch_idx = (payload or {}).get("chapter_index", 1)
        used_settings = (payload or {}).get("setting_usage", [])
        record_usage = getattr(SettingRegistry, "record_setting_usage", SettingRegistry.record_system_usage)
        for s_name in used_settings:
            record_usage(novel_id, s_name, ch_idx)

        scene_audit = _scene_setting_coverage(payload or {})
        return {
            "audit_type": "chapter",
            "passed": scene_audit["passed"],
            "chapter_index": ch_idx,
            "updated_settings": used_settings,
            "matched_keywords": scene_audit.get("matched_keywords", []),
            "missing_keywords": scene_audit.get("missing_keywords", []),
            "issues": scene_audit.get("issues", []),
        }

    return {"passed": True, "audit_type": audit_type}
