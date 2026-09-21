# -*- coding: utf-8 -*-
"""
幾何圖譜 (Geometry Graph) 的持久層模組。
提供對 geometry_nodes, geometry_edges, geometry_threads, geometry_volumes, geometry_arcs 以及 geometry_metadata 的完整 CRUD 與修復操作。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

from backend.geometry.models import (
    ArcContainer,
    EdgeType,
    GeometryComplexity,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    GeometryThread,
    NodeHierarchy,
    RepairOperation,
    RepairProposal,
    SequenceContainer,
    StructuralRole,
    ThreadType,
    VolumeContainer,
)
from backend.persistence.connection import get_db_connection


def save_geometry_graph(novel_id: str, graph: Union[GeometryGraph, Dict[str, Any]]) -> None:
    """
    將完整的 GeometryGraph 保存至資料庫。
    每次保存皆原子性全量取代該小說先前的幾何圖數據。
    """
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()

        # 1. 清理該小說舊幾何數據
        cursor.execute("DELETE FROM geometry_nodes WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_edges WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_threads WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_volumes WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_arcs WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_metadata WHERE novel_id = ?", (novel_id,))

        # 2. 保存 Params / Metadata
        params_dict = {}
        if hasattr(graph, "params") and graph.params is not None:
            params_dict = asdict(graph.params)
        elif isinstance(graph, dict) and "params" in graph:
            params_dict = graph["params"]

        cursor.execute(
            "INSERT OR REPLACE INTO geometry_metadata (novel_id, params_json) VALUES (?, ?)",
            (novel_id, json.dumps(params_dict, ensure_ascii=False)),
        )

        # 3. 保存 Nodes
        nodes_iterable = []
        if hasattr(graph, "nodes"):
            nodes_iterable = list(graph.nodes.values()) if isinstance(graph.nodes, dict) else graph.nodes
        elif isinstance(graph, dict) and "nodes" in graph:
            n_val = graph["nodes"]
            nodes_iterable = list(n_val.values()) if isinstance(n_val, dict) else n_val

        nodes_data = []
        for n in nodes_iterable:
            if isinstance(n, GeometryNode):
                h = n.hierarchy
                nodes_data.append((
                    n.node_id,
                    novel_id,
                    h.volume_index if h else 1,
                    h.arc_index if h else 1,
                    h.sequence_index if h else 1,
                    n.chapter_window[0] if n.chapter_window else 1,
                    n.chapter_window[1] if n.chapter_window else 1,
                    n.structural_role.value if hasattr(n.structural_role, "value") else str(n.structural_role),
                    n.primary_thread,
                    n.importance,
                    json.dumps(n.semantic, ensure_ascii=False) if n.semantic is not None else None,
                    json.dumps(n.metadata, ensure_ascii=False) if n.metadata else None,
                ))
            elif isinstance(n, dict):
                h = n.get("hierarchy", {}) or {}
                cw = n.get("chapter_window", (1, 1)) or (1, 1)
                s_role = n.get("structural_role", "")
                nodes_data.append((
                    n.get("node_id"),
                    novel_id,
                    h.get("volume_index", n.get("volume_index", 1)),
                    h.get("arc_index", n.get("arc_index", 1)),
                    h.get("sequence_index", n.get("sequence_index", 1)),
                    cw[0] if isinstance(cw, (list, tuple)) and len(cw) > 0 else n.get("chapter_start", 1),
                    cw[1] if isinstance(cw, (list, tuple)) and len(cw) > 1 else n.get("chapter_end", 1),
                    s_role.value if hasattr(s_role, "value") else str(s_role),
                    n.get("primary_thread"),
                    n.get("importance", 0.5),
                    json.dumps(n.get("semantic"), ensure_ascii=False) if n.get("semantic") is not None else None,
                    json.dumps(n.get("metadata"), ensure_ascii=False) if n.get("metadata") else None,
                ))

        if nodes_data:
            cursor.executemany(
                """
                INSERT INTO geometry_nodes (
                    node_id, novel_id, volume_index, arc_index, sequence_index,
                    chapter_start, chapter_end, structural_role, primary_thread,
                    importance, semantic_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                nodes_data,
            )

        # 4. 保存 Edges
        edges_iterable = []
        if hasattr(graph, "edges"):
            edges_iterable = graph.edges
        elif isinstance(graph, dict) and "edges" in graph:
            edges_iterable = graph["edges"]

        edges_data = []
        for e in edges_iterable:
            if isinstance(e, GeometryEdge):
                e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
                edges_data.append((
                    e.edge_id,
                    novel_id,
                    e.source,
                    e.target,
                    e_type,
                    e.distance,
                    json.dumps(e.semantic, ensure_ascii=False) if e.semantic is not None else None,
                    json.dumps(e.metadata, ensure_ascii=False) if e.metadata else None,
                ))
            elif isinstance(e, dict):
                e_type = e.get("edge_type", "")
                edges_data.append((
                    e.get("edge_id"),
                    novel_id,
                    e.get("source") or e.get("source_node"),
                    e.get("target") or e.get("target_node"),
                    e_type.value if hasattr(e_type, "value") else str(e_type),
                    e.get("distance", 0),
                    json.dumps(e.get("semantic"), ensure_ascii=False) if e.get("semantic") is not None else None,
                    json.dumps(e.get("metadata"), ensure_ascii=False) if e.get("metadata") else None,
                ))

        if edges_data:
            cursor.executemany(
                """
                INSERT INTO geometry_edges (
                    edge_id, novel_id, source_node, target_node, edge_type,
                    distance, semantic_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                edges_data,
            )

        # 5. 保存 Threads
        threads_iterable = []
        if hasattr(graph, "threads"):
            threads_iterable = list(graph.threads.values()) if isinstance(graph.threads, dict) else graph.threads
        elif isinstance(graph, dict) and "threads" in graph:
            t_val = graph["threads"]
            threads_iterable = list(t_val.values()) if isinstance(t_val, dict) else t_val

        threads_data = []
        for t in threads_iterable:
            if isinstance(t, GeometryThread):
                t_type = t.thread_type.value if hasattr(t.thread_type, "value") else str(t.thread_type)
                skeleton_repr = [r.value if hasattr(r, "value") else str(r) for r in t.structural_skeleton]
                threads_data.append((
                    t.thread_id,
                    novel_id,
                    t_type,
                    json.dumps(t.node_sequence, ensure_ascii=False),
                    json.dumps(skeleton_repr, ensure_ascii=False),
                    json.dumps(t.semantic, ensure_ascii=False) if t.semantic is not None else None,
                    json.dumps(t.metadata, ensure_ascii=False) if t.metadata else None,
                ))
            elif isinstance(t, dict):
                t_type = t.get("thread_type", "")
                threads_data.append((
                    t.get("thread_id"),
                    novel_id,
                    t_type.value if hasattr(t_type, "value") else str(t_type),
                    json.dumps(t.get("node_sequence", []), ensure_ascii=False),
                    json.dumps(t.get("structural_skeleton", []), ensure_ascii=False),
                    json.dumps(t.get("semantic"), ensure_ascii=False) if t.get("semantic") is not None else None,
                    json.dumps(t.get("metadata"), ensure_ascii=False) if t.get("metadata") else None,
                ))

        if threads_data:
            cursor.executemany(
                """
                INSERT INTO geometry_threads (
                    thread_id, novel_id, thread_type, node_sequence_json,
                    structural_skeleton_json, semantic_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                threads_data,
            )

        # 6. 保存 Volumes (Containers)
        vols_iterable = []
        if hasattr(graph, "volumes"):
            vols_iterable = list(graph.volumes.values()) if isinstance(graph.volumes, dict) else graph.volumes
        elif isinstance(graph, dict) and "volumes" in graph:
            v_val = graph["volumes"]
            vols_iterable = list(v_val.values()) if isinstance(v_val, dict) else v_val

        vols_data = []
        for v in vols_iterable:
            if isinstance(v, VolumeContainer):
                vols_data.append((
                    v.volume_id,
                    novel_id,
                    v.volume_index,
                    v.chapter_range[0] if v.chapter_range else 1,
                    v.chapter_range[1] if v.chapter_range else 1,
                    json.dumps(v.arc_ids, ensure_ascii=False),
                    json.dumps(v.semantic, ensure_ascii=False) if v.semantic is not None else None,
                ))
            elif isinstance(v, dict):
                cr = v.get("chapter_range", (1, 1)) or (1, 1)
                vols_data.append((
                    v.get("volume_id"),
                    novel_id,
                    v.get("volume_index", 1),
                    cr[0] if isinstance(cr, (list, tuple)) and len(cr) > 0 else v.get("chapter_start", 1),
                    cr[1] if isinstance(cr, (list, tuple)) and len(cr) > 1 else v.get("chapter_end", 1),
                    json.dumps(v.get("arc_ids", []), ensure_ascii=False),
                    json.dumps(v.get("semantic"), ensure_ascii=False) if v.get("semantic") is not None else None,
                ))

        if vols_data:
            cursor.executemany(
                """
                INSERT INTO geometry_volumes (
                    volume_id, novel_id, volume_index, chapter_start,
                    chapter_end, arc_ids_json, semantic_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                vols_data,
            )

        # 7. 保存 Arcs (Containers)
        arcs_iterable = []
        if hasattr(graph, "arcs"):
            arcs_iterable = list(graph.arcs.values()) if isinstance(graph.arcs, dict) else graph.arcs
        elif isinstance(graph, dict) and "arcs" in graph:
            a_val = graph["arcs"]
            arcs_iterable = list(a_val.values()) if isinstance(a_val, dict) else a_val

        arcs_data = []
        for a in arcs_iterable:
            if isinstance(a, ArcContainer):
                arcs_data.append((
                    a.arc_id,
                    novel_id,
                    a.volume_index,
                    a.arc_index,
                    a.chapter_range[0] if a.chapter_range else 1,
                    a.chapter_range[1] if a.chapter_range else 1,
                    json.dumps(a.thread_ids, ensure_ascii=False),
                    json.dumps(a.semantic, ensure_ascii=False) if a.semantic is not None else None,
                ))
            elif isinstance(a, dict):
                cr = a.get("chapter_range", (1, 1)) or (1, 1)
                arcs_data.append((
                    a.get("arc_id"),
                    novel_id,
                    a.get("volume_index", 1),
                    a.get("arc_index", 1),
                    cr[0] if isinstance(cr, (list, tuple)) and len(cr) > 0 else a.get("chapter_start", 1),
                    cr[1] if isinstance(cr, (list, tuple)) and len(cr) > 1 else a.get("chapter_end", 1),
                    json.dumps(a.get("thread_ids", []), ensure_ascii=False),
                    json.dumps(a.get("semantic"), ensure_ascii=False) if a.get("semantic") is not None else None,
                ))

        if arcs_data:
            cursor.executemany(
                """
                INSERT INTO geometry_arcs (
                    arc_id, novel_id, volume_index, arc_index, chapter_start,
                    chapter_end, thread_ids_json, semantic_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                arcs_data,
            )


def load_geometry_graph(novel_id: str) -> Optional[GeometryGraph]:
    """
    從資料庫讀取完整的 GeometryGraph 實例。
    若該小說尚無幾何圖數據，回傳 None。
    """
    if not has_geometry(novel_id):
        return None

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 讀取 Metadata / Params
    meta_row = cursor.execute("SELECT params_json FROM geometry_metadata WHERE novel_id = ?", (novel_id,)).fetchone()
    params_dict = json.loads(meta_row["params_json"]) if meta_row and meta_row["params_json"] else {}
    if "complexity" in params_dict and isinstance(params_dict["complexity"], str):
        try:
            params_dict["complexity"] = GeometryComplexity(params_dict["complexity"])
        except ValueError:
            params_dict["complexity"] = GeometryComplexity.DENSE

    if "target_chapters" not in params_dict:
        params_dict["target_chapters"] = 800
    if "volume_count" not in params_dict:
        params_dict["volume_count"] = 16

    params = GeometryParams(**params_dict)
    graph = GeometryGraph(params)

    # 2. 讀取 Nodes
    node_rows = cursor.execute(
        "SELECT * FROM geometry_nodes WHERE novel_id = ? ORDER BY chapter_start ASC, node_id ASC",
        (novel_id,),
    ).fetchall()

    for r in node_rows:
        d = dict(r)
        semantic = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        metadata = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}

        try:
            s_role = StructuralRole(d["structural_role"])
        except ValueError:
            s_role = StructuralRole.DEVELOP

        hierarchy = NodeHierarchy(
            volume_index=d.get("volume_index", 1),
            arc_index=d.get("arc_index", 1),
            sequence_index=d.get("sequence_index", 1),
        )

        node = GeometryNode(
            node_id=d["node_id"],
            hierarchy=hierarchy,
            chapter_window=(d.get("chapter_start", 1), d.get("chapter_end", 1)),
            structural_role=s_role,
            primary_thread=d.get("primary_thread") or "",
            importance=float(d.get("importance") or 0.5),
            semantic=semantic,
            metadata=metadata,
        )
        graph.add_node(node)

    # 3. 讀取 Edges
    edge_rows = cursor.execute("SELECT * FROM geometry_edges WHERE novel_id = ?", (novel_id,)).fetchall()
    for r in edge_rows:
        d = dict(r)
        semantic = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        metadata = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}

        try:
            e_type = EdgeType(d["edge_type"])
        except ValueError:
            e_type = EdgeType.CAUSES

        edge = GeometryEdge(
            edge_id=d["edge_id"],
            source=d["source_node"],
            target=d["target_node"],
            edge_type=e_type,
            distance=int(d.get("distance") or 0),
            semantic=semantic,
            metadata=metadata,
        )
        graph.add_edge(edge)

    # 4. 讀取 Threads
    thread_rows = cursor.execute("SELECT * FROM geometry_threads WHERE novel_id = ?", (novel_id,)).fetchall()
    for r in thread_rows:
        d = dict(r)
        semantic = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        metadata = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        node_seq = json.loads(d["node_sequence_json"]) if d.get("node_sequence_json") else []
        skeleton_raw = json.loads(d["structural_skeleton_json"]) if d.get("structural_skeleton_json") else []

        try:
            t_type = ThreadType(d["thread_type"])
        except ValueError:
            t_type = ThreadType.MAIN

        skeleton: List[StructuralRole] = []
        for r_name in skeleton_raw:
            try:
                skeleton.append(StructuralRole(r_name))
            except ValueError:
                skeleton.append(StructuralRole.DEVELOP)

        thread = GeometryThread(
            thread_id=d["thread_id"],
            thread_type=t_type,
            node_sequence=node_seq,
            structural_skeleton=skeleton,
            semantic=semantic,
            metadata=metadata,
        )
        graph.add_thread(thread)

    # 5. 讀取 Volumes
    vol_rows = cursor.execute("SELECT * FROM geometry_volumes WHERE novel_id = ?", (novel_id,)).fetchall()
    for r in vol_rows:
        d = dict(r)
        arc_ids = json.loads(d["arc_ids_json"]) if d.get("arc_ids_json") else []
        semantic = json.loads(d["semantic_json"]) if d.get("semantic_json") else None

        vol = VolumeContainer(
            volume_id=d["volume_id"],
            volume_index=d.get("volume_index", 1),
            chapter_range=(d.get("chapter_start", 1), d.get("chapter_end", 1)),
            arc_ids=arc_ids,
            semantic=semantic,
        )
        graph.add_volume(vol)

    # 6. 讀取 Arcs
    arc_rows = cursor.execute("SELECT * FROM geometry_arcs WHERE novel_id = ?", (novel_id,)).fetchall()
    for r in arc_rows:
        d = dict(r)
        thread_ids = json.loads(d["thread_ids_json"]) if d.get("thread_ids_json") else []
        semantic = json.loads(d["semantic_json"]) if d.get("semantic_json") else None

        arc = ArcContainer(
            arc_id=d["arc_id"],
            volume_index=d.get("volume_index", 1),
            arc_index=d.get("arc_index", 1),
            chapter_range=(d.get("chapter_start", 1), d.get("chapter_end", 1)),
            thread_ids=thread_ids,
            semantic=semantic,
        )
        graph.add_arc(arc)

    return graph


def get_geometry_node(novel_id: str, node_id: str) -> Optional[dict]:
    """獲取單個幾何節點資訊。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM geometry_nodes WHERE novel_id = ? AND node_id = ?", (novel_id, node_id)).fetchone()
    if row:
        d = dict(row)
        d["semantic"] = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        return d
    return None


def get_geometry_edges_for_node(novel_id: str, node_id: str, direction: str = "both") -> List[dict]:
    """獲取與節點相連的邊。direction 可為 'incoming', 'outgoing', 或 'both'。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM geometry_edges WHERE novel_id = ?"
    params = [novel_id]

    if direction == "outgoing":
        query += " AND source_node = ?"
        params.append(node_id)
    elif direction == "incoming":
        query += " AND target_node = ?"
        params.append(node_id)
    else:
        query += " AND (source_node = ? OR target_node = ?)"
        params.extend([node_id, node_id])

    rows = cursor.execute(query, params).fetchall()
    edges = []
    for r in rows:
        d = dict(r)
        d["semantic"] = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        edges.append(d)
    return edges


def get_geometry_thread(novel_id: str, thread_id: str) -> Optional[dict]:
    """獲取單條線索。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM geometry_threads WHERE novel_id = ? AND thread_id = ?", (novel_id, thread_id)).fetchone()
    if row:
        d = dict(row)
        d["node_sequence"] = json.loads(d["node_sequence_json"]) if d.get("node_sequence_json") else []
        d["structural_skeleton"] = json.loads(d["structural_skeleton_json"]) if d.get("structural_skeleton_json") else []
        d["semantic"] = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        return d
    return None


def get_geometry_nodes_in_range(novel_id: str, chapter_start: int, chapter_end: int) -> List[dict]:
    """獲取章節區間有交集的所有節點。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT * FROM geometry_nodes
        WHERE novel_id = ?
          AND chapter_start <= ?
          AND chapter_end >= ?
        ORDER BY chapter_start ASC, node_id ASC
    """
    rows = cursor.execute(query, (novel_id, chapter_end, chapter_start)).fetchall()

    nodes = []
    for r in rows:
        d = dict(r)
        d["semantic"] = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
        d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        nodes.append(d)
    return nodes


def update_node_semantic(novel_id: str, node_id: str, semantic: dict) -> None:
    """更新節點的語義內容。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE geometry_nodes SET semantic_json = ? WHERE novel_id = ? AND node_id = ?",
            (json.dumps(semantic, ensure_ascii=False), novel_id, node_id),
        )


def update_thread_semantic(novel_id: str, thread_id: str, semantic: dict) -> None:
    """更新線索的語義內容。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE geometry_threads SET semantic_json = ? WHERE novel_id = ? AND thread_id = ?",
            (json.dumps(semantic, ensure_ascii=False), novel_id, thread_id),
        )


def update_edge_semantic(novel_id: str, edge_id: str, semantic: dict) -> None:
    """更新邊的語義內容。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE geometry_edges SET semantic_json = ? WHERE novel_id = ? AND edge_id = ?",
            (json.dumps(semantic, ensure_ascii=False), novel_id, edge_id),
        )


def update_volume_semantic(novel_id: str, volume_id: str, semantic: dict) -> None:
    """更新篇卷容器的語義內容。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE geometry_volumes SET semantic_json = ? WHERE novel_id = ? AND volume_id = ?",
            (json.dumps(semantic, ensure_ascii=False), novel_id, volume_id),
        )


def get_geometry_stats(novel_id: str) -> dict:
    """回傳幾何圖統計與語義填充進度。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    node_count = cursor.execute("SELECT COUNT(*) FROM geometry_nodes WHERE novel_id = ?", (novel_id,)).fetchone()[0]
    edge_count = cursor.execute("SELECT COUNT(*) FROM geometry_edges WHERE novel_id = ?", (novel_id,)).fetchone()[0]
    thread_count = cursor.execute("SELECT COUNT(*) FROM geometry_threads WHERE novel_id = ?", (novel_id,)).fetchone()[0]

    filled_nodes = cursor.execute(
        "SELECT COUNT(*) FROM geometry_nodes WHERE novel_id = ? AND semantic_json IS NOT NULL AND semantic_json != '{}' AND semantic_json != 'null'",
        (novel_id,),
    ).fetchone()[0]

    filled_threads = cursor.execute(
        "SELECT COUNT(*) FROM geometry_threads WHERE novel_id = ? AND semantic_json IS NOT NULL AND semantic_json != '{}' AND semantic_json != 'null'",
        (novel_id,),
    ).fetchone()[0]

    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "thread_count": thread_count,
        "filled_nodes": filled_nodes,
        "unfilled_nodes": node_count - filled_nodes,
        "filled_threads": filled_threads,
        "unfilled_threads": thread_count - filled_threads,
        "filling_progress": round(filled_nodes / node_count, 3) if node_count > 0 else 0.0,
    }


def has_geometry(novel_id: str) -> bool:
    """檢查指定小說是否存在幾何圖數據。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    count = cursor.execute("SELECT COUNT(*) FROM geometry_nodes WHERE novel_id = ?", (novel_id,)).fetchone()[0]
    return count > 0


def delete_geometry(novel_id: str) -> None:
    """刪除指定小說的所有幾何圖數據。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM geometry_nodes WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_edges WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_threads WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_volumes WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_arcs WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_metadata WHERE novel_id = ?", (novel_id,))


def apply_repair(
    novel_id: str,
    proposal: RepairProposal,
    condition: Any,
    gatekeeper_context: dict,
) -> Any:
    """
    執行幾何結構修復操作 (SPLIT / EXPAND / INSERT / COMPRESS)。
    1. 載入當前幾何圖
    2. 通過門禁條件檢驗並執行拓撲變更
    3. 若修復成功，將重構後的圖譜覆寫回資料庫
    """
    from backend.geometry.repair import GeometryRepairEngine

    graph = load_geometry_graph(novel_id)
    if not graph:
        from backend.geometry.repair import GeometryRepairResult
        return GeometryRepairResult(
            success=False,
            operation=proposal.operation,
            condition=condition,
            message="該作品尚未生成幾何圖，無法執行修復",
        )

    engine = GeometryRepairEngine(graph)
    result = engine.execute_repair(proposal, condition, gatekeeper_context)

    if result.success:
        save_geometry_graph(novel_id, graph)

    return result
