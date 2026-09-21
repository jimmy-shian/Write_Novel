# -*- coding: utf-8 -*-
"""
Cross Relation Semantic Runner (Pass 4 執行器)

在 GeometryGraph 基礎上：
- Pass 4: 為圖譜中的跨距結構邊（CONVERGES, ECHOES, CONTRASTS 等）注入實質因果與多線碰撞動機
- 持久化至 geometry_edges 表中，供 Director Context Compiler 作為 Layer 4 Cross Context 調用
"""

from __future__ import annotations

import json
from typing import Any, Dict, Generator, List, Optional

from backend import persistence as db
from backend.agents.cross_relation.prompts import build_cross_relation_messages
from backend.geometry.models import EdgeType
from backend.models.client import call_llm_json


def _sse(obj: Dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def run_cross_relation_semantic(
    novel_id: str,
    user_prompt: Optional[str] = None,
    stream: bool = True,
    force_json: bool = True,
) -> Generator[str, None, None]:
    """
    執行 Pass 4 跨距關聯與交匯語義填充。
    """
    yield _sse({"type": "thinking", "delta": "正在啟動跨距 Motif 關聯語義編織 (Cross Relation Semantic Filling - Pass 4)...\n"})

    # 1. 載入幾何圖
    graph = db.load_geometry_graph(novel_id)
    if not graph:
        yield _sse({"type": "error", "message": "尚未建立敘事幾何圖，請先執行幾何生成階段。"})
        yield "data: [DONE]\n\n"
        return

    novel = db.get_novel(novel_id)
    title = novel.get("title", "未命名作品") if novel else "未命名作品"

    # 2. 彙整線程語義摘要
    thread_lines = []
    for t_id, t in graph.threads.items():
        t_sem = t.semantic or {}
        name = t_sem.get("thread_name") or t_id
        desc = t_sem.get("description", "")
        thread_lines.append(f"- [{t_id}] {name}：{desc}")
    threads_summary_text = "\n".join(thread_lines) if thread_lines else "主線推進與伏筆交織"

    # 3. 篩選高價值跨距 Motif 邊 (CONVERGES, ECHOES, CONTRASTS, SETS_UP, PAYS_OFF)
    target_edge_types = {
        EdgeType.CONVERGES,
        EdgeType.ECHOES,
        EdgeType.CONTRASTS,
        EdgeType.PAYS_OFF,
        EdgeType.SETS_UP,
        EdgeType.RELATIONSHIP_CHANGE,
    }

    cross_edges = []
    for e in graph.edges:
        if e.edge_type in target_edge_types:
            src_node = graph.get_node(e.source)
            tgt_node = graph.get_node(e.target)
            cross_edges.append({
                "edge_id": e.edge_id,
                "edge_type": e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type),
                "source": e.source,
                "source_chapter": src_node.chapter_window[0] if src_node else "?",
                "source_thread": src_node.primary_thread if src_node else "?",
                "target": e.target,
                "target_chapter": tgt_node.chapter_window[0] if tgt_node else "?",
                "target_thread": tgt_node.primary_thread if tgt_node else "?",
                "distance": e.distance,
            })

    yield _sse({
        "type": "thinking",
        "delta": f"【Pass 4】篩選出 {len(cross_edges)} 條跨距 Motif 關聯邊，正在調用 LLM 填入具體碰撞動機與因果細節...\n",
    })

    messages = build_cross_relation_messages(
        novel_title=title,
        threads_summary=threads_summary_text,
        cross_edges_info=cross_edges,
        user_prompt=user_prompt or "",
    )

    llm_res = call_llm_json("architect", messages) or {}
    filled_edges = llm_res.get("edges", {})

    # 4. 更新邊的語義至資料庫
    for e_id, e_data in filled_edges.items():
        db.update_edge_semantic(novel_id, e_id, e_data)

    yield _sse({
        "type": "thinking",
        "delta": f"【Pass 4 完成】成功為 {len(filled_edges)} 條跨距 Motif 邊注入因果與碰撞理由。\n",
    })

    summary_text = (
        f"跨距關聯填充完畢：成功注入 {len(filled_edges)} 條 Motif 邊的文學因果，"
        f"多線匯聚、遠距呼應與思想對比已具備充分的戲劇動機。"
    )

    result_payload = {
        "status": "success",
        "stage": "cross_relation",
        "novel_id": novel_id,
        "edges_filled": len(filled_edges),
        "summary": summary_text,
    }

    yield _sse({"type": "content", "delta": json.dumps(result_payload, ensure_ascii=False, indent=2)})
    yield "data: [DONE]\n\n"
