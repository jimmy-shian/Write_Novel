# -*- coding: utf-8 -*-
"""
Macro Semantic Runner (Pass 1 & Pass 2 執行器)

在 GeometryGraph 基礎上：
- Pass 1: 填充 VolumeContainer 與 ArcContainer 語義
- Pass 2: 填充 GeometryThread 語義
- 同步維護 SQLite 關聯表，確保向下相容性
"""

from __future__ import annotations

import json
from typing import Any, Dict, Generator, List, Optional

from backend import persistence as db
from backend.agents.macro_semantic.prompts import (
    build_thread_semantic_messages,
    build_volume_semantic_messages,
)
from backend.models.client import call_llm_json


def _sse(obj: Dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def run_macro_semantic(
    novel_id: str,
    user_prompt: Optional[str] = None,
    stream: bool = True,
    force_json: bool = True,
) -> Generator[str, None, None]:
    """
    執行 Pass 1 (Volume/Arc) 與 Pass 2 (Thread) 宏觀語義填充。
    """
    yield _sse({"type": "thinking", "delta": "正在啟動宏觀語義填充 (Macro Semantic Filling - Pass 1 & 2)...\n"})

    # 1. 檢驗並載入幾何圖譜
    graph = db.load_geometry_graph(novel_id)
    if not graph or not graph.volumes:
        yield _sse({"type": "error", "message": "尚未建立敘事幾何圖，請先執行幾何生成階段。"})
        yield "data: [DONE]\n\n"
        return

    novel = db.get_novel(novel_id)
    title = novel.get("title", "未命名作品") if novel else "未命名作品"
    genre = novel.get("genre", "玄幻") if novel else "玄幻"

    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = wb.get("content", "") if wb else ""

    # ==========================================
    # Pass 1: 篇卷與弧線語義填充 (Volume & Arc)
    # ==========================================
    yield _sse({"type": "thinking", "delta": f"【Pass 1】正在為全書 {len(graph.volumes)} 個篇卷容器注入主題與衝突核心...\n"})

    vol_specs = [
        {
            "volume_id": v.volume_id,
            "volume_index": v.volume_index,
            "chapter_range": v.chapter_range,
            "arcs": v.arc_ids,
        }
        for v in sorted(graph.volumes.values(), key=lambda x: x.volume_index)
    ]

    vol_messages = build_volume_semantic_messages(
        novel_title=title,
        genre=genre,
        worldview_text=worldview_text,
        volumes_info=vol_specs,
        user_prompt=user_prompt or "",
    )

    vol_res = call_llm_json("volumes", vol_messages) or {}
    filled_vols = vol_res.get("volumes", {})
    filled_arcs = vol_res.get("arcs", {})

    # 更新篇卷容器語義並同步維護 volumes 表
    vol_summary_lines = []
    for v_id, sem in filled_vols.items():
        db.update_volume_semantic(novel_id, v_id, sem)
        v_obj = graph.volumes.get(v_id)
        v_idx = v_obj.volume_index if v_obj else 1
        ch_span = (v_obj.chapter_range[1] - v_obj.chapter_range[0] + 1) if v_obj else 50
        v_title = sem.get("title", f"第 {v_idx} 卷")
        v_summary = sem.get("summary", "")

        vol_summary_lines.append(f"- 【第 {v_idx} 卷：{v_title}】{v_summary}")

        # 同步回寫至原系統 volumes 實體表，確保向下相容性
        try:
            db.create_or_update_volume(
                novel_id=novel_id,
                volume_index=v_idx,
                title=v_title,
                summary=v_summary,
                chapter_count=ch_span,
            )
        except Exception:
            pass

    yield _sse({"type": "thinking", "delta": f"【Pass 1 完成】已成功填充 {len(filled_vols)} 卷語義與 {len(filled_arcs)} 條弧線。\n"})

    # ==========================================
    # Pass 2: 敘事線程語義填充 (Thread Semantics)
    # ==========================================
    yield _sse({"type": "thinking", "delta": f"【Pass 2】正在為全書 {len(graph.threads)} 條敘事線程（主線、副線、主題線）注入劇本線索...\n"})

    thread_specs = [
        {
            "thread_id": t.thread_id,
            "thread_type": t.thread_type.value if hasattr(t.thread_type, "value") else str(t.thread_type),
            "node_sequence": t.node_sequence,
            "structural_skeleton": [r.value if hasattr(r, "value") else str(r) for r in t.structural_skeleton],
            "metadata": t.metadata,
        }
        for t in graph.threads.values()
    ]

    thread_messages = build_thread_semantic_messages(
        novel_title=title,
        genre=genre,
        worldview_text=worldview_text,
        volume_semantics_summary="\n".join(vol_summary_lines),
        threads_info=thread_specs,
        user_prompt=user_prompt or "",
    )

    thread_res = call_llm_json("architect", thread_messages) or {}
    filled_threads = thread_res.get("threads", {})

    for t_id, sem in filled_threads.items():
        db.update_thread_semantic(novel_id, t_id, sem)

    yield _sse({"type": "thinking", "delta": f"【Pass 2 完成】已成功為 {len(filled_threads)} 條幾何線程注入具體懸念與目標。\n"})

    # 3. 輸出最終結果
    summary_text = (
        f"宏觀語義填充完畢：成功注入 {len(filled_vols)} 個卷主題與 "
        f"{len(filled_threads)} 條具體劇情線程。幾何骨架已具備明確情節方向。"
    )

    result_payload = {
        "status": "success",
        "stage": "macro_semantic",
        "novel_id": novel_id,
        "volumes_filled": len(filled_vols),
        "threads_filled": len(filled_threads),
        "summary": summary_text,
    }

    yield _sse({"type": "content", "delta": json.dumps(result_payload, ensure_ascii=False, indent=2)})
    yield "data: [DONE]\n\n"
