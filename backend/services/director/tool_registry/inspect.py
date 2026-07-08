# -*- coding: utf-8 -*-
import json
from typing import Optional, Dict, Any, List

from backend import persistence as db
from backend.models.parsers import extract_json_block

def _coerce_range(start_index: Any = None, end_index: Any = None, default_size: int = 15) -> tuple[int, int]:
    try:
        start = int(start_index or 1)
    except Exception:
        start = 1
    try:
        end = int(end_index or (start + default_size - 1))
    except Exception:
        end = start + default_size - 1
    start = max(1, start)
    end = max(start, end)
    return start, end

def _page_items(items: List[Any], start_index: int, end_index: int) -> Dict[str, Any]:
    start_offset = max(0, start_index - 1)
    end_offset = max(start_offset, end_index)
    return {
        "start_index": start_index,
        "end_index": end_index,
        "total_count": len(items),
        "returned_count": len(items[start_offset:end_offset]),
        "items": items[start_offset:end_offset],
    }

def expand_collapsed_json(
    stage_name: str,
    field_name: str,
    start_index: int,
    end_index: int,
    novel_id: str
) -> Dict[str, Any]:
    """
    [Tool 4] 允許總監分批展開查看被收合的 JSON 陣列內容 (如 1~10, 11~20)
    避免一次載入全部 50 個項目導致上下文溢出，使總監能精準評估。
    """
    if stage_name in ("foreshadowing", "worldview"):
        wb = db.get_latest_worldbuilding(novel_id)
        if not wb:
            return {"success": False, "error": "世界觀設定為空"}
        try:
            parsed = json.loads(wb["content"])
        except Exception:
            parsed = db.parse_worldview_to_json(wb["content"])

        if not isinstance(parsed, dict):
            return {"success": False, "error": "無法解析世界觀 JSON"}

        items = parsed.get(field_name, [])
        if not isinstance(items, list):
            return {"success": False, "error": f"欄位 {field_name} 不是列表"}

        total_count = len(items)
        # Convert 1-based indexing to 0-based slice
        start_offset = max(0, start_index - 1)
        end_offset = max(start_offset, end_index)
        sub_items = items[start_offset:end_offset]

        return {
            "success": True,
            "stage_name": stage_name,
            "field_name": field_name,
            "start_index": start_index,
            "end_index": end_index,
            "total_count": total_count,
            "returned_count": len(sub_items),
            "items": sub_items,
            "step_description": f"已展開查看 {field_name} 的第 {start_index} 到 {end_index} 個項目 (總計 {total_count} 個)。"
        }
    else:
        return {"success": False, "error": f"不支援的階段: {stage_name}"}

def inspect_content_block(
    stage_name: str,
    block_name: str = "",
    novel_id: str = "",
    volume_index: Optional[int] = None,
    chapter_index: Optional[int] = None,
    start_index: int = 1,
    end_index: Optional[int] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """
    [Tool] Inspect a concrete persisted block chosen by the Director.
    This is the preferred path for long inputs: counts stay in validation reports,
    and details are paged by explicit location/range.
    """
    stage = (stage_name or "").strip()
    block = (block_name or "").strip()

    if stage in ("volumes", "volume_skeleton") and not block:
        block = "volumes" if stage == "volumes" else "chapters_outline"

    if stage == "volume_skeleton" and volume_index is not None:
        start_chapter = extra.get("start_chapter")
        end_chapter = extra.get("end_chapter")
        if start_chapter is not None or end_chapter is not None:
            try:
                vols_for_range = db.get_volumes(novel_id)
                vol_start, vol_end = db.get_volume_chapter_range(vols_for_range, int(volume_index))
                if start_chapter is not None:
                    start_index = max(1, int(start_chapter) - vol_start + 1)
                if end_chapter is not None:
                    end_index = max(start_index, min(vol_end, int(end_chapter)) - vol_start + 1)
            except Exception:
                pass

    start, end = _coerce_range(start_index, end_index)

    if stage in ("worldview", "foreshadowing"):
        wb = db.get_latest_worldbuilding(novel_id)
        if not wb:
            return {"success": False, "error": "世界觀設定為空"}
        try:
            parsed = json.loads(wb["content"])
        except Exception:
            parsed = db.parse_worldview_to_json(wb["content"])
        if not isinstance(parsed, dict):
            return {"success": False, "error": "無法解析世界觀 JSON"}
        value = parsed.get(block)
        if isinstance(value, list):
            return {"success": True, "stage_name": stage, "block_name": block, **_page_items(value, start, end)}
        return {"success": True, "stage_name": stage, "block_name": block, "value": value}

    if stage == "characters":
        char_data = db.get_latest_characters(novel_id)
        parsed = char_data.get("parsed_data") if char_data else None
        chars = parsed.get("characters", []) if isinstance(parsed, dict) else []
        if block in ("characters", "角色", ""):
            return {"success": True, "stage_name": stage, "block_name": "characters", **_page_items(chars, start, end)}
        return {"success": False, "error": f"不支援的角色區塊: {block}"}

    if stage in ("volumes", "volume_skeleton"):
        vols = db.get_volumes(novel_id)
        if stage == "volumes" or block in ("volumes", "篇卷", ""):
            return {"success": True, "stage_name": stage, "block_name": "volumes", **_page_items(vols, start, end)}
        try:
            vol_idx = int(volume_index) if volume_index is not None else None
        except Exception:
            vol_idx = None
        target_vol = next((v for v in vols if int(v.get("volume_index", 0)) == int(vol_idx or 0)), None)
        if not target_vol:
            return {"success": False, "error": f"找不到第 {vol_idx} 卷"}
        chapters = target_vol.get("chapters_outline") or []
        if isinstance(chapters, str):
            try:
                chapters = json.loads(chapters)
            except Exception:
                chapters = []
        return {
            "success": True,
            "stage_name": stage,
            "block_name": "chapters_outline",
            "volume_index": vol_idx,
            **_page_items(chapters if isinstance(chapters, list) else [], start, end),
        }

    if stage in ("writer", "editor"):
        try:
            ch_idx = int(chapter_index or 1)
        except Exception:
            ch_idx = 1
        chapter = db.get_latest_chapter(novel_id, ch_idx)
        return {
            "success": bool(chapter),
            "stage_name": stage,
            "block_name": block or "chapter",
            "chapter_index": ch_idx,
            "chapter": dict(chapter) if chapter else None,
            "error": None if chapter else f"第 {ch_idx} 章尚無正文",
        }

    if stage == "last_agent_run":
        run = db.get_last_agent_run(novel_id)
        if not run:
            return {"success": False, "error": "沒有上一輪 Agent 執行記錄"}
        if block not in ("input_data", "output_data", "all", ""):
            return {"success": False, "error": f"不支援的 last_agent_run 區塊: {block}"}
        payload = {
            "agent_name": run.get("agent_name"),
            "timestamp": run.get("timestamp"),
        }
        fields = ("input_data", "output_data") if block in ("all", "") else (block,)
        for field in fields:
            value = run.get(field) or ""
            parsed = None
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = extract_json_block(value)
            payload[field] = parsed if parsed else value
            payload[f"{field}_char_count"] = len(value)
        return {"success": True, "stage_name": stage, "block_name": block or "all", **payload}

    if stage == "novel":
        novel = db.get_novel(novel_id)
        if not novel:
            return {"success": False, "error": "找不到小說"}
        if block in ("pipeline_prompt", ""):
            value = novel.get("pipeline_prompt") or ""
            return {
                "success": True,
                "stage_name": stage,
                "block_name": "pipeline_prompt",
                "char_count": len(value),
                "value": value,
            }
        return {"success": False, "error": f"不支援的 novel 區塊: {block}"}

    return {"success": False, "error": f"不支援的階段: {stage}"}
