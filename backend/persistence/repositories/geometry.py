# -*- coding: utf-8 -*-
"""
幾何圖譜 (Geometry Graph) 的持久層模組（單一真相來源：MASTER_GRAPH_*）。
本模組函式為相容層：節點/邊讀寫一律轉發 MASTER，舊 geometry_nodes /
geometry_edges 僅在晉升遷移時讀取，遷完即刪。線程/卷/弧/元數據為共用表。
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
    將完整的 GeometryGraph 保存至資料庫（單一真相來源：MASTER_GRAPH_*）。
    舊 geometry_nodes / geometry_edges 已退役；本函式僅為相容層，直接轉發。
    每次保存皆原子性全量取代該小說先前的圖數據。
    """
    from backend.persistence.repositories import master_graph_repository as _mgr
    _mgr.save_master_graph(novel_id, graph)
    return


def _legacy_tables_exist() -> bool:
    """舊 geometry_nodes / geometry_edges 是否尚存（過渡期相容）。"""
    try:
        conn = get_db_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        return "geometry_nodes" in tables and "geometry_edges" in tables
    except Exception:
        return False


def _delete_legacy_geometry_rows(novel_id: str) -> None:
    """刪除該書舊表殘留行（晉升遷移後清理）。"""
    if not _legacy_tables_exist():
        return
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM geometry_nodes WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM geometry_edges WHERE novel_id = ?", (novel_id,))


def _drop_legacy_tables_if_empty() -> None:
    """舊表皆空時物理刪除（單存儲收尾）；非空則保留待下次晉升，不丟資料。"""
    if not _legacy_tables_exist():
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        n = cur.execute("SELECT COUNT(*) FROM geometry_nodes").fetchone()[0]
        e = cur.execute("SELECT COUNT(*) FROM geometry_edges").fetchone()[0]
        if n == 0 and e == 0:
            with conn:
                conn.execute("DROP TABLE IF EXISTS geometry_nodes")
                conn.execute("DROP TABLE IF EXISTS geometry_edges")
    except Exception as _exc:
        print(f"[WARN] drop legacy geometry tables skipped: {_exc}")


def load_geometry_graph(novel_id: str) -> Optional[GeometryGraph]:
    """
    從資料庫讀取完整的 GeometryGraph 實例（單一真相來源：MASTER_GRAPH_*）。
    舊表僅有資料而 MASTER 缺失時，晉升遷移至 MASTER 後回傳。
    若該小說尚無幾何圖數據，回傳 None。
    """
    from backend.persistence.repositories import master_graph_repository as _mgr
    try:
        if _mgr.has_master_graph(novel_id):
            _g = _mgr.load_master_graph(novel_id)
            if _g is not None and getattr(_g, "nodes", None):
                return _g
    except Exception:
        pass
    _legacy = _load_legacy_geometry_graph(novel_id)
    if _legacy is not None and getattr(_legacy, "nodes", None):
        try:
            _mgr.save_master_graph(novel_id, _legacy)
            _delete_legacy_geometry_rows(novel_id)
            _drop_legacy_tables_if_empty()
        except Exception as _exc:
            print(f"[WARN] promote legacy geometry failed: {_exc}")
        try:
            _promoted = _mgr.load_master_graph(novel_id)
            if _promoted is not None and getattr(_promoted, "nodes", None):
                return _promoted
        except Exception:
            pass
        return _legacy
    return None


def _load_legacy_geometry_graph(novel_id: str) -> Optional[GeometryGraph]:
    """
    讀取舊 geometry_* 表（退役中，僅供晉升遷移）。
    若該小說尚無幾何圖數據，回傳 None。
    """
    if not _legacy_tables_exist():
        return None
    if not has_geometry(novel_id):
        return None

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 讀取 Metadata / Params
    meta_row = cursor.execute("SELECT params_json FROM geometry_metadata WHERE novel_id = ?", (novel_id,)).fetchone()
    raw_meta = json.loads(meta_row["params_json"]) if meta_row and meta_row["params_json"] else {}
    graph_revision = 1
    if isinstance(raw_meta, dict):
        graph_revision = int(raw_meta.pop("_graph_revision", raw_meta.pop("graph_revision", 1)))
        params_dict = raw_meta
    else:
        params_dict = {}

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
    graph.graph_revision = graph_revision

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


def _node_to_dict(novel_id: str, n) -> dict:
    """GeometryNode 轉舊相容 dict（含新舊兩套鍵）。"""
    h = getattr(n, "hierarchy", None)
    cw = getattr(n, "chapter_window", None) or (1, 1)
    s_role = getattr(n, "structural_role", "")
    return {
        "node_id": getattr(n, "node_id", ""),
        "novel_id": novel_id,
        "volume_index": h.volume_index if h else 1,
        "arc_index": h.arc_index if h else 1,
        "sequence_index": h.sequence_index if h else 1,
        "chapter_start": cw[0],
        "chapter_end": cw[1],
        "chapter_window": [cw[0], cw[1]],
        "structural_role": s_role.value if hasattr(s_role, "value") else str(s_role),
        "primary_thread": getattr(n, "primary_thread", "") or "",
        "importance": getattr(n, "importance", 0.5),
        "semantic": getattr(n, "semantic", None),
        "metadata": getattr(n, "metadata", None) or {},
        "thread_memberships": list(getattr(n, "thread_memberships", None) or []),
    }


def _edge_to_dict(novel_id: str, e) -> dict:
    """GeometryEdge 轉舊相容 dict（含新舊兩套鍵）。"""
    e_type = getattr(e, "edge_type", "")
    return {
        "edge_id": getattr(e, "edge_id", ""),
        "novel_id": novel_id,
        "source_node": getattr(e, "source", ""),
        "target_node": getattr(e, "target", ""),
        "source": getattr(e, "source", ""),
        "target": getattr(e, "target", ""),
        "edge_type": e_type.value if hasattr(e_type, "value") else str(e_type),
        "distance": getattr(e, "distance", 0) or 0,
        "semantic": getattr(e, "semantic", None),
        "metadata": getattr(e, "metadata", None) or {},
    }


def get_geometry_node(novel_id: str, node_id: str) -> Optional[dict]:
    """獲取單個幾何節點資訊（讀 MASTER）。"""
    graph = load_geometry_graph(novel_id)
    if not graph:
        return None
    node = graph.nodes.get(node_id) if isinstance(graph.nodes, dict) else None
    if node is None:
        return None
    return _node_to_dict(novel_id, node)


def get_geometry_edges_for_node(novel_id: str, node_id: str, direction: str = "both") -> List[dict]:
    """獲取與節點相連的邊（讀 MASTER）。direction 可為 'incoming', 'outgoing', 或 'both'。"""
    graph = load_geometry_graph(novel_id)
    if not graph:
        return []
    edges = []
    for e in graph.edges or []:
        src = getattr(e, "source", "")
        tgt = getattr(e, "target", "")
        if direction == "outgoing" and src != node_id:
            continue
        if direction == "incoming" and tgt != node_id:
            continue
        if direction not in ("outgoing", "incoming") and src != node_id and tgt != node_id:
            continue
        edges.append(_edge_to_dict(novel_id, e))
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
    """獲取章節區間有交集的所有節點（讀 MASTER）。"""
    graph = load_geometry_graph(novel_id)
    if not graph:
        return []
    nodes = []
    for n in (graph.nodes.values() if isinstance(graph.nodes, dict) else []):
        cw = getattr(n, "chapter_window", None) or (1, 1)
        if cw[0] <= chapter_end and cw[1] >= chapter_start:
            nodes.append(_node_to_dict(novel_id, n))
    nodes.sort(key=lambda d: (d["chapter_start"], d["node_id"]))
    return nodes


def update_node_semantic(novel_id: str, node_id: str, semantic: dict) -> None:
    """更新節點的語義內容（寫 MASTER：併入契約 worldview_slot）。"""
    from backend.persistence.repositories import master_graph_repository as _mgr
    graph = _mgr.load_master_graph(novel_id)
    if not graph:
        return
    node = graph.nodes.get(node_id) if isinstance(graph.nodes, dict) else None
    if node is None:
        return
    contract = node.ensure_story_contract() if hasattr(node, "ensure_story_contract") else None
    if contract is not None:
        slot = getattr(contract, "worldview_slot", None)
        merged = dict(slot) if isinstance(slot, dict) else {}
        if isinstance(semantic, dict):
            merged.update(semantic)
        else:
            merged["value"] = semantic
        contract.worldview_slot = merged
    try:
        node.semantic = dict(getattr(node, "semantic", None) or {})
        if isinstance(semantic, dict):
            node.semantic.update(semantic)
    except Exception:
        pass
    _mgr.save_master_graph(novel_id, graph)


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
    """更新邊的語義內容（寫 MASTER，語義隨 metadata 攜帶）。"""
    from backend.persistence.repositories import master_graph_repository as _mgr
    graph = _mgr.load_master_graph(novel_id)
    if not graph:
        return
    updated = False
    for e in graph.edges or []:
        if getattr(e, "edge_id", None) == edge_id:
            e.semantic = semantic
            updated = True
            break
    if updated:
        _mgr.save_master_graph(novel_id, graph)


def update_volume_semantic(novel_id: str, volume_id: str, semantic: dict) -> None:
    """更新篇卷容器的語義內容。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE geometry_volumes SET semantic_json = ? WHERE novel_id = ? AND volume_id = ?",
            (json.dumps(semantic, ensure_ascii=False), novel_id, volume_id),
        )


def update_arc_semantic(novel_id: str, arc_id: str, semantic: dict) -> None:
    """更新弧容器的語義內容。"""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE geometry_arcs SET semantic_json = ? WHERE novel_id = ? AND arc_id = ?",
            (json.dumps(semantic, ensure_ascii=False), novel_id, arc_id),
        )


def get_geometry_stats(novel_id: str) -> dict:
    """回傳幾何圖統計與語義填充進度（讀 MASTER）。"""
    graph = load_geometry_graph(novel_id)
    if not graph:
        return {
            "node_count": 0, "edge_count": 0, "thread_count": 0,
            "filled_nodes": 0, "unfilled_nodes": 0,
            "filled_threads": 0, "unfilled_threads": 0,
            "filled_edges": 0, "filled_volumes": 0,
            "filling_progress": 0.0,
        }
    nodes = list(graph.nodes.values()) if isinstance(graph.nodes, dict) else []
    edges = list(graph.edges or [])
    threads = list(graph.threads.values()) if isinstance(graph.threads, dict) else []
    volumes = list(graph.volumes.values()) if isinstance(graph.volumes, dict) else []
    filled_nodes = sum(1 for n in nodes if getattr(n, "semantic", None))
    filled_threads = sum(1 for t in threads if getattr(t, "semantic", None))
    filled_edges = sum(1 for e in edges if getattr(e, "semantic", None))
    filled_volumes = sum(1 for v in volumes if getattr(v, "semantic", None))
    node_count = len(nodes)
    thread_count = len(threads)
    return {
        "node_count": node_count,
        "edge_count": len(edges),
        "thread_count": thread_count,
        "filled_nodes": filled_nodes,
        "unfilled_nodes": node_count - filled_nodes,
        "filled_threads": filled_threads,
        "unfilled_threads": thread_count - filled_threads,
        "filled_edges": filled_edges,
        "filled_volumes": filled_volumes,
        "filling_progress": round(filled_nodes / node_count, 3) if node_count > 0 else 0.0,
    }


def has_geometry(novel_id: str) -> bool:
    """檢查指定小說是否存在幾何圖數據（MASTER 優先，舊表殘留亦算）。"""
    from backend.persistence.repositories import master_graph_repository as _mgr
    try:
        if _mgr.has_master_graph(novel_id):
            return True
    except Exception:
        pass
    if not _legacy_tables_exist():
        return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        count = cursor.execute("SELECT COUNT(*) FROM geometry_nodes WHERE novel_id = ?", (novel_id,)).fetchone()[0]
        return count > 0
    except Exception:
        return False


def delete_geometry(novel_id: str) -> None:
    """刪除指定小說的所有幾何圖數據（MASTER 與舊表殘留一併清除）。"""
    from backend.persistence.repositories import master_graph_repository as _mgr
    try:
        _mgr.delete_master_graph(novel_id)
    except Exception as _exc:
        print(f"[WARN] delete master graph skipped: {_exc}")
    _delete_legacy_geometry_rows(novel_id)


def apply_repair(
    novel_id: str,
    proposal: RepairProposal,
    condition: Any,
    gatekeeper_context: dict,
) -> Any:
    """
    執行幾何結構修復操作 (SPLIT / EXPAND / INSERT / COMPRESS)。
    單一真相來源：只讀寫 MASTER_GRAPH_*，舊表不再寫入。
    1. 載入當前 MASTER 圖（舊表殘留會先晉升遷移）
    2. 通過門禁條件檢驗並執行拓撲變更
    3. 若修復成功，將重構後的圖譜覆寫回 MASTER
    """
    from backend.geometry.repair import GeometryRepairEngine
    from backend.persistence.repositories import master_graph_repository as _mgr

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
        _mgr.save_master_graph(novel_id, graph)

    return result
