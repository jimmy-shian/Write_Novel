# -*- coding: utf-8 -*-
"""
幾何生成器任務處理器 (Geometry Generation Handler)

純程式碼執行的 Pipeline 階段處理器（完全零 LLM 消耗）：
1. 讀取小說基本設定與題材預設 (Genre Presets)
2. 組合出最適合該小說體量的 GeometryParams
3. 調用 GeometryGenerator 一次性生成全書敘事幾何骨架
4. 持久化至 SQLite (geometry_nodes, geometry_edges, geometry_threads 等)
5. 串流回傳生成進度與最終幾何統計數據
"""

from __future__ import annotations

import json
from typing import Any, Dict, Generator

from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import GeometryComplexity, GeometryParams
from backend.generation.routing.schema import GenerationTaskRequest
from backend.schemas.genre_presets import get_genre_preset


def _sse(obj: Dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def run_geometry_task(task: GenerationTaskRequest, context: Any = None) -> Generator[str, None, None]:
    """
    執行幾何圖生成任務。
    以 Generator 形式輸出 SSE 事件，相容 router 與 post_processor。
    """
    novel_id = task.novel_id

    # 1. 發送開始思考事件
    yield _sse({"type": "thinking", "delta": "正在初始化程式化敘事幾何生成器 (Geometry Generator)...\n"})

    # 2. 獲取小說設定與題材配置
    novel = db.get_novel(novel_id)
    genre = (novel.get("genre") or "general_fiction") if novel else "general_fiction"
    preset = get_genre_preset(genre)
    g_preset_params = preset.get("geometry_params", {})

    # 3. 解析目標章數與卷數
    volumes = db.get_volumes(novel_id)
    if volumes:
        volume_count = len(volumes)
        chapters_per_vol = int(volumes[0].get("chapter_count") or 50)
        target_chapters = sum(int(v.get("chapter_count") or 50) for v in volumes)
    else:
        # 從 genre preset 或預設值推導
        vol_range = preset.get("target_volume_count_range", (8, 16))
        ch_per_vol_range = preset.get("target_chapters_per_volume", (35, 50))
        volume_count = vol_range[0]
        chapters_per_vol = ch_per_vol_range[1]
        target_chapters = volume_count * chapters_per_vol

    # 支援透過 task.options 或 instruction 覆寫參數
    complexity_str = g_preset_params.get("complexity", "DENSE")
    try:
        complexity = GeometryComplexity(complexity_str)
    except ValueError:
        complexity = GeometryComplexity.DENSE

    yield _sse({"type": "thinking", "delta": f"題材 [{genre}] 幾何參數配置就緒：目標章數 {target_chapters} 章，卷數 {volume_count} 卷，複雜度 {complexity.value}...\n"})

    params = GeometryParams(
        target_chapters=target_chapters,
        volume_count=volume_count,
        chapters_per_volume=chapters_per_vol,
        complexity=complexity,
        main_thread_count=g_preset_params.get("main_thread_count", 4),
        subplot_count=g_preset_params.get("subplot_count", 12),
        character_arc_count=g_preset_params.get("character_arc_count", 8),
        relationship_arc_count=g_preset_params.get("relationship_arc_count", 6),
        thematic_thread_count=g_preset_params.get("thematic_thread_count", 4),
        cross_thread_ratio=g_preset_params.get("cross_thread_ratio", 0.5),
        long_distance_chain_count=g_preset_params.get("long_distance_chain_count", 15),
        convergence_point_count=g_preset_params.get("convergence_point_count", 8),
        contrast_pair_count=g_preset_params.get("contrast_pair_count", 6),
        seed_for_rng=f"novel_geom_{novel_id}",
    )

    # 4. 執行全書幾何圖譜一次性生成
    yield _sse({"type": "thinking", "delta": "正在執行 Narrative Geometry Motif 拓撲編織 (A:長距回收, B:分岔合流, C:線程交織, D:多源匯聚, E:情節耦合, F:長距對比)...\n"})

    generator = GeometryGenerator(params)
    graph = generator.generate()

    yield _sse({"type": "thinking", "delta": f"幾何拓撲建立成功：產生 {len(graph.nodes)} 個敘事節點、{len(graph.edges)} 條結構邊、{len(graph.threads)} 條敘事線程。正在保存至資料庫...\n"})

    # 5. 持久化至資料庫
    db.save_geometry_graph(novel_id, graph)
    stats = db.get_geometry_stats(novel_id)

    # 6. 組裝完成 Payload
    result_payload = {
        "status": "success",
        "stage": "geometry",
        "novel_id": novel_id,
        "target_chapters": target_chapters,
        "volume_count": volume_count,
        "stats": stats,
        "summary": (
            f"成功完成敘事幾何圖生成：共 {stats['node_count']} 個骨架節點，"
            f"{stats['edge_count']} 條跨距 Motif 邊，{stats['thread_count']} 條敘事線程。"
            f"所有節點已建立空間拓撲與結構角色 (semantic=None)，等待後續語義填充 (Semantic Filling)。"
        ),
    }

    result_json = json.dumps(result_payload, ensure_ascii=False, indent=2)

    # 7. 輸出最終內容與完成標記
    yield _sse({"type": "content", "delta": result_json})
    yield "data: [DONE]\n\n"
