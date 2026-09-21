# -*- coding: utf-8 -*-
"""
Character Semantic Runner (Pass 3 執行器)

在 GeometryGraph 基礎上：
- Pass 3: 將角色聖經中的人物綁定到幾何圖的角色弧線 (CHARACTER_ARC) 與關係線 (RELATIONSHIP_ARC)
- 為幾何圖中的 CHARACTER_SHIFT 與 RELATIONSHIP_CHANGE 節點注入心境轉向語義
"""

from __future__ import annotations

import json
from typing import Any, Dict, Generator, List, Optional

from backend import persistence as db
from backend.agents.character_semantic.prompts import build_character_semantic_messages
from backend.geometry.models import StructuralRole, ThreadType
from backend.models.client import call_llm_json


def _sse(obj: Dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def run_character_semantic(
    novel_id: str,
    user_prompt: Optional[str] = None,
    stream: bool = True,
    force_json: bool = True,
) -> Generator[str, None, None]:
    """
    執行 Pass 3 角色幾何插槽綁定與弧線心境填充。
    """
    yield _sse({"type": "thinking", "delta": "正在啟動角色語義綁定 (Character Semantic Filling - Pass 3)...\n"})

    # 1. 載入幾何圖與角色庫
    graph = db.load_geometry_graph(novel_id)
    if not graph:
        yield _sse({"type": "error", "message": "尚未建立敘事幾何圖，請先執行幾何生成階段。"})
        yield "data: [DONE]\n\n"
        return

    novel = db.get_novel(novel_id)
    title = novel.get("title", "未命名作品") if novel else "未命名作品"

    char_record = db.get_latest_characters(novel_id)
    char_list = []
    if char_record and char_record.get("parsed_data"):
        raw = char_record["parsed_data"]
        char_list = raw.get("characters", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])

    if not char_list:
        # Fallback: 若無立卡角色，提供基礎提示
        char_list = [
            {"name": "主角", "role": "主角", "personality": ["堅毅", "謹慎"], "want": "尋找身世真相"},
            {"name": "主要宿敵", "role": "反派", "personality": ["野心勃勃", "殘酷"], "want": "奪取宗門大權"},
        ]

    # 2. 篩選 CHARACTER_ARC 與 RELATIONSHIP_ARC 線程
    target_thread_types = {ThreadType.CHARACTER_ARC, ThreadType.RELATIONSHIP_ARC}
    char_threads = [
        {
            "thread_id": t.thread_id,
            "thread_type": t.thread_type.value if hasattr(t.thread_type, "value") else str(t.thread_type),
            "node_count": len(t.node_sequence),
            "chapter_span": t.metadata.get("chapter_span", (1, 1)),
        }
        for t in graph.threads.values()
        if t.thread_type in target_thread_types
    ]

    # 3. 篩選 CHARACTER_SHIFT 與 RELATIONSHIP_CHANGE 節點
    target_roles = {StructuralRole.CHARACTER_SHIFT, StructuralRole.RELATIONSHIP_CHANGE}
    shift_nodes = [
        {
            "node_id": n.node_id,
            "structural_role": n.structural_role.value if hasattr(n.structural_role, "value") else str(n.structural_role),
            "chapter_window": n.chapter_window,
            "primary_thread": n.primary_thread,
        }
        for n in graph.nodes.values()
        if n.structural_role in target_roles
    ]

    yield _sse({
        "type": "thinking",
        "delta": f"【Pass 3】正在為 {len(char_threads)} 條角色/關係線程綁定人物，並為 {len(shift_nodes)} 個心境位移節點注入戲劇抉擇...\n",
    })

    messages = build_character_semantic_messages(
        novel_title=title,
        characters_bible=char_list,
        character_threads_info=char_threads,
        shift_nodes_info=shift_nodes,
        user_prompt=user_prompt or "",
    )

    llm_res = call_llm_json("character", messages) or {}
    bindings = llm_res.get("thread_bindings", {})
    shifts = llm_res.get("node_shifts", {})

    # 4. 更新線程與節點語義
    for t_id, b_data in bindings.items():
        existing_sem = {}
        thread_obj = graph.threads.get(t_id)
        if thread_obj and thread_obj.semantic:
            existing_sem = thread_obj.semantic
        existing_sem.update({"character_binding": b_data})
        db.update_thread_semantic(novel_id, t_id, existing_sem)

    for n_id, s_data in shifts.items():
        db.update_node_semantic(novel_id, n_id, s_data)

    yield _sse({
        "type": "thinking",
        "delta": f"【Pass 3 完成】成功綁定 {len(bindings)} 條角色線程，並注入 {len(shifts)} 處關鍵角色心境轉變。\n",
    })

    summary_text = (
        f"角色語義填充完畢：已將名冊人物綁定至 {len(bindings)} 條幾何人物弧線，"
        f"並為 {len(shifts)} 個轉折節點確立了心魔攻防、信念重塑與關係質變。"
    )

    result_payload = {
        "status": "success",
        "stage": "character_semantic",
        "novel_id": novel_id,
        "threads_bound": len(bindings),
        "nodes_shifted": len(shifts),
        "summary": summary_text,
    }

    yield _sse({"type": "content", "delta": json.dumps(result_payload, ensure_ascii=False, indent=2)})
    yield "data: [DONE]\n\n"
