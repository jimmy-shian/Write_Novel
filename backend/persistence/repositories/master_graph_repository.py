# -*- coding: utf-8 -*-
"""
Master Graph 持久化倉儲層 (Master Graph Repository Layer).

負責 Master Graph 單一真相核心 (Single Source of Truth, SSOT) 的持久化與關聯檢索：
1. MASTER_GRAPH_NODES: 節點屬性、雙軌狀態 (planning_status / realization_status)、NodeStoryContract 完整契約與版本號。
2. MASTER_GRAPH_EDGES: 因果邊 (CAUSES/ENABLES/ESCALATES) 與非因果邊 (ECHOES/PARALLELS 等) 之持久化。
3. STORY_EVENT_ENTITIES: 九維具體故事事件契約 (StoryEventContract) 之正規化儲存。
4. NODE_CHAPTER_BEATS: 節點與章節拍點的多對多映射 (chapter_index, beat_index, coverage_ratio)。
5. NODE_THREAD_MEMBERSHIPS: 節點的多線程歸屬 (thread_id, sequence_index)。
6. pipeline_task_checkpoints: 斷點續傳任務狀態機 (run_id, current_stage, graph_revision, retry_count, next_retry_at, status)。
7. chapter_draft_audits: 總監草稿違規審計追蹤 (audit_status, defects_json, audit_report_json)。

提供完整事務原子保護 (ACID Transactions) 與 GeometryGraph 雙向無損反序列化。
"""

from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from backend.geometry.models import (
    CAUSAL_EDGE_TYPES,
    NON_CAUSAL_EDGE_TYPES,
    ArcContainer,
    EdgeType,
    ForeshadowingDemand,
    GeometryComplexity,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    GeometryThread,
    MasterGraphEdgeContract,
    NodeHierarchy,
    NodeStoryContract,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    SequenceContainer,
    StoryEventContract,
    StructuralRole,
    ThreadType,
    VolumeContainer,
    is_causal_edge,
)
from backend.persistence.connection import (
    ConnectionProvider,
    get_db_connection,
    transaction,
)


class MasterGraphRepository:
    """
    Master Graph 數據庫倉儲類別。
    支援依賴注入 ConnectionProvider，並封裝完整的 CRUD、事務與反序列化邏輯。
    """

    def __init__(self, connection_provider: Optional[ConnectionProvider] = None) -> None:
        self._connection_provider = connection_provider or get_db_connection

    def _get_conn(self) -> sqlite3.Connection:
        """取得當前執行緒之資料庫連線"""
        return self._connection_provider()

    # =========================================================================
    # 1. 表結構初始化 (Table DDL Initialization)
    # =========================================================================

    def init_tables(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """
        初始化 Master Graph 所有專屬資料表與高效能覆蓋索引。
        """
        connection = conn or self._get_conn()
        cursor = connection.cursor()

        # 1. MASTER_GRAPH_NODES
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS MASTER_GRAPH_NODES (
            node_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            volume_index INTEGER NOT NULL DEFAULT 1,
            arc_index INTEGER NOT NULL DEFAULT 1,
            structural_role TEXT NOT NULL DEFAULT 'DEVELOP',
            node_type TEXT NOT NULL DEFAULT 'FACTION_COLLISION',
            foreshadowing_demand TEXT NOT NULL DEFAULT 'NONE',
            planning_status TEXT NOT NULL DEFAULT 'DRAFT',
            realization_status TEXT NOT NULL DEFAULT 'PENDING',
            graph_revision INTEGER NOT NULL DEFAULT 1,
            story_contract_json TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (novel_id, node_id),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mgn_novel_node ON MASTER_GRAPH_NODES (novel_id, node_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mgn_novel_vol ON MASTER_GRAPH_NODES (novel_id, volume_index);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mgn_novel_status ON MASTER_GRAPH_NODES (novel_id, planning_status);")

        # 2. MASTER_GRAPH_EDGES
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS MASTER_GRAPH_EDGES (
            edge_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            source_node TEXT NOT NULL,
            target_node TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            is_causal INTEGER NOT NULL DEFAULT 1,
            weight REAL DEFAULT 1.0,
            graph_revision INTEGER NOT NULL DEFAULT 1,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (novel_id, edge_id),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mge_novel_source ON MASTER_GRAPH_EDGES (novel_id, source_node);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mge_novel_target ON MASTER_GRAPH_EDGES (novel_id, target_node);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mge_novel_causal ON MASTER_GRAPH_EDGES (novel_id, is_causal);")

        # 3. STORY_EVENT_ENTITIES (9-Dimension Story Events)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS STORY_EVENT_ENTITIES (
            event_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            event_summary TEXT NOT NULL DEFAULT '',
            participant_entities_json TEXT NOT NULL DEFAULT '[]',
            action_motives_json TEXT NOT NULL DEFAULT '[]',
            causal_preconditions_json TEXT NOT NULL DEFAULT '[]',
            core_conflict TEXT NOT NULL DEFAULT '',
            direct_outcome TEXT NOT NULL DEFAULT '',
            state_mutations_json TEXT NOT NULL DEFAULT '[]',
            downstream_impact_json TEXT NOT NULL DEFAULT '[]',
            clue_bindings_json TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (novel_id, event_id),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_see_novel_node ON STORY_EVENT_ENTITIES (novel_id, node_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_see_novel_event ON STORY_EVENT_ENTITIES (novel_id, event_id);")

        # 4. NODE_CHAPTER_BEATS (Many-to-Many Beat Mapping)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS NODE_CHAPTER_BEATS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            chapter_index INTEGER NOT NULL,
            beat_index INTEGER NOT NULL DEFAULT 0,
            coverage_ratio REAL NOT NULL DEFAULT 1.0,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
            UNIQUE(novel_id, node_id, chapter_index, beat_index)
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ncb_node ON NODE_CHAPTER_BEATS (novel_id, node_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ncb_chapter ON NODE_CHAPTER_BEATS (novel_id, chapter_index);")

        # 5. NODE_THREAD_MEMBERSHIPS (Multi-Thread Memberships)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS NODE_THREAD_MEMBERSHIPS (
            node_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            sequence_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (novel_id, node_id, thread_id),
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ntm_novel_node ON NODE_THREAD_MEMBERSHIPS (novel_id, node_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ntm_novel_thread ON NODE_THREAD_MEMBERSHIPS (novel_id, thread_id, sequence_index);")

        # 6. pipeline_task_checkpoints (Resilient Task Checkpoint State Machine)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_task_checkpoints (
            run_id TEXT PRIMARY KEY,
            novel_id TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            current_node_id TEXT,
            current_chapter INTEGER DEFAULT 0,
            graph_revision INTEGER NOT NULL DEFAULT 1,
            retry_count INTEGER NOT NULL DEFAULT 0,
            next_retry_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            state_payload_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ptc_novel_status ON pipeline_task_checkpoints (novel_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ptc_next_retry ON pipeline_task_checkpoints (status, next_retry_at);")

        # 7. chapter_draft_audits (Draft Violations & Audit Ledger)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chapter_draft_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            novel_id TEXT NOT NULL,
            chapter_index INTEGER NOT NULL,
            audit_status TEXT NOT NULL,
            defects_json TEXT NOT NULL DEFAULT '[]',
            audit_report_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cda_novel_chapter ON chapter_draft_audits (novel_id, chapter_index, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cda_novel_status ON chapter_draft_audits (novel_id, audit_status);")

        connection.commit()

    # =========================================================================
    # 2. Master Graph 核心存儲 (Save Master Graph)
    # =========================================================================

    def save_master_graph(
        self,
        novel_id: str,
        graph: Union[GeometryGraph, Dict[str, Any]],
        revision: Optional[int] = None,
    ) -> None:
        """
        將完整的 Master Graph 保存至 SQLite。
        以單一原子事務 (Atomic Transaction) 覆蓋寫入該小說的全部圖節點、邊、九維事件、拍點與線程映射。
        """
        conn = self._get_conn()

        # 解析目標版本號
        target_revision = 1
        if revision is not None:
            target_revision = int(revision)
        elif hasattr(graph, "graph_revision"):
            target_revision = int(graph.graph_revision)
        elif isinstance(graph, dict) and "graph_revision" in graph:
            target_revision = int(graph["graph_revision"])

        with conn:
            cursor = conn.cursor()

            # 1. 清理該小說舊圖數據
            cursor.execute("DELETE FROM MASTER_GRAPH_NODES WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM MASTER_GRAPH_EDGES WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM STORY_EVENT_ENTITIES WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM NODE_CHAPTER_BEATS WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM NODE_THREAD_MEMBERSHIPS WHERE novel_id = ?", (novel_id,))

            # 2. 準備節點、事件、拍點、線程資料
            nodes_iterable = []
            if hasattr(graph, "nodes"):
                nodes_iterable = list(graph.nodes.values()) if isinstance(graph.nodes, dict) else graph.nodes
            elif isinstance(graph, dict) and "nodes" in graph:
                n_dict = graph["nodes"]
                nodes_iterable = list(n_dict.values()) if isinstance(n_dict, dict) else n_dict

            node_rows: List[Tuple[Any, ...]] = []
            event_rows: List[Tuple[Any, ...]] = []
            beat_rows: List[Tuple[Any, ...]] = []
            membership_rows: List[Tuple[Any, ...]] = []

            for n in nodes_iterable:
                if isinstance(n, GeometryNode):
                    contract = None
                    if hasattr(graph, "get_story_contract"):
                        contract = graph.get_story_contract(n.node_id)
                    if not contract:
                        contract = n.ensure_story_contract()

                    contract.graph_revision = target_revision
                    n.graph_revision = target_revision

                    nid = n.node_id
                    vol_idx = n.hierarchy.volume_index if n.hierarchy else 1
                    arc_idx = n.hierarchy.arc_index if n.hierarchy else 1
                    s_role = n.structural_role.value if hasattr(n.structural_role, "value") else str(n.structural_role)
                    n_type = n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type)
                    f_demand = n.foreshadowing_demand.value if hasattr(n.foreshadowing_demand, "value") else str(n.foreshadowing_demand)
                    p_status = n.planning_status.value if hasattr(n.planning_status, "value") else str(n.planning_status)
                    r_status = n.realization_status.value if hasattr(n.realization_status, "value") else str(n.realization_status)
                    contract_json = json.dumps(contract.to_dict(), ensure_ascii=False)
                    node_meta = dict(n.metadata or {})
                    if hasattr(n, "chapter_window") and n.chapter_window:
                        node_meta["_chapter_window"] = list(n.chapter_window)
                    meta_json = json.dumps(node_meta, ensure_ascii=False)

                    node_rows.append((
                        nid, novel_id, vol_idx, arc_idx, s_role, n_type, f_demand,
                        p_status, r_status, target_revision, contract_json, meta_json
                    ))

                    # 收集九維故事事件
                    for ev in contract.story_events:
                        ed = ev.to_dict() if hasattr(ev, "to_dict") else dict(ev)
                        event_rows.append((
                            ed.get("event_id", f"EV_{nid}_{uuid.uuid4().hex[:6]}"),
                            nid, novel_id,
                            ed.get("event_summary", ""),
                            json.dumps(ed.get("participant_entities", []), ensure_ascii=False),
                            json.dumps(ed.get("action_motives", []), ensure_ascii=False),
                            json.dumps(ed.get("causal_preconditions", []), ensure_ascii=False),
                            ed.get("core_conflict", ""),
                            ed.get("direct_outcome", ""),
                            json.dumps(ed.get("state_mutations", []), ensure_ascii=False),
                            json.dumps(ed.get("downstream_impact", []), ensure_ascii=False),
                            json.dumps(ed.get("clue_bindings", []), ensure_ascii=False),
                        ))

                    # 收集多對多章節拍點
                    for mapping in contract.chapter_mappings:
                        beat_rows.append((
                            nid, novel_id,
                            mapping.get("chapter_index", 1),
                            mapping.get("beat_index", 0),
                            float(mapping.get("coverage_ratio", 1.0)),
                            json.dumps(mapping, ensure_ascii=False),
                        ))

                    # 收集多線程歸屬
                    threads = contract.thread_memberships or n.thread_memberships
                    for seq_idx, th_id in enumerate(threads):
                        membership_rows.append((nid, novel_id, th_id, seq_idx))

                elif isinstance(n, dict):
                    nid = n.get("node_id", "")
                    h = n.get("hierarchy", {}) or {}
                    vol_idx = h.get("volume_index", n.get("volume_index", 1))
                    arc_idx = h.get("arc_index", n.get("arc_index", 1))
                    s_role = str(n.get("structural_role", "DEVELOP"))
                    n_type = str(n.get("node_type", "FACTION_COLLISION"))
                    f_demand = str(n.get("foreshadowing_demand", "NONE"))
                    p_status = str(n.get("planning_status", "DRAFT"))
                    r_status = str(n.get("realization_status", "PENDING"))
                    contract_dict = n.get("story_contract") or n.get("_story_contract") or {}
                    contract_json = json.dumps(contract_dict, ensure_ascii=False) if contract_dict else None
                    node_meta = dict(n.get("metadata", {}) or {})
                    if "chapter_window" in n and n["chapter_window"]:
                        node_meta["_chapter_window"] = list(n["chapter_window"])
                    meta_json = json.dumps(node_meta, ensure_ascii=False)

                    node_rows.append((
                        nid, novel_id, vol_idx, arc_idx, s_role, n_type, f_demand,
                        p_status, r_status, target_revision, contract_json, meta_json
                    ))

                    for ev in contract_dict.get("story_events", []):
                        ed = ev if isinstance(ev, dict) else ev.to_dict()
                        event_rows.append((
                            ed.get("event_id", f"EV_{nid}_{uuid.uuid4().hex[:6]}"),
                            nid, novel_id,
                            ed.get("event_summary", ""),
                            json.dumps(ed.get("participant_entities", []), ensure_ascii=False),
                            json.dumps(ed.get("action_motives", []), ensure_ascii=False),
                            json.dumps(ed.get("causal_preconditions", []), ensure_ascii=False),
                            ed.get("core_conflict", ""),
                            ed.get("direct_outcome", ""),
                            json.dumps(ed.get("state_mutations", []), ensure_ascii=False),
                            json.dumps(ed.get("downstream_impact", []), ensure_ascii=False),
                            json.dumps(ed.get("clue_bindings", []), ensure_ascii=False),
                        ))

                    for mapping in contract_dict.get("chapter_mappings", []):
                        beat_rows.append((
                            nid, novel_id,
                            mapping.get("chapter_index", 1),
                            mapping.get("beat_index", 0),
                            float(mapping.get("coverage_ratio", 1.0)),
                            json.dumps(mapping, ensure_ascii=False),
                        ))

                    threads = contract_dict.get("thread_memberships", []) or n.get("thread_memberships", [])
                    for seq_idx, th_id in enumerate(threads):
                        membership_rows.append((nid, novel_id, th_id, seq_idx))

            if node_rows:
                cursor.executemany("""
                INSERT INTO MASTER_GRAPH_NODES (
                    node_id, novel_id, volume_index, arc_index, structural_role,
                    node_type, foreshadowing_demand, planning_status, realization_status,
                    graph_revision, story_contract_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, node_rows)

            if event_rows:
                cursor.executemany("""
                INSERT INTO STORY_EVENT_ENTITIES (
                    event_id, node_id, novel_id, event_summary, participant_entities_json,
                    action_motives_json, causal_preconditions_json, core_conflict, direct_outcome,
                    state_mutations_json, downstream_impact_json, clue_bindings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, event_rows)

            if beat_rows:
                cursor.executemany("""
                INSERT OR REPLACE INTO NODE_CHAPTER_BEATS (
                    node_id, novel_id, chapter_index, beat_index, coverage_ratio, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, beat_rows)

            if membership_rows:
                cursor.executemany("""
                INSERT OR REPLACE INTO NODE_THREAD_MEMBERSHIPS (
                    node_id, novel_id, thread_id, sequence_index
                ) VALUES (?, ?, ?, ?)
                """, membership_rows)

            # 3. 收集與保存 Edges
            edges_iterable = []
            if hasattr(graph, "edges"):
                edges_iterable = graph.edges
            elif isinstance(graph, dict) and "edges" in graph:
                edges_iterable = graph["edges"]

            edge_rows: List[Tuple[Any, ...]] = []
            for e in edges_iterable:
                if isinstance(e, GeometryEdge):
                    e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
                    is_causal_int = 1 if e.is_causal else 0
                    dist = float(e.distance or 1.0)
                    meta_json = json.dumps(e.metadata, ensure_ascii=False)
                    edge_rows.append((
                        e.edge_id, novel_id, e.source, e.target, e_type,
                        is_causal_int, dist, target_revision, meta_json
                    ))
                elif isinstance(e, MasterGraphEdgeContract):
                    e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
                    is_causal_int = 1 if e.is_causal else 0
                    meta_json = json.dumps(e.metadata, ensure_ascii=False)
                    edge_rows.append((
                        e.edge_id, novel_id, e.source_id, e.target_id, e_type,
                        is_causal_int, 1.0, target_revision, meta_json
                    ))
                elif isinstance(e, dict):
                    e_type_val = e.get("edge_type", "CAUSES")
                    e_type = e_type_val.value if hasattr(e_type_val, "value") else str(e_type_val)
                    is_c = 1 if is_causal_edge(e_type) else 0
                    dist = float(e.get("distance", e.get("weight", 1.0)))
                    meta_json = json.dumps(e.get("metadata", {}), ensure_ascii=False)
                    src = e.get("source") or e.get("source_node") or e.get("source_id", "")
                    tgt = e.get("target") or e.get("target_node") or e.get("target_id", "")
                    edge_rows.append((
                        e.get("edge_id", f"EDGE_{uuid.uuid4().hex[:8]}"),
                        novel_id, src, tgt, e_type, is_c, dist, target_revision, meta_json
                    ))

            if edge_rows:
                cursor.executemany("""
                INSERT INTO MASTER_GRAPH_EDGES (
                    edge_id, novel_id, source_node, target_node, edge_type,
                    is_causal, weight, graph_revision, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, edge_rows)

            # 4. 同步 Params 與容器結構以保全 GeometryGraph 全域拓撲
            params_dict: Dict[str, Any] = {}
            if hasattr(graph, "params") and graph.params is not None:
                params_dict = asdict(graph.params)
            elif isinstance(graph, dict) and "params" in graph:
                params_dict = dict(graph["params"])
            params_dict["_graph_revision"] = target_revision

            cursor.execute("""
            INSERT OR REPLACE INTO geometry_metadata (novel_id, params_json) VALUES (?, ?)
            """, (novel_id, json.dumps(params_dict, ensure_ascii=False)))

            # 同步保存 Threads, Volumes, Arcs (若由 GeometryGraph 傳入)
            if hasattr(graph, "threads") and graph.threads:
                cursor.execute("DELETE FROM geometry_threads WHERE novel_id = ?", (novel_id,))
                t_rows = []
                for t in graph.threads.values():
                    t_type = t.thread_type.value if hasattr(t.thread_type, "value") else str(t.thread_type)
                    sk_repr = [r.value if hasattr(r, "value") else str(r) for r in t.structural_skeleton]
                    t_rows.append((
                        t.thread_id, novel_id, t_type,
                        json.dumps(t.node_sequence, ensure_ascii=False),
                        json.dumps(sk_repr, ensure_ascii=False),
                        json.dumps(t.semantic, ensure_ascii=False) if t.semantic else None,
                        json.dumps(t.metadata, ensure_ascii=False) if t.metadata else None,
                    ))
                cursor.executemany("""
                INSERT INTO geometry_threads (
                    thread_id, novel_id, thread_type, node_sequence_json,
                    structural_skeleton_json, semantic_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, t_rows)

            if hasattr(graph, "volumes") and graph.volumes:
                cursor.execute("DELETE FROM geometry_volumes WHERE novel_id = ?", (novel_id,))
                v_rows = []
                seen_vol_ids = set()
                for v in graph.volumes.values():
                    if not v or v.volume_id in seen_vol_ids:
                        continue
                    seen_vol_ids.add(v.volume_id)
                    sem = dict(v.semantic) if v.semantic and isinstance(v.semantic, dict) else {}
                    if getattr(v, "title", None):
                        sem["title"] = v.title
                    if getattr(v, "summary", None):
                        sem["summary"] = v.summary
                    v_rows.append((
                        v.volume_id, novel_id, v.volume_index,
                        v.chapter_range[0] if v.chapter_range else 1,
                        v.chapter_range[1] if v.chapter_range else 1,
                        json.dumps(v.arc_ids, ensure_ascii=False),
                        json.dumps(sem, ensure_ascii=False) if sem else None,
                    ))
                if v_rows:
                    cursor.executemany("""
                    INSERT INTO geometry_volumes (
                        volume_id, novel_id, volume_index, chapter_start, chapter_end, arc_ids_json, semantic_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, v_rows)

            if hasattr(graph, "arcs") and graph.arcs:
                cursor.execute("DELETE FROM geometry_arcs WHERE novel_id = ?", (novel_id,))
                a_rows = []
                seen_arc_ids = set()
                for a in graph.arcs.values():
                    if not a or a.arc_id in seen_arc_ids:
                        continue
                    seen_arc_ids.add(a.arc_id)
                    a_rows.append((
                        a.arc_id, novel_id, a.volume_index, a.arc_index,
                        a.chapter_range[0] if a.chapter_range else 1,
                        a.chapter_range[1] if a.chapter_range else 1,
                        json.dumps(a.thread_ids, ensure_ascii=False),
                        json.dumps(a.semantic, ensure_ascii=False) if a.semantic else None,
                    ))
                if a_rows:
                    cursor.executemany("""
                    INSERT INTO geometry_arcs (
                        arc_id, novel_id, volume_index, arc_index, chapter_start, chapter_end, thread_ids_json, semantic_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, a_rows)

    # =========================================================================
    # 3. Master Graph 核心讀取 (Load Master Graph)
    # =========================================================================

    def load_master_graph(self, novel_id: str) -> Optional[GeometryGraph]:
        """
        從資料庫載入完整的 GeometryGraph 實例。
        無縫反序列化 NodeStoryContract, StoryEventContract, MasterGraphEdgeContract,
        並組裝線程、卷次與弧容器，保證通過 validate_causal_dag() 驗收。
        若 Master Graph 尚未建立，自動 fallback 檢查舊版 geometry 表；若皆無則回傳 None。
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # 檢查 MASTER_GRAPH_NODES 是否有數據
        count_row = cursor.execute(
            "SELECT COUNT(*) FROM MASTER_GRAPH_NODES WHERE novel_id = ?", (novel_id,)
        ).fetchone()
        has_nodes = count_row[0] > 0 if count_row else False

        if not has_nodes:
            # 嘗試回退讀取舊幾何表 (向前相容)
            from backend.persistence.repositories.geometry import load_geometry_graph
            return load_geometry_graph(novel_id)

        # 1. 載入 Params / Revision
        meta_row = cursor.execute(
            "SELECT params_json FROM geometry_metadata WHERE novel_id = ?", (novel_id,)
        ).fetchone()
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

        params = GeometryParams(
            target_chapters=int(params_dict.get("target_chapters", 500)),
            volume_count=int(params_dict.get("volume_count", 10)),
            chapters_per_volume=int(params_dict.get("chapters_per_volume", 50)),
            complexity=params_dict.get("complexity", GeometryComplexity.DENSE),
            main_thread_count=int(params_dict.get("main_thread_count", 6)),
            subplot_count=int(params_dict.get("subplot_count", 18)),
            seed_for_rng=params_dict.get("seed_for_rng"),
        )
        graph = GeometryGraph(params)

        # 2. 預載入九維故事事件、拍點、線程歸屬 (避免 N+1 查詢)
        event_rows = cursor.execute(
            "SELECT * FROM STORY_EVENT_ENTITIES WHERE novel_id = ? ORDER BY event_id ASC", (novel_id,)
        ).fetchall()
        events_by_node: Dict[str, List[StoryEventContract]] = {}
        for er in event_rows:
            d = dict(er)
            ev = StoryEventContract(
                event_id=d["event_id"],
                node_id=d["node_id"],
                event_summary=d.get("event_summary", ""),
                participant_entities=json.loads(d["participant_entities_json"]) if d.get("participant_entities_json") else [],
                action_motives=json.loads(d["action_motives_json"]) if d.get("action_motives_json") else [],
                causal_preconditions=json.loads(d["causal_preconditions_json"]) if d.get("causal_preconditions_json") else [],
                core_conflict=d.get("core_conflict", ""),
                direct_outcome=d.get("direct_outcome", ""),
                state_mutations=json.loads(d["state_mutations_json"]) if d.get("state_mutations_json") else [],
                downstream_impact=json.loads(d["downstream_impact_json"]) if d.get("downstream_impact_json") else [],
                clue_bindings=json.loads(d["clue_bindings_json"]) if d.get("clue_bindings_json") else [],
            )
            events_by_node.setdefault(d["node_id"], []).append(ev)

        beat_rows = cursor.execute(
            "SELECT * FROM NODE_CHAPTER_BEATS WHERE novel_id = ? ORDER BY chapter_index ASC, beat_index ASC", (novel_id,)
        ).fetchall()
        beats_by_node: Dict[str, List[Dict[str, Any]]] = {}
        for br in beat_rows:
            d = dict(br)
            beats_by_node.setdefault(d["node_id"], []).append({
                "chapter_index": d["chapter_index"],
                "beat_index": d["beat_index"],
                "coverage_ratio": float(d.get("coverage_ratio", 1.0)),
            })

        membership_rows = cursor.execute(
            "SELECT * FROM NODE_THREAD_MEMBERSHIPS WHERE novel_id = ? ORDER BY sequence_index ASC", (novel_id,)
        ).fetchall()
        threads_by_node: Dict[str, List[str]] = {}
        for mr in membership_rows:
            d = dict(mr)
            threads_by_node.setdefault(d["node_id"], []).append(d["thread_id"])

        # 3. 載入 Nodes 並重構 NodeStoryContract 與 GeometryNode
        node_rows = cursor.execute(
            "SELECT * FROM MASTER_GRAPH_NODES WHERE novel_id = ? ORDER BY volume_index ASC, arc_index ASC, node_id ASC",
            (novel_id,),
        ).fetchall()

        max_revision = graph_revision
        for nr in node_rows:
            d = dict(nr)
            nid = d["node_id"]
            contract_raw = json.loads(d["story_contract_json"]) if d.get("story_contract_json") else {}

            if contract_raw:
                contract = NodeStoryContract.from_dict(contract_raw)
            else:
                contract = NodeStoryContract(
                    node_id=nid,
                    volume_index=d.get("volume_index", 1),
                    arc_index=d.get("arc_index", 1),
                )

            # 補齊正規表關聯資料
            if nid in events_by_node and not contract.story_events:
                contract.story_events = events_by_node[nid]
            if nid in beats_by_node:
                contract.chapter_mappings = beats_by_node[nid]
            if nid in threads_by_node and not contract.thread_memberships:
                contract.thread_memberships = threads_by_node[nid]

            try:
                contract.structural_role = StructuralRole(d.get("structural_role", "DEVELOP"))
            except ValueError:
                contract.structural_role = StructuralRole.DEVELOP

            try:
                contract.node_type = NodeType(d.get("node_type", "FACTION_COLLISION"))
            except ValueError:
                contract.node_type = NodeType.FACTION_COLLISION

            try:
                contract.foreshadowing_demand = ForeshadowingDemand(d.get("foreshadowing_demand", "NONE"))
            except ValueError:
                contract.foreshadowing_demand = ForeshadowingDemand.NONE

            try:
                contract.planning_status = PlanningStatus(d.get("planning_status", "DRAFT"))
            except ValueError:
                contract.planning_status = PlanningStatus.DRAFT

            try:
                contract.realization_status = RealizationStatus(d.get("realization_status", "PENDING"))
            except ValueError:
                contract.realization_status = RealizationStatus.PENDING

            node_rev = int(d.get("graph_revision", 1))
            contract.graph_revision = node_rev
            max_revision = max(max_revision, node_rev)

            meta = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}

            # 計算章節視窗
            chapter_window = (1, 1)
            if contract.chapter_mappings:
                chs = [m["chapter_index"] for m in contract.chapter_mappings if "chapter_index" in m]
                if chs:
                    chapter_window = (min(chs), max(chs))
            elif "_chapter_window" in meta:
                cw = meta["_chapter_window"]
                chapter_window = (int(cw[0]), int(cw[1]))
            else:
                v_idx = d.get("volume_index", 1)
                ch_per_vol = getattr(params, "chapters_per_volume", 30) or 30
                start_ch = (v_idx - 1) * ch_per_vol + 1
                chapter_window = (start_ch, start_ch + ch_per_vol - 1)

            geo_node = contract.to_geometry_node(chapter_window=chapter_window, metadata=meta)
            graph.add_node(geo_node)

        graph.graph_revision = max_revision

        # 4. 載入 Edges
        edge_rows = cursor.execute(
            "SELECT * FROM MASTER_GRAPH_EDGES WHERE novel_id = ?", (novel_id,)
        ).fetchall()
        for er in edge_rows:
            d = dict(er)
            try:
                e_type = EdgeType(d["edge_type"])
            except ValueError:
                e_type = EdgeType.CAUSES

            meta = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
            edge = GeometryEdge(
                edge_id=d["edge_id"],
                source=d["source_node"],
                target=d["target_node"],
                edge_type=e_type,
                distance=int(d.get("weight") or 1),
                metadata=meta,
                graph_revision=int(d.get("graph_revision") or 1),
            )
            graph.add_edge(edge)

        # 5. 載入 Threads, Volumes, Arcs 容器
        t_rows = cursor.execute("SELECT * FROM geometry_threads WHERE novel_id = ?", (novel_id,)).fetchall()
        for tr in t_rows:
            d = dict(tr)
            try:
                t_type = ThreadType(d["thread_type"])
            except ValueError:
                t_type = ThreadType.MAIN
            node_seq = json.loads(d["node_sequence_json"]) if d.get("node_sequence_json") else []
            sk_raw = json.loads(d["structural_skeleton_json"]) if d.get("structural_skeleton_json") else []
            sk: List[StructuralRole] = []
            for r in sk_raw:
                try:
                    sk.append(StructuralRole(r))
                except ValueError:
                    sk.append(StructuralRole.DEVELOP)

            thread = GeometryThread(
                thread_id=d["thread_id"],
                thread_type=t_type,
                node_sequence=node_seq,
                structural_skeleton=sk,
                semantic=json.loads(d["semantic_json"]) if d.get("semantic_json") else None,
                metadata=json.loads(d["metadata_json"]) if d.get("metadata_json") else {},
            )
            graph.add_thread(thread)

        v_rows = cursor.execute("SELECT * FROM geometry_volumes WHERE novel_id = ?", (novel_id,)).fetchall()
        for vr in v_rows:
            d = dict(vr)
            sem = json.loads(d["semantic_json"]) if d.get("semantic_json") else None
            title = sem.get("title", "") if sem and isinstance(sem, dict) else ""
            summary = sem.get("summary", "") if sem and isinstance(sem, dict) else ""
            vol = VolumeContainer(
                volume_id=d["volume_id"],
                volume_index=int(d.get("volume_index", 1)),
                chapter_range=(int(d.get("chapter_start", 1)), int(d.get("chapter_end", 1))),
                arc_ids=json.loads(d["arc_ids_json"]) if d.get("arc_ids_json") else [],
                semantic=sem,
                title=title,
                summary=summary,
            )
            graph.add_volume(vol)

        a_rows = cursor.execute("SELECT * FROM geometry_arcs WHERE novel_id = ?", (novel_id,)).fetchall()
        for ar in a_rows:
            d = dict(ar)
            arc = ArcContainer(
                arc_id=d["arc_id"],
                volume_index=int(d.get("volume_index", 1)),
                arc_index=int(d.get("arc_index", 1)),
                chapter_range=(int(d.get("chapter_start", 1)), int(d.get("chapter_end", 1))),
                thread_ids=json.loads(d["thread_ids_json"]) if d.get("thread_ids_json") else [],
                semantic=json.loads(d["semantic_json"]) if d.get("semantic_json") else None,
            )
            graph.add_arc(arc)

        return graph

    # =========================================================================
    # 4. 斷點續傳任務 Checkpoints (Plan §7.1)
    # =========================================================================

    def save_checkpoint(self, checkpoint: Dict[str, Any]) -> None:
        """
        儲存或更新全自動流水線任務 Checkpoint。
        支援 non-blocking cooldown 狀態、喚醒時間戳與重試計數。
        """
        conn = self._get_conn()
        run_id = checkpoint.get("run_id") or str(uuid.uuid4())
        novel_id = checkpoint.get("novel_id", "")
        stage = checkpoint.get("current_stage", "UNKNOWN")
        node_id = checkpoint.get("current_node_id")
        chapter = int(checkpoint.get("current_chapter", 0))
        revision = int(checkpoint.get("graph_revision", 1))
        retry_count = int(checkpoint.get("retry_count", 0))
        next_retry = checkpoint.get("next_retry_at")
        status = checkpoint.get("status", "RUNNING")
        payload = checkpoint.get("state_payload") or checkpoint.get("state_payload_json") or {}
        payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)

        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO pipeline_task_checkpoints (
                run_id, novel_id, current_stage, current_node_id, current_chapter,
                graph_revision, retry_count, next_retry_at, status, state_payload_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(run_id) DO UPDATE SET
                novel_id = excluded.novel_id,
                current_stage = excluded.current_stage,
                current_node_id = excluded.current_node_id,
                current_chapter = excluded.current_chapter,
                graph_revision = excluded.graph_revision,
                retry_count = excluded.retry_count,
                next_retry_at = excluded.next_retry_at,
                status = excluded.status,
                state_payload_json = excluded.state_payload_json,
                updated_at = CURRENT_TIMESTAMP
            """, (run_id, novel_id, stage, node_id, chapter, revision, retry_count, next_retry, status, payload_str))

    def load_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        """根據 run_id 讀取 Checkpoint 資料與反序列化現場狀態。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT * FROM pipeline_task_checkpoints WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None

        d = dict(row)
        try:
            d["state_payload"] = json.loads(d["state_payload_json"]) if d.get("state_payload_json") else {}
        except Exception:
            d["state_payload"] = {}
        return d

    def get_latest_checkpoint(self, novel_id: str, status: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """獲取指定小說最新的任務 Checkpoint。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM pipeline_task_checkpoints WHERE novel_id = ?"
        params: List[Any] = [novel_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC, rowid DESC LIMIT 1"

        row = cursor.execute(query, params).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["state_payload"] = json.loads(d["state_payload_json"]) if d.get("state_payload_json") else {}
        except Exception:
            d["state_payload"] = {}
        return d

    def update_checkpoint_status(
        self,
        run_id: str,
        status: str,
        next_retry_at: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        """更新 Checkpoint 的執行狀態與喚醒時鐘。"""
        conn = self._get_conn()
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = [status]
        if next_retry_at is not None:
            updates.append("next_retry_at = ?")
            params.append(next_retry_at)
        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)
        params.append(run_id)

        with conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE pipeline_task_checkpoints SET {', '.join(updates)} WHERE run_id = ?",
                params,
            )

    # =========================================================================
    # 5. 草稿審計日誌 (Draft Audits Ledger, Plan §3 & §6.1)
    # =========================================================================

    def record_draft_audit(
        self,
        novel_id: str,
        chapter_index: int,
        audit_status: str,
        defects: Optional[List[Dict[str, Any]]] = None,
        audit_report: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        記錄 Writer 草稿或 Editor 潤飾的事實審計違規報告。
        重要規則：審計違規結果 (VIOLATED) 僅記錄於此表，嚴禁污染已鎖定之 Master Graph。
        """
        conn = self._get_conn()
        defects_str = json.dumps(defects or [], ensure_ascii=False)
        report_str = json.dumps(audit_report or {}, ensure_ascii=False)

        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO chapter_draft_audits (
                novel_id, chapter_index, audit_status, defects_json, audit_report_json
            ) VALUES (?, ?, ?, ?, ?)
            """, (novel_id, chapter_index, audit_status, defects_str, report_str))
            return cursor.lastrowid or 0

    def get_draft_audits(
        self,
        novel_id: str,
        chapter_index: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """檢索指定小說或章節的歷史審計記錄。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM chapter_draft_audits WHERE novel_id = ?"
        params: List[Any] = [novel_id]
        if chapter_index is not None:
            query += " AND chapter_index = ?"
            params.append(chapter_index)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = cursor.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["defects"] = json.loads(d["defects_json"]) if d.get("defects_json") else []
            except Exception:
                d["defects"] = []
            try:
                d["audit_report"] = json.loads(d["audit_report_json"]) if d.get("audit_report_json") else {}
            except Exception:
                d["audit_report"] = {}
            result.append(d)
        return result

    # =========================================================================
    # 6. 拍點與多對多檢索 (Beat Mapping Query Helpers)
    # =========================================================================

    def get_node_beats(self, novel_id: str, node_id: str) -> List[Dict[str, Any]]:
        """
        查詢指定節點跨越的所有章節拍點映射。
        回傳清單依照 chapter_index ASC, beat_index ASC 排序。
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        rows = cursor.execute("""
        SELECT * FROM NODE_CHAPTER_BEATS
        WHERE novel_id = ? AND node_id = ?
        ORDER BY chapter_index ASC, beat_index ASC
        """, (novel_id, node_id)).fetchall()

        beats = []
        for r in rows:
            d = dict(r)
            beats.append({
                "id": d["id"],
                "node_id": d["node_id"],
                "chapter_index": d["chapter_index"],
                "beat_index": d["beat_index"],
                "coverage_ratio": float(d.get("coverage_ratio", 1.0)),
                "metadata": json.loads(d["metadata_json"]) if d.get("metadata_json") else {},
            })
        return beats

    def get_beat_nodes(self, novel_id: str, chapter_index: int) -> List[Dict[str, Any]]:
        """
        查詢指定章節承載的所有 Master Graph 節點拍點。
        關聯 MASTER_GRAPH_NODES 回傳結構角色、節點類型與雙軌生命週期狀態。
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        rows = cursor.execute("""
        SELECT b.id, b.node_id, b.chapter_index, b.beat_index, b.coverage_ratio,
               n.structural_role, n.node_type, n.planning_status, n.realization_status,
               n.foreshadowing_demand, n.volume_index, n.arc_index
        FROM NODE_CHAPTER_BEATS b
        LEFT JOIN MASTER_GRAPH_NODES n ON b.novel_id = n.novel_id AND b.node_id = n.node_id
        WHERE b.novel_id = ? AND b.chapter_index = ?
        ORDER BY b.beat_index ASC
        """, (novel_id, chapter_index)).fetchall()

        nodes = []
        for r in rows:
            nodes.append(dict(r))
        return nodes

    def save_node_chapter_beats(
        self,
        novel_id: str,
        beats: List[Dict[str, Any]],
    ) -> None:
        """
        保存或更新節點與章節拍點映射 (NODE_CHAPTER_BEATS)。
        """
        conn = self._get_conn()
        with conn:
            cursor = conn.cursor()
            for b in beats:
                nid = b["node_id"]
                ch_idx = int(b["chapter_index"])
                beat_idx = int(b.get("beat_index", 0))
                coverage = float(b.get("coverage_ratio", 1.0))
                meta_json = json.dumps(b.get("metadata", {}), ensure_ascii=False)
                cursor.execute("""
                INSERT INTO NODE_CHAPTER_BEATS (
                    node_id, novel_id, chapter_index, beat_index, coverage_ratio, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(novel_id, node_id, chapter_index, beat_index) DO UPDATE SET
                    coverage_ratio = excluded.coverage_ratio,
                    metadata_json = excluded.metadata_json
                """, (nid, novel_id, ch_idx, beat_idx, coverage, meta_json))

    def update_node_realization_status(
        self,
        novel_id: str,
        node_id: str,
        realization_status: Union[RealizationStatus, str],
    ) -> None:
        """更新單個節點的實現狀態 (如 REALIZED, IN_PROGRESS)"""
        conn = self._get_conn()
        status_val = realization_status.value if hasattr(realization_status, "value") else str(realization_status)
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE MASTER_GRAPH_NODES
            SET realization_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE novel_id = ? AND node_id = ?
            """, (status_val, novel_id, node_id))

    # =========================================================================
    # 7. 輔助檢索與統計方法 (Auxiliary Queries & Statistics)
    # =========================================================================

    def get_story_events_for_node(self, novel_id: str, node_id: str) -> List[StoryEventContract]:
        """檢索指定節點內的所有九維故事事件契約實體。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        rows = cursor.execute("""
        SELECT * FROM STORY_EVENT_ENTITIES
        WHERE novel_id = ? AND node_id = ?
        ORDER BY event_id ASC
        """, (novel_id, node_id)).fetchall()

        events = []
        for r in rows:
            d = dict(r)
            events.append(StoryEventContract(
                event_id=d["event_id"],
                node_id=d["node_id"],
                event_summary=d.get("event_summary", ""),
                participant_entities=json.loads(d["participant_entities_json"]) if d.get("participant_entities_json") else [],
                action_motives=json.loads(d["action_motives_json"]) if d.get("action_motives_json") else [],
                causal_preconditions=json.loads(d["causal_preconditions_json"]) if d.get("causal_preconditions_json") else [],
                core_conflict=d.get("core_conflict", ""),
                direct_outcome=d.get("direct_outcome", ""),
                state_mutations=json.loads(d["state_mutations_json"]) if d.get("state_mutations_json") else [],
                downstream_impact=json.loads(d["downstream_impact_json"]) if d.get("downstream_impact_json") else [],
                clue_bindings=json.loads(d["clue_bindings_json"]) if d.get("clue_bindings_json") else [],
            ))
        return events

    def get_node(self, novel_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """獲取單個節點的持久化記錄與契約內容。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        row = cursor.execute("""
        SELECT * FROM MASTER_GRAPH_NODES
        WHERE novel_id = ? AND node_id = ?
        """, (novel_id, node_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["story_contract"] = json.loads(d["story_contract_json"]) if d.get("story_contract_json") else {}
        except Exception:
            d["story_contract"] = {}
        try:
            d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        except Exception:
            d["metadata"] = {}
        return d

    def get_edges_for_node(self, novel_id: str, node_id: str, direction: str = "both") -> List[Dict[str, Any]]:
        """獲取與節點相連的邊。direction 可為 'incoming', 'outgoing', 或 'both'。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM MASTER_GRAPH_EDGES WHERE novel_id = ?"
        params: List[Any] = [novel_id]

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
            try:
                d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
            except Exception:
                d["metadata"] = {}
            edges.append(d)
        return edges

    def get_master_graph_stats(self, novel_id: str) -> Dict[str, Any]:
        """統計 Master Graph 各項關鍵指標。"""
        conn = self._get_conn()
        cursor = conn.cursor()

        node_cnt = cursor.execute(
            "SELECT COUNT(*) FROM MASTER_GRAPH_NODES WHERE novel_id = ?", (novel_id,)
        ).fetchone()[0]
        edge_cnt = cursor.execute(
            "SELECT COUNT(*) FROM MASTER_GRAPH_EDGES WHERE novel_id = ?", (novel_id,)
        ).fetchone()[0]
        causal_cnt = cursor.execute(
            "SELECT COUNT(*) FROM MASTER_GRAPH_EDGES WHERE novel_id = ? AND is_causal = 1", (novel_id,)
        ).fetchone()[0]
        event_cnt = cursor.execute(
            "SELECT COUNT(*) FROM STORY_EVENT_ENTITIES WHERE novel_id = ?", (novel_id,)
        ).fetchone()[0]
        beat_cnt = cursor.execute(
            "SELECT COUNT(*) FROM NODE_CHAPTER_BEATS WHERE novel_id = ?", (novel_id,)
        ).fetchone()[0]
        locked_cnt = cursor.execute(
            "SELECT COUNT(*) FROM MASTER_GRAPH_NODES WHERE novel_id = ? AND planning_status = 'STORY_CANON_LOCKED'",
            (novel_id,),
        ).fetchone()[0]

        rev_row = cursor.execute(
            "SELECT MAX(graph_revision) FROM MASTER_GRAPH_NODES WHERE novel_id = ?", (novel_id,)
        ).fetchone()
        current_rev = rev_row[0] if rev_row and rev_row[0] is not None else 1

        return {
            "node_count": node_cnt,
            "edge_count": edge_cnt,
            "causal_edge_count": causal_cnt,
            "non_causal_edge_count": edge_cnt - causal_cnt,
            "story_event_count": event_cnt,
            "chapter_beat_count": beat_cnt,
            "locked_node_count": locked_cnt,
            "is_canon_locked": (node_cnt > 0 and locked_cnt == node_cnt),
            "graph_revision": current_rev,
        }

    def has_master_graph(self, novel_id: str) -> bool:
        """檢查指定小說是否存在 Master Graph。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cnt = cursor.execute(
            "SELECT COUNT(*) FROM MASTER_GRAPH_NODES WHERE novel_id = ?", (novel_id,)
        ).fetchone()[0]
        return cnt > 0

    def delete_master_graph(self, novel_id: str) -> None:
        """刪除指定小說的 Master Graph 全部關聯數據。"""
        conn = self._get_conn()
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM MASTER_GRAPH_NODES WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM MASTER_GRAPH_EDGES WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM STORY_EVENT_ENTITIES WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM NODE_CHAPTER_BEATS WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM NODE_THREAD_MEMBERSHIPS WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM pipeline_task_checkpoints WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM chapter_draft_audits WHERE novel_id = ?", (novel_id,))


# =============================================================================
# 8. 全域實例與模組級別便捷函式 (Module Singleton & Top-Level Functions)
# =============================================================================

master_graph_repository = MasterGraphRepository()

def init_master_graph_tables(conn: Optional[sqlite3.Connection] = None) -> None:
    master_graph_repository.init_tables(conn)

def save_master_graph(novel_id: str, graph: Union[GeometryGraph, Dict[str, Any]], revision: Optional[int] = None) -> None:
    master_graph_repository.save_master_graph(novel_id, graph, revision)

def load_master_graph(novel_id: str) -> Optional[GeometryGraph]:
    return master_graph_repository.load_master_graph(novel_id)

def save_checkpoint(checkpoint: Dict[str, Any]) -> None:
    master_graph_repository.save_checkpoint(checkpoint)

def load_checkpoint(run_id: str) -> Optional[Dict[str, Any]]:
    return master_graph_repository.load_checkpoint(run_id)

def get_latest_checkpoint(novel_id: str, status: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return master_graph_repository.get_latest_checkpoint(novel_id, status)

def record_draft_audit(
    novel_id: str,
    chapter_index: int,
    audit_status: str,
    defects: Optional[List[Dict[str, Any]]] = None,
    audit_report: Optional[Dict[str, Any]] = None,
) -> int:
    return master_graph_repository.record_draft_audit(novel_id, chapter_index, audit_status, defects, audit_report)

def get_draft_audits(novel_id: str, chapter_index: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    return master_graph_repository.get_draft_audits(novel_id, chapter_index, limit)

def get_node_beats(novel_id: str, node_id: str) -> List[Dict[str, Any]]:
    return master_graph_repository.get_node_beats(novel_id, node_id)

def get_beat_nodes(novel_id: str, chapter_index: int) -> List[Dict[str, Any]]:
    return master_graph_repository.get_beat_nodes(novel_id, chapter_index)

def save_node_chapter_beats(novel_id: str, beats: List[Dict[str, Any]]) -> None:
    master_graph_repository.save_node_chapter_beats(novel_id, beats)

def update_node_realization_status(novel_id: str, node_id: str, realization_status: Union[RealizationStatus, str]) -> None:
    master_graph_repository.update_node_realization_status(novel_id, node_id, realization_status)

def get_story_events_for_node(novel_id: str, node_id: str) -> List[StoryEventContract]:
    return master_graph_repository.get_story_events_for_node(novel_id, node_id)

def get_master_graph_stats(novel_id: str) -> Dict[str, Any]:
    return master_graph_repository.get_master_graph_stats(novel_id)

def has_master_graph(novel_id: str) -> bool:
    return master_graph_repository.has_master_graph(novel_id)

def delete_master_graph(novel_id: str) -> None:
    master_graph_repository.delete_master_graph(novel_id)


__all__ = [
    "MasterGraphRepository",
    "master_graph_repository",
    "init_master_graph_tables",
    "save_master_graph",
    "load_master_graph",
    "save_checkpoint",
    "load_checkpoint",
    "get_latest_checkpoint",
    "record_draft_audit",
    "get_draft_audits",
    "get_node_beats",
    "get_beat_nodes",
    "save_node_chapter_beats",
    "update_node_realization_status",
    "get_story_events_for_node",
    "get_master_graph_stats",
    "has_master_graph",
    "delete_master_graph",
]

