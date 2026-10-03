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

    # ── 提示詞瘦身：角色聖經 26 人全欄位可達 60KB+，易觸發代理上下文截斷導致空回傳 ──
    # 僅保留綁定所需的識別與弧線欄位（禁咒法師 62KB 案例）。
    def _slim_character(c):
        if not isinstance(c, dict):
            return {"name": str(c)}
        personality = c.get("personality", [])
        if isinstance(personality, str):
            personality = [personality]
        slim = {
            "name": c.get("name", ""),
            "role": c.get("role", ""),
            "personality": (personality or [])[:5],
            "want": str(c.get("want") or c.get("motivation") or "")[:200],
            "fatal_flaw": str(c.get("fatal_flaw") or "")[:200],
            "arc": str(c.get("arc") or "")[:200],
        }
        return {k: v for k, v in slim.items() if v}
    char_list = [_slim_character(c) for c in char_list[:20] if isinstance(c, dict) and c.get("name")]

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

    if not char_threads and not shift_nodes:
        yield _sse({"type": "error", "message": "幾何圖中無 CHARACTER_ARC/RELATIONSHIP_ARC 線程且無 CHARACTER_SHIFT/RELATIONSHIP_CHANGE 節點，無法執行角色語義綁定。請先重建幾何圖。"})
        yield "data: [DONE]\n\n"
        return

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
    if not isinstance(bindings, dict):
        bindings = {}
    if not isinstance(shifts, dict):
        shifts = {}

    # ── 實質防護：空結果 / 幻覺 ID 不得靜默回報成功 ──
    # 否則上游 _execute_stage_with_retry 會看到 ok=True 卻 verify 失敗，
    # 重試 20 次都拿不到真正病因（禁咒法師 42330e2b 案例即為此）。
    valid_thread_ids = set(graph.threads.keys())
    valid_node_ids = set(graph.nodes.keys())
    invalid_thread_ids = [t for t in bindings.keys() if t not in valid_thread_ids]
    invalid_node_ids = [n for n in shifts.keys() if n not in valid_node_ids]
    valid_bindings = {t: v for t, v in bindings.items() if t in valid_thread_ids}
    valid_shifts = {n: v for n, v in shifts.items() if n in valid_node_ids}

    if not valid_bindings and not valid_shifts:
        diag = (
            f"角色語義 LLM 未產出可持久化資料：目標線程 {len(char_threads)} 條、"
            f"目標節點 {len(shift_nodes)} 個，LLM 回傳 thread_bindings={len(bindings)}、"
            f"node_shifts={len(shifts)}，其中有效 thread={len(valid_bindings)}、有效 node={len(valid_shifts)}"
        )
        if invalid_thread_ids:
            diag += f"，幻覺線程ID樣本={invalid_thread_ids[:5]}"
        if invalid_node_ids:
            diag += f"，幻覺節點ID樣本={invalid_node_ids[:5]}"
        if not llm_res:
            diag += "（LLM 回傳為空，可能為模型拒答/連線異常/JSON解析失敗，請檢查模型服務與 Cookie）"
        yield _sse({"type": "error", "message": diag})
        yield "data: [DONE]\n\n"
        return

    # 4. 更新線程與節點語義（僅寫入真實存在的 ID，並合併既有語義避免覆蓋宏觀填充）
    persisted_threads = 0
    for t_id, b_data in valid_bindings.items():
        existing_sem = {}
        thread_obj = graph.threads.get(t_id)
        if thread_obj and thread_obj.semantic:
            existing_sem = dict(thread_obj.semantic)
        existing_sem.update({"character_binding": b_data if isinstance(b_data, dict) else {"value": b_data}})
        db.update_thread_semantic(novel_id, t_id, existing_sem)
        persisted_threads += 1

    persisted_nodes = 0
    for n_id, s_data in valid_shifts.items():
        node_obj = graph.nodes.get(n_id)
        existing_nsem = dict(node_obj.semantic) if node_obj and node_obj.semantic else {}
        if isinstance(s_data, dict):
            existing_nsem.update(s_data)
        else:
            existing_nsem.update({"shift": s_data})
        db.update_node_semantic(novel_id, n_id, existing_nsem)
        persisted_nodes += 1

    if invalid_thread_ids or invalid_node_ids:
        yield _sse({
            "type": "thinking",
            "delta": f"⚠️ 過濾幻覺ID：無效線程 {len(invalid_thread_ids)}（樣本 {invalid_thread_ids[:5]}），無效節點 {len(invalid_node_ids)}（樣本 {invalid_node_ids[:5]}），已僅持久化有效資料。\n",
        })

    if persisted_threads == 0 and persisted_nodes == 0:
        yield _sse({"type": "error", "message": f"角色語義持久化 0 筆（有效綁定 0），請檢查 LLM 輸出 ID 是否與幾何圖一致。"})
        yield "data: [DONE]\n\n"
        return

    yield _sse({
        "type": "thinking",
        "delta": f"【Pass 3 完成】成功綁定 {persisted_threads} 條角色線程，並注入 {persisted_nodes} 處關鍵角色心境轉變。\n",
    })

    summary_text = (
        f"角色語義填充完畢：已將名冊人物綁定至 {persisted_threads} 條幾何人物弧線，"
        f"並為 {persisted_nodes} 個轉折節點確立了心魔攻防、信念重塑與關係質變。"
    )

    result_payload = {
        "status": "success",
        "stage": "character_semantic",
        "novel_id": novel_id,
        "threads_bound": persisted_threads,
        "nodes_shifted": persisted_nodes,
        "summary": summary_text,
    }

    yield _sse({"type": "content", "delta": json.dumps(result_payload, ensure_ascii=False, indent=2)})
    yield "data: [DONE]\n\n"
