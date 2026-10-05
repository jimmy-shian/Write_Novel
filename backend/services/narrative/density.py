# -*- coding: utf-8 -*-
"""
Chapter Outline Density Overload Detection & Outline Splitting Helpers
"""
import copy
from typing import Any, Dict, List, Optional


def is_chapter_outline_density_overloaded(chapter_outline: Dict[str, Any]) -> bool:
    """
    判斷單章細綱是否資訊密度過載。
    判斷標準（滿足任一即判定為過載）：
    1. 轉折點數量 turning_points >= 2
    2. 伏筆任務合計 len(foreshadowing_plants) + len(foreshadowing_payoffs) >= 4
    3. 事件/場景數量 len(events) >= 3
    4. 場景跳躍 + 角色轉折 (scene_jumps + character_turns >= 3 或 scene_jumps >= 2 且 character_turns >= 1)
    """
    if not isinstance(chapter_outline, dict):
        return False

    allocated = chapter_outline.get("allocated_tasks") or {}
    if not isinstance(allocated, dict):
        allocated = {}

    # 1. 轉折點
    turning_points = (
        allocated.get("turning_points")
        or chapter_outline.get("turning_points")
        or []
    )
    tp_count = len(turning_points) if isinstance(turning_points, list) else int(turning_points or 0)
    if tp_count >= 2:
        return True

    # 2. 伏筆埋設與回收
    plants = (
        allocated.get("foreshadowing_plants")
        or chapter_outline.get("foreshadowing_plants")
        or []
    )
    payoffs = (
        allocated.get("foreshadowing_payoffs")
        or chapter_outline.get("foreshadowing_payoffs")
        or []
    )
    plant_count = len(plants) if isinstance(plants, list) else int(plants or 0)
    payoff_count = len(payoffs) if isinstance(payoffs, list) else int(payoffs or 0)
    if (plant_count + payoff_count) >= 4:
        return True

    # 3. 事件數量
    events = chapter_outline.get("events") or []
    event_count = len(events) if isinstance(events, list) else int(events or 0)
    if event_count >= 3:
        return True

    # 4. 場景跳躍與角色轉折
    scene_jumps = chapter_outline.get("scene_jumps")
    if scene_jumps is None:
        if isinstance(events, list) and len(events) > 1:
            locs = [
                e.get("location")
                for e in events
                if isinstance(e, dict) and e.get("location")
            ]
            if locs:
                scene_jumps = sum(1 for i in range(len(locs) - 1) if locs[i] != locs[i + 1])
            else:
                scene_jumps = len(events) - 1
        else:
            scene_jumps = 0
    else:
        scene_jumps = int(scene_jumps or 0)

    character_turns = chapter_outline.get("character_turns")
    if character_turns is None:
        character_turns = tp_count
    else:
        character_turns = int(character_turns or 0)

    if (scene_jumps >= 2 and character_turns >= 1) or (scene_jumps + character_turns >= 3):
        return True

    return False


def build_split_chapter_outlines(
    original_outline: Dict[str, Any],
    split_count: int = 2,
) -> List[Dict[str, Any]]:
    """
    將過載的單章大綱拆分為 split_count 個子章節大綱。
    """
    split_count = max(2, min(3, split_count))
    ch_idx = int(original_outline.get("chapter_index", 1))
    title = original_outline.get("chapter_title") or f"第 {ch_idx} 章"
    summary = original_outline.get("chapter_summary") or ""
    events = original_outline.get("events") or []
    allocated = copy.deepcopy(original_outline.get("allocated_tasks") or {})

    # 按比例拆分 events
    ev_total = len(events)
    step_ev = max(1, (ev_total + split_count - 1) // split_count) if ev_total > 0 else 0

    # 每個子章都拿到自己的深拷貝，避免後續 writer 修改時互相污染。
    def _chunk(lst):
        k, m = divmod(len(lst), split_count)
        return [
            copy.deepcopy(lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)])
            for i in range(split_count)
        ]

    def _split_field(value):
        return _chunk(value) if isinstance(value, list) else [copy.deepcopy(value) for _ in range(split_count)]

    task_chunks = {
        key: _split_field(value)
        for key, value in allocated.items()
    }
    beat_chunks = {
        key: _chunk(value)
        for key in ("scene_beats", "beats")
        if isinstance((value := original_outline.get(key)), list)
    }

    sub_outlines = []
    suffix_labels = ["（上）", "（中）", "（下）"] if split_count == 3 else ["（上）", "（下）"]

    for i in range(split_count):
        sub_ch_idx = ch_idx + i
        ev_start = i * step_ev
        ev_end = ev_start + step_ev if i < split_count - 1 else ev_total
        sub_events = events[ev_start:ev_end] if ev_total > 0 else []

        sub_outline = copy.deepcopy(original_outline)
        sub_outline["chapter_index"] = sub_ch_idx
        sub_outline["chapter_title"] = f"{title}{suffix_labels[i]}"
        part_name = f"第{i + 1}階段"
        sub_outline["chapter_summary"] = f"【{part_name}】{summary}"
        sub_outline["events"] = copy.deepcopy(sub_events)
        sub_outline["allocated_tasks"] = {
            key: chunks[i] for key, chunks in task_chunks.items()
        }
        for key, chunks in beat_chunks.items():
            sub_outline[key] = chunks[i]
        if i == 0:
            sub_outline["scene_function"] = original_outline.get("scene_function") or "confrontation"
        elif i == split_count - 1:
            sub_outline["scene_function"] = "climax"
        else:
            sub_outline["scene_function"] = "transition"

        sub_outlines.append(sub_outline)

    return sub_outlines
