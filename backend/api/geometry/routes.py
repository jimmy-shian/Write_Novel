# -*- coding: utf-8 -*-
"""
敘事幾何 API 路由 (Narrative Geometry API Routes)

提供前端骨架圖視覺化、節點檢視、幾何參數調整與手動/自動修復 (Repair) 介面。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import GeometryComplexity, GeometryParams, RepairOperation
from backend.geometry.repair import GeometryRepairCondition
from backend.services.director.tools import repair_story_geometry

router = APIRouter(tags=["geometry"])


@router.get("/novels/{novel_id}/geometry")
def get_geometry_graph_endpoint(
    novel_id: str,
    chapter_start: Optional[int] = Query(None, description="篩選起始章節"),
    chapter_end: Optional[int] = Query(None, description="篩選結束章節"),
):
    """取得小說完整的幾何圖結構或章節切片。"""
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    graph = db.load_geometry_graph(novel_id)
    if not graph:
        return {
            "has_geometry": False,
            "novel_id": novel_id,
            "stats": {"node_count": 0, "edge_count": 0, "thread_count": 0, "filling_progress": 0.0},
            "nodes": [],
            "edges": [],
            "threads": [],
            "volumes": [],
        }

    stats = db.get_geometry_stats(novel_id)

    # 若有章節範圍篩選
    nodes = list(graph.nodes.values())
    if chapter_start is not None and chapter_end is not None:
        nodes = graph.get_nodes_in_range(chapter_start, chapter_end)
    elif chapter_start is not None:
        nodes = [n for n in nodes if n.chapter_window[1] >= chapter_start]
    elif chapter_end is not None:
        nodes = [n for n in nodes if n.chapter_window[0] <= chapter_end]

    visible_node_ids = {n.node_id for n in nodes}
    visible_edges = [
        e for e in graph.edges
        if e.source in visible_node_ids and e.target in visible_node_ids
    ]

    return {
        "has_geometry": True,
        "novel_id": novel_id,
        "params": {
            "target_chapters": graph.params.target_chapters,
            "volume_count": graph.params.volume_count,
            "complexity": graph.params.complexity.value if hasattr(graph.params.complexity, "value") else str(graph.params.complexity),
        },
        "stats": stats,
        "nodes": [
            {
                "node_id": n.node_id,
                "volume_index": n.hierarchy.volume_index,
                "arc_index": n.hierarchy.arc_index,
                "sequence_index": n.hierarchy.sequence_index,
                "chapter_start": n.chapter_window[0],
                "chapter_end": n.chapter_window[1],
                "structural_role": n.structural_role.value if hasattr(n.structural_role, "value") else str(n.structural_role),
                "primary_thread": n.primary_thread,
                "importance": n.importance,
                "semantic": n.semantic,
                "metadata": n.metadata,
            }
            for n in nodes
        ],
        "edges": [
            {
                "edge_id": e.edge_id,
                "source": e.source,
                "target": e.target,
                "edge_type": e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type),
                "distance": e.distance,
                "semantic": e.semantic,
                "metadata": e.metadata,
            }
            for e in visible_edges
        ],
        "threads": [
            {
                "thread_id": t.thread_id,
                "thread_type": t.thread_type.value if hasattr(t.thread_type, "value") else str(t.thread_type),
                "node_sequence": t.node_sequence,
                "structural_skeleton": [r.value if hasattr(r, "value") else str(r) for r in t.structural_skeleton],
                "semantic": t.semantic,
                "metadata": t.metadata,
            }
            for t in graph.threads.values()
        ],
        "volumes": [
            {
                "volume_id": v.volume_id,
                "volume_index": v.volume_index,
                "chapter_start": v.chapter_range[0],
                "chapter_end": v.chapter_range[1],
                "arc_ids": v.arc_ids,
                "semantic": v.semantic,
            }
            for v in graph.volumes.values()
        ],
    }


@router.get("/novels/{novel_id}/geometry/stats")
def get_geometry_stats_endpoint(novel_id: str):
    """取得幾何圖的整體統計與填充進度。"""
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return db.get_geometry_stats(novel_id)


@router.post("/novels/{novel_id}/geometry/generate")
def generate_geometry_endpoint(
    novel_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
):
    """手動重新生成該作品的敘事幾何骨架。"""
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    target_chapters = int(payload.get("target_chapters") or 800)
    volume_count = int(payload.get("volume_count") or max(1, target_chapters // 50))
    chapters_per_volume = max(1, target_chapters // volume_count)
    complexity_str = payload.get("complexity", "DENSE")

    try:
        complexity = GeometryComplexity(complexity_str)
    except ValueError:
        complexity = GeometryComplexity.DENSE

    params = GeometryParams(
        target_chapters=target_chapters,
        volume_count=volume_count,
        chapters_per_volume=chapters_per_volume,
        complexity=complexity,
        main_thread_count=int(payload.get("main_thread_count") or 4),
        subplot_count=int(payload.get("subplot_count") or 12),
        character_arc_count=int(payload.get("character_arc_count") or 8),
        relationship_arc_count=int(payload.get("relationship_arc_count") or 6),
        thematic_thread_count=int(payload.get("thematic_thread_count") or 4),
        seed_for_rng=f"manual_{novel_id}",
    )

    generator = GeometryGenerator(params)
    graph = generator.generate()
    db.save_geometry_graph(novel_id, graph)
    stats = db.get_geometry_stats(novel_id)

    return {
        "status": "success",
        "message": f"成功重新生成幾何圖：共 {stats['node_count']} 個節點、{stats['edge_count']} 條邊、{stats['thread_count']} 條線程。",
        "stats": stats,
    }


@router.post("/novels/{novel_id}/geometry/repair")
def repair_geometry_endpoint(
    novel_id: str,
    payload: Dict[str, Any] = Body(...),
):
    """手動觸發幾何修復操作 (SPLIT / EXPAND / INSERT / COMPRESS)。需符合 4 大重大判定條件。"""
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    operation = payload.get("operation", "")
    condition = payload.get("condition", "")
    target_nodes = payload.get("target_nodes", [])
    reason = payload.get("reason", "")
    detail = payload.get("detail", {})
    gatekeeper_context = payload.get("gatekeeper_context", {})

    result = repair_story_geometry(
        novel_id=novel_id,
        operation=operation,
        condition=condition,
        target_nodes=target_nodes,
        reason=reason,
        detail=detail,
        gatekeeper_context=gatekeeper_context,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message") or result.get("error"))

    return result


@router.patch("/novels/{novel_id}/geometry/nodes/{node_id}/semantic")
def update_node_semantic_endpoint(
    novel_id: str,
    node_id: str,
    payload: Dict[str, Any] = Body(...),
):
    """局部更新單一節點語義。"""
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    node = db.get_geometry_node(novel_id, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Geometry node {node_id} not found")

    db.update_node_semantic(novel_id, node_id, payload)
    return {"status": "success", "node_id": node_id, "updated_semantic": payload}


@router.get("/novels/{novel_id}/geometry/nodes/{node_id}/context")
def get_node_context_endpoint(novel_id: str, node_id: str):
    """取得指定節點的上下文約束與敘事義務包裹 (Layer 3 & Layer 4)。"""
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    node = db.get_geometry_node(novel_id, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Geometry node {node_id} not found")

    from backend.services.director.context_compiler import GeometryContextCompiler
    # db.get_geometry_node 回傳 dict（chapter_start/chapter_end），非物件；
    # 兼容 dict 與物件兩種形態，避免 'dict' object has no attribute 'chapter_window' 500。
    if isinstance(node, dict):
        chapter_index = int(node.get("chapter_start", 1) or 1)
    else:
        cw = getattr(node, "chapter_window", None) or (1, 1)
        chapter_index = int(cw[0] if isinstance(cw, (list, tuple)) else 1)
    pkg = GeometryContextCompiler.compile(
        novel_id=novel_id,
        chapter_index=chapter_index,
        target_node_id=node_id,
    )
    return {
        "novel_id": pkg.novel_id,
        "chapter_index": pkg.chapter_index,
        "target_node_id": pkg.target_node_id,
        "has_geometry": pkg.has_geometry,
        "structural_role": pkg.structural_role,
        "role_obligation": pkg.role_obligation,
        "incoming_edges_summary": pkg.incoming_edges_summary,
        "outgoing_obligations": pkg.outgoing_obligations,
        "cross_context_threads": pkg.cross_context_threads,
        "echo_contrast_context": pkg.echo_contrast_context,
        "geometry_overlay_text": pkg.format_geometry_overlay(),
        "cross_context_text": pkg.format_cross_context(),
    }
