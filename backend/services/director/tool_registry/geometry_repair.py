# -*- coding: utf-8 -*-
"""
Director Tool: repair_story_geometry (敘事幾何修復工具)

只有符合以下 4 大重大條件之一才准調用：
1. 密度超載：1個骨架節點塞 >=3 個 turning_points，或 >=4 個 plant/payoff，或 1章要寫完2個場景跳躍+1個人物轉折。
2. 因果斷層：A->C 中間缺 B，沒有 B 讀者看不懂，必須 INSERT 橋接章。
3. 收束撞車：同卷要收 2 條大線 + 卷末高潮，3 節點收不完，必須 EXPAND 3->5。
4. 章數膨脹：volume.chapter_count 要變，chapter_index 連續性要重排。
沒中上面 4 條，一律不准加節點，改走舊 evaluate_output + supplement_content 打回重寫。

操作支援：
  SPLIT: 1 -> 2/3
  EXPAND: 3 -> 5
  INSERT: 橋接章，後續章號順延
  COMPRESS: 水章壓縮合併
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.geometry.models import RepairOperation, RepairProposal
from backend.geometry.repair import GeometryRepairCondition, GeometryRepairGatekeeper
from backend.persistence.repositories.geometry import apply_repair


def repair_story_geometry(
    novel_id: str,
    operation: str,
    condition: str,
    target_nodes: Optional[List[str]] = None,
    reason: str = "",
    detail: Optional[Dict[str, Any]] = None,
    gatekeeper_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    執行幾何拓撲修復工具。
    """
    target_nodes = target_nodes or []
    detail = detail or {}
    gatekeeper_context = gatekeeper_context or {}

    try:
        op_enum = RepairOperation(operation)
    except ValueError:
        return {
            "success": False,
            "error": f"不支援的幾何操作: {operation}。僅支援 SPLIT, EXPAND, INSERT, COMPRESS。",
        }

    try:
        cond_enum = GeometryRepairCondition(condition)
    except ValueError:
        return {
            "success": False,
            "error": f"不支援的重大條件: {condition}。僅支援 DENSITY_OVERLOAD, CAUSAL_GAP, CONVERGENCE_COLLISION, CHAPTER_EXPANSION。",
        }

    proposal = RepairProposal(
        operation=op_enum,
        target_nodes=target_nodes,
        reason=reason,
        detail=detail,
        approved=True,
    )

    result = apply_repair(
        novel_id=novel_id,
        proposal=proposal,
        condition=cond_enum,
        gatekeeper_context=gatekeeper_context,
    )

    return {
        "success": result.success,
        "operation": result.operation.value if hasattr(result.operation, "value") else str(result.operation),
        "condition": result.condition.value if hasattr(result.condition, "value") else str(result.condition),
        "affected_nodes": result.affected_nodes,
        "new_nodes": result.new_nodes,
        "removed_nodes": result.removed_nodes,
        "chapter_delta": result.chapter_delta,
        "message": result.message,
    }
