# -*- coding: utf-8 -*-
"""總監工具：伏筆配額派發 (dispatch_foreshadowing_quota)

由總監依據全書宏觀架構與分卷節奏，為指定卷或全書派發伏筆埋設 (plants)、
伏筆回收 (payoffs) 與關鍵轉折 (turns) 任務。

Python 作為剛性夾具驗證，確保：
- 1 <= plant_chapter < payoff_chapter <= T
- 章號落在該卷的 [start_chapter, end_chapter] 區間內
- 回收的伏筆存在於已埋設清單中

總監作為決策大腦，Python 作為邊界校驗裁判。
"""

import json
from typing import Any, Dict, List, Optional

from backend.services.foreshadowing.blueprint import (
    dispatch_foreshadowing_allocation,
    get_foreshadowing_lifecycle,
    get_overdue_foreshadowing,
    get_global_foreshadowing_blueprint,
)
from backend.services.foreshadowing.chapter_math import get_volume_chapter_range


def dispatch_foreshadowing_quota(
    novel_id: str,
    volume_index: Optional[int] = None,
    plants: Optional[List[Dict[str, Any]]] = None,
    payoffs: Optional[List[Dict[str, Any]]] = None,
    turns: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """總監派發伏筆配額工具。

    Parameters:
        novel_id: 作品 ID
        volume_index: 可選。若指定，所有 plants/payoffs 的章號必須在該卷區間內
        plants: [{"seed_id": "FS001", "chapter": 15}, ...] 本批要埋設的伏筆
        payoffs: [{"seed_id": "FS001", "chapter": 45}, ...] 本批要回收的伏筆
        turns: [chapter_index, ...] 本批轉折點章節

    Returns:
        {"status": "ok", "dispatched": {...}, "lifecycle_summary": {...}}
    """
    from backend import persistence as db

    volumes = db.get_volumes(novel_id)
    if not volumes:
        return {
            "status": "error",
            "message": "分卷結構尚未確立，無法派發伏筆配額。請先完成分卷規劃。",
        }

    # 取得現有藍圖
    existing_blueprint = get_global_foreshadowing_blueprint(novel_id)
    existing_alloc = list(existing_blueprint.get("foreshadowing_allocations", []))
    existing_turns = list(existing_blueprint.get("turning_allocations", []))

    # 驗證卷區間
    vol_start, vol_end = None, None
    if volume_index is not None:
        try:
            vol_start, vol_end = get_volume_chapter_range(volumes, volume_index)
        except Exception:
            return {
                "status": "error",
                "message": f"找不到第 {volume_index} 卷的章節區間。",
            }

    errors = []

    # 處理 plants：建立新的 (plant, payoff) 對，先只填 plant
    plant_map = {}
    for p in (plants or []):
        seed_id = p.get("seed_id", "")
        ch = p.get("chapter", 0)
        if vol_start and vol_end and (ch < vol_start or ch > vol_end):
            errors.append(f"Plant {seed_id} 的章號 {ch} 不在第 {volume_index} 卷區間 [{vol_start}, {vol_end}]")
            continue
        plant_map[seed_id] = ch

    # 處理 payoffs：尋找對應的 plant 建立完整對
    payoff_map = {}
    for p in (payoffs or []):
        seed_id = p.get("seed_id", "")
        ch = p.get("chapter", 0)
        if vol_start and vol_end and (ch < vol_start or ch > vol_end):
            errors.append(f"Payoff {seed_id} 的章號 {ch} 不在第 {volume_index} 卷區間 [{vol_start}, {vol_end}]")
            continue
        payoff_map[seed_id] = ch

    # 合併：建立完整 allocation 對
    new_alloc = list(existing_alloc)  # 保留既有的

    # 更新 plant 位置
    for seed_id, plant_ch in plant_map.items():
        # 嘗試找到既有的 allocation pair 並更新 plant
        idx = _seed_id_to_index(seed_id)
        if idx is not None and idx < len(new_alloc):
            pair = list(new_alloc[idx])
            pair[0] = plant_ch
            new_alloc[idx] = tuple(pair)
        # 否則新增一個暫時只有 plant 的 pair
        elif idx is not None:
            while len(new_alloc) <= idx:
                new_alloc.append((1, 2))
            new_alloc[idx] = (plant_ch, new_alloc[idx][1] if idx < len(new_alloc) else plant_ch + 1)

    # 更新 payoff 位置
    for seed_id, payoff_ch in payoff_map.items():
        idx = _seed_id_to_index(seed_id)
        if idx is not None and idx < len(new_alloc):
            pair = list(new_alloc[idx])
            pair[1] = payoff_ch
            new_alloc[idx] = tuple(pair)

    # 更新 turns
    new_turns = list(existing_turns)
    if turns:
        new_turns = turns

    if errors:
        return {
            "status": "error",
            "message": "部分派發驗證失敗",
            "errors": errors,
        }

    # 呼叫核心派發函數（含夾具驗證）
    try:
        blueprint = dispatch_foreshadowing_allocation(
            novel_id=novel_id,
            allocations=new_alloc,
            turning_allocations=new_turns,
        )
    except ValueError as ve:
        return {
            "status": "error",
            "message": str(ve),
        }

    # 取得最新生命週期
    lifecycle = get_foreshadowing_lifecycle(novel_id)
    overdue = [s for s in lifecycle if s["state"] == "OVERDUE"]

    return {
        "status": "ok",
        "dispatched": {
            "total_allocations": len(new_alloc),
            "total_turns": len(new_turns),
            "plants_updated": list(plant_map.keys()),
            "payoffs_updated": list(payoff_map.keys()),
        },
        "lifecycle_summary": {
            "total_seeds": len(lifecycle),
            "pending": sum(1 for s in lifecycle if s["state"] == "PENDING"),
            "planted": sum(1 for s in lifecycle if s["state"] == "PLANTED"),
            "paid": sum(1 for s in lifecycle if s["state"] == "PAID"),
            "overdue": len(overdue),
            "overdue_details": overdue[:10],
        },
    }


def _seed_id_to_index(seed_id: str) -> Optional[int]:
    """將 'FS001' 格式的 seed_id 轉換為 0-based index。"""
    if not seed_id or not seed_id.startswith("FS"):
        return None
    try:
        return int(seed_id[2:]) - 1
    except ValueError:
        return None
