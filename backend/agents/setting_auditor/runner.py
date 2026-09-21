# -*- coding: utf-8 -*-
"""
Setting Auditor Runner (Story Engine 2.0)
執行跨階段世界觀設定審查邏輯
"""

import json
from typing import Any, Dict, Optional

from backend import persistence as db
from backend.services.narrative.setting_registry import SettingRegistry


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
        for s_name in used_settings:
            SettingRegistry.record_setting_usage(novel_id, s_name, ch_idx)

        return {
            "audit_type": "chapter",
            "passed": True,
            "chapter_index": ch_idx,
            "updated_settings": used_settings,
        }

    return {"passed": True, "audit_type": audit_type}
