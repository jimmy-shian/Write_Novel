# -*- coding: utf-8 -*-
"""
Formal Geometry Graph Materializer.
Transforms the Planning Blueprint and Volume Outlines into a fully materialized,
chapter-level physical Narrative Geometry Graph, ensuring atomic SQLite persistence.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import (
    GeometryGraph,
    GeometryParams,
    GeometryComplexity,
    GeometryNode,
    GeometryEdge,
    GeometryThread,
    StructuralRole,
    ThreadType,
    EdgeType,
    NodeHierarchy,
)
from backend.schemas.genre_presets import get_genre_preset


def materialize_formal_geometry(novel_id: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Constructs and persists the formal GeometryGraph for the novel.
    Guarantees that database statistics (nodes, edges, threads, volumes) become > 0.
    """
    stats = db.get_geometry_stats(novel_id) if hasattr(db, "get_geometry_stats") else {}
    if not overwrite and stats and int(stats.get("node_count") or 0) > 0 and int(stats.get("edge_count") or 0) > 0:
        return {
            "status": "ready",
            "stats": stats,
            "message": "敘事幾何拓樸圖已就緒，無須重新生成",
        }

    novel = db.get_novel(novel_id) or {}
    genre = novel.get("genre") or "general_fiction"
    preset = get_genre_preset(genre)
    g_preset_params = preset.get("geometry_params", {})

    volumes = db.get_volumes(novel_id) or []
    if volumes:
        volume_count = len(volumes)
        chapters_per_vol = int(volumes[0].get("chapter_count") or 50)
        target_chapters = sum(int(v.get("chapter_count") or chapters_per_vol) for v in volumes)
    else:
        vol_range = preset.get("target_volume_count_range", (8, 12))
        volume_count = vol_range[0]
        chapters_per_vol = preset.get("target_chapters_per_volume", (30, 50))[1]
        target_chapters = volume_count * chapters_per_vol

    complexity_str = g_preset_params.get("complexity", "DENSE")
    try:
        complexity = GeometryComplexity(complexity_str)
    except Exception:
        complexity = GeometryComplexity.DENSE

    params = GeometryParams(
        target_chapters=target_chapters,
        volume_count=volume_count,
        chapters_per_volume=chapters_per_vol,
        complexity=complexity,
        main_thread_count=int(g_preset_params.get("main_thread_count", 4)),
        subplot_count=int(g_preset_params.get("subplot_count", 12)),
        character_arc_count=int(g_preset_params.get("character_arc_count", 8)),
        relationship_arc_count=int(g_preset_params.get("relationship_arc_count", 6)),
        thematic_thread_count=int(g_preset_params.get("thematic_thread_count", 4)),
        cross_thread_ratio=float(g_preset_params.get("cross_thread_ratio", 0.5)),
        long_distance_chain_count=int(g_preset_params.get("long_distance_chain_count", 15)),
        convergence_point_count=int(g_preset_params.get("convergence_point_count", 8)),
        contrast_pair_count=int(g_preset_params.get("contrast_pair_count", 6)),
        seed_for_rng=f"formal_geom_{novel_id}",
    )

    generator = GeometryGenerator(params)
    graph = generator.generate()

    # Save to SQLite
    db.save_geometry_graph(novel_id, graph)
    updated_stats = db.get_geometry_stats(novel_id)

    return {
        "status": "success",
        "novel_id": novel_id,
        "volume_count": volume_count,
        "target_chapters": target_chapters,
        "stats": updated_stats,
        "summary": f"成功實體化敘事幾何拓樸圖：共 {updated_stats['node_count']} 個骨架節點，{updated_stats['edge_count']} 條跨距邊，{updated_stats['thread_count']} 條線程。",
    }
