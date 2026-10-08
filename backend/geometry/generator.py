# -*- coding: utf-8 -*-
"""
程式化幾何生成器 (Programmatic Geometry Generator)

核心職責：
1. 完全不依賴 LLM，純粹以程式演算法 + 敘事結構 Motif 生成完整、高複雜度、長距離關聯的故事骨架。
2. 根據 GeometryParams（規模、題材密度、線程數量等），一次性產生全書的：
   - 層級容器（Volumes -> Arcs -> Sequences，保證 10+ 卷）
   - 章節事件節點（GeometryNode，掛載 NodeStoryContract 與多線程歸屬）
   - 線程骨架（GeometryThread，包含 6 主線 TM01-TM06、18 支線 TS01-TS18 共 24 條全線程）
   - 結構 Motif 邊（長距離回收、分岔合流、交織、匯聚、情節角色耦合、主題對比）
3. 嚴格強制因果邊 (CAUSES, ENABLES, ESCALATES) 為有向無環圖 (DAG，cycle_count == 0)。
4. 輸出符合 Geometry-First 與 Master Graph 標準的完整 GeometryGraph。
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional, Tuple

from backend.geometry.models import (
    ArcContainer,
    CAUSAL_EDGE_TYPES,
    EdgeType,
    ForeshadowingDemand,
    GeometryComplexity,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    GeometryThread,
    NodeHierarchy,
    NodeStoryContract,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    SequenceContainer,
    StructuralRole,
    ThreadType,
    VolumeContainer,
)
from backend.geometry.motifs import MotifApplicator


class GeometryGenerator:
    """
    純程式碼幾何生成器。
    一次性為全書（例如 300-800 章）生成無語義內容但具備高度拓撲結構與故事合約的空骨架圖。
    """

    def __init__(self, params: GeometryParams):
        self.params = params

        # 隨機數種子保證可重現性
        if params.seed_for_rng is not None:
            seed_str = str(params.seed_for_rng)
            seed_int = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)
            self.rng = random.Random(seed_int)
        else:
            self.rng = random.Random()

    def generate(self) -> GeometryGraph:
        """
        核心生成入口：一次性產出完整高複雜度 GeometryGraph。
        """
        graph = GeometryGraph(self.params)

        # 1. 構建層級架構容器 (Volumes -> Arcs -> Sequences)
        self._build_hierarchy(graph)

        # 2. 構建章節節點容器 (Chapter Containers & Event Nodes)
        self._build_nodes(graph)

        # 3. 構建敘事線程骨架 (Thread Skeletons)
        self._build_threads(graph)

        # 4. 應用結構 Motif 產生跨線與長距離關聯
        motif_app = MotifApplicator(self.rng)
        motif_app.apply_all_motifs(graph)

        # 5. 保證全圖連通性（消除孤立節點）
        self._ensure_connectivity(graph)

        # 6. 強制因果約束邊拓撲無環性 (DAG Invariant)
        self._enforce_causal_dag_ordering(graph)

        # 7. 掛接所有節點的 NodeStoryContract
        graph.ensure_story_contracts()

        # 8. 嚴格驗證因果 DAG 無環不變量
        cycle_errors = graph.validate_causal_dag()
        if cycle_errors:
            raise ValueError(f"GeometryGenerator DAG invariant violation: {cycle_errors}")

        return graph

    def _build_hierarchy(self, graph: GeometryGraph) -> None:
        """
        構建篇卷、弧線、序列的層級劃分。
        保證預設或未指定時生成 10+ 卷，若傳入自定義 volume_count 則精確尊重。
        """
        target_chapters = self.params.target_chapters
        volume_count = self.params.volume_count

        if volume_count <= 0:
            volume_count = max(10, target_chapters // max(1, self.params.chapters_per_volume))

        # 若指定的 chapters_per_volume 偏大會導致提前終止無法生成指定卷數，自適應章節跨度
        if volume_count > 0 and self.params.chapters_per_volume * volume_count > target_chapters:
            chapters_per_vol = max(1, target_chapters // volume_count)
        else:
            chapters_per_vol = max(1, self.params.chapters_per_volume)

        global_arc_idx = 1
        global_seq_idx = 1

        for v_idx in range(1, volume_count + 1):
            v_start = (v_idx - 1) * chapters_per_vol + 1
            if v_idx == volume_count:
                v_end = target_chapters
            else:
                v_end = min(v_idx * chapters_per_vol, target_chapters)

            if v_start > target_chapters:
                break
            if v_end > target_chapters:
                v_end = target_chapters

            vol_id = f"V{v_idx:02d}"
            vol_arc_ids: List[str] = []

            # 每個 Volume 分割為 3 到 4 個 Arc
            vol_span = v_end - v_start + 1
            arcs_in_vol = 4 if vol_span >= 20 else max(1, min(3, vol_span))
            ch_span = max(1, vol_span // arcs_in_vol)

            for a_sub_idx in range(1, arcs_in_vol + 1):
                a_start = v_start + (a_sub_idx - 1) * ch_span
                a_end = v_end if a_sub_idx == arcs_in_vol else min(a_start + ch_span - 1, v_end)
                if a_start > v_end:
                    break

                arc_id = f"A{global_arc_idx:02d}"
                global_arc_idx += 1
                vol_arc_ids.append(arc_id)

                # 每個 Arc 包含 2 到 3 個 Sequence
                arc_span = a_end - a_start + 1
                seq_count = 2 if arc_span < 8 else 3
                s_span = max(1, arc_span // seq_count)

                for s_sub_idx in range(1, seq_count + 1):
                    s_start = a_start + (s_sub_idx - 1) * s_span
                    s_end = a_end if s_sub_idx == seq_count else min(s_start + s_span - 1, a_end)
                    if s_start > a_end:
                        break

                    seq_id = f"S{global_seq_idx:03d}"
                    global_seq_idx += 1

                    seq_container = SequenceContainer(
                        sequence_id=seq_id,
                        arc_id=arc_id,
                        sequence_index=s_sub_idx,
                        chapter_range=(s_start, s_end),
                        node_ids=[],
                    )
                    graph.add_sequence(seq_container)

                arc_container = ArcContainer(
                    arc_id=arc_id,
                    volume_index=v_idx,
                    arc_index=a_sub_idx,
                    chapter_range=(a_start, a_end),
                    thread_ids=[],
                    semantic=None,
                )
                graph.add_arc(arc_container)

            vol_container = VolumeContainer(
                volume_id=vol_id,
                volume_index=v_idx,
                chapter_range=(v_start, v_end),
                arc_ids=vol_arc_ids,
                semantic=None,
            )
            graph.add_volume(vol_container)

    def _build_nodes(self, graph: GeometryGraph) -> None:
        """
        根據密度配置為每一章產生具備 structural_role 與 NodeStoryContract 的幾何節點。
        """
        complexity_density = {
            GeometryComplexity.SPARSE: 1.5,
            GeometryComplexity.STANDARD: 2.2,
            GeometryComplexity.DENSE: 2.8,
            GeometryComplexity.VERY_DENSE: 3.5,
        }
        nodes_per_chapter = complexity_density.get(self.params.complexity, 2.8)

        node_counter = 1
        sequences = sorted(graph.sequences.values(), key=lambda s: s.chapter_range[0])

        for seq in sequences:
            s_start, s_end = seq.chapter_range
            arc = graph.arcs.get(seq.arc_id)
            v_idx = arc.volume_index if arc else 1
            a_idx = arc.arc_index if arc else 1
            s_idx = seq.sequence_index

            hierarchy = NodeHierarchy(
                volume_index=v_idx,
                arc_index=a_idx,
                sequence_index=s_idx,
            )

            for ch in range(s_start, s_end + 1):
                count = int(nodes_per_chapter) + (1 if self.rng.random() < (nodes_per_chapter % 1) else 0)
                count = max(1, count)

                for beat_idx in range(count):
                    node_id = f"G{node_counter:04d}"
                    node_counter += 1

                    role = self._determine_structural_role(ch, beat_idx, count, s_start, s_end, a_idx)

                    is_climax = (ch == s_end and a_idx in (3, 4))
                    importance = 0.85 if is_climax else round(self.rng.uniform(0.4, 0.7), 2)

                    # 判定 node_type
                    if is_climax or role in (StructuralRole.PAYOFF, StructuralRole.CONVERGE):
                        node_type = NodeType.CRISIS
                    elif role in (StructuralRole.OPEN_THREAD, StructuralRole.TRANSITION):
                        node_type = NodeType.FACTION_COLLISION
                    elif role in (StructuralRole.REVISIT, StructuralRole.ECHO):
                        node_type = NodeType.SECRET_REVEAL
                    elif role in (StructuralRole.CHARACTER_SHIFT, StructuralRole.RELATIONSHIP_CHANGE):
                        node_type = NodeType.TRANSFORMATION
                    else:
                        node_type = NodeType.DEVELOPMENT

                    # 判定 foreshadowing_demand
                    if role == StructuralRole.OPEN_THREAD or (v_idx <= 3 and beat_idx == 0):
                        foreshadowing_demand = ForeshadowingDemand.REQUIRES_PLANT
                    elif role in (StructuralRole.REVISIT, StructuralRole.BRANCH):
                        foreshadowing_demand = ForeshadowingDemand.TURN_SITE
                    elif role in (StructuralRole.PAYOFF, StructuralRole.CLOSE) or (v_idx >= 8 and is_climax):
                        foreshadowing_demand = ForeshadowingDemand.MUST_PAYOFF
                    else:
                        foreshadowing_demand = ForeshadowingDemand.NONE

                    # 建立 NodeStoryContract
                    story_contract = NodeStoryContract(
                        node_id=node_id,
                        volume_index=v_idx,
                        arc_index=a_idx,
                        thread_memberships=[],
                        structural_role=role,
                        node_type=node_type,
                        foreshadowing_demand=foreshadowing_demand,
                        planning_status=PlanningStatus.DRAFT,
                        realization_status=RealizationStatus.PENDING,
                        graph_revision=1,
                    )

                    node = GeometryNode(
                        node_id=node_id,
                        hierarchy=hierarchy,
                        chapter_window=(ch, ch),
                        structural_role=role,
                        primary_thread="",  # 在 _build_threads 中綁定
                        importance=importance,
                        semantic=None,
                        metadata={
                            "beat_index": beat_idx,
                            "is_climax_candidate": is_climax,
                            "thread_memberships": [],
                        },
                        thread_memberships=[],
                        node_type=node_type,
                        foreshadowing_demand=foreshadowing_demand,
                        story_contract=story_contract,
                    )

                    graph.add_node(node)
                    seq.node_ids.append(node_id)

    def _determine_structural_role(
        self,
        chapter: int,
        beat: int,
        total_beats: int,
        s_start: int,
        s_end: int,
        arc_index: int,
    ) -> StructuralRole:
        """
        純幾何拓撲邏輯判斷節點的初始 StructuralRole。
        """
        if chapter == s_start and beat == 0:
            return StructuralRole.OPEN_THREAD if arc_index == 1 else StructuralRole.TRANSITION

        if chapter == s_end and beat == total_beats - 1:
            if arc_index >= 3:
                return StructuralRole.PAYOFF
            return StructuralRole.CONVERGE

        mid_rand = self.rng.random()
        if mid_rand < 0.35:
            return StructuralRole.DEVELOP
        elif mid_rand < 0.60:
            return StructuralRole.ESCALATE
        elif mid_rand < 0.75:
            return StructuralRole.REVISIT
        elif mid_rand < 0.85:
            return StructuralRole.CHARACTER_SHIFT
        elif mid_rand < 0.93:
            return StructuralRole.ECHO
        else:
            return StructuralRole.RELATIONSHIP_CHANGE

    def _build_threads(self, graph: GeometryGraph) -> None:
        """
        為幾何圖構建貫穿全書或特定弧線的線程（Thread Skeletons）。
        支援獨立前綴編號（TM01-06, TS01-18），註冊多線程歸屬至 node_story_contract。
        """
        target_chapters = self.params.target_chapters
        all_nodes = sorted(
            graph.nodes.values(),
            key=lambda n: (n.chapter_window[0], n.metadata.get("beat_index", 0), n.node_id)
        )
        if not all_nodes:
            return

        thread_specs = [
            (ThreadType.MAIN, self.params.main_thread_count, "TM"),
            (ThreadType.SUBPLOT, self.params.subplot_count, "TS"),
            (ThreadType.CHARACTER_ARC, self.params.character_arc_count, "TC"),
            (ThreadType.RELATIONSHIP_ARC, self.params.relationship_arc_count, "TR"),
            (ThreadType.THEMATIC, self.params.thematic_thread_count, "TT"),
        ]

        for t_type, count, prefix in thread_specs:
            for idx in range(1, count + 1):
                thread_id = f"{prefix}{idx:02d}"

                if t_type == ThreadType.MAIN:
                    t_start = 1
                    t_end = target_chapters
                elif t_type == ThreadType.THEMATIC:
                    t_start = 1
                    t_end = target_chapters
                elif t_type == ThreadType.CHARACTER_ARC:
                    v_span = self.rng.randint(2, max(3, len(graph.volumes)))
                    v_start_idx = self.rng.randint(1, max(1, len(graph.volumes) - v_span + 1))
                    t_start = (v_start_idx - 1) * self.params.chapters_per_volume + 1
                    t_end = min(target_chapters, (v_start_idx + v_span - 1) * self.params.chapters_per_volume)
                else:
                    span_ch = self.rng.randint(15, max(30, target_chapters // 4))
                    t_start = self.rng.randint(1, max(1, target_chapters - span_ch))
                    t_end = min(target_chapters, t_start + span_ch)

                candidate_nodes = [
                    n for n in all_nodes
                    if t_start <= n.chapter_window[0] <= t_end
                ]

                sample_step = max(2, len(candidate_nodes) // self.rng.randint(6, 18))
                selected_nodes = candidate_nodes[::sample_step]

                if len(selected_nodes) < 3:
                    selected_nodes = candidate_nodes[:min(5, len(candidate_nodes))]

                # 確保節點依嚴格時序升序排列
                selected_nodes.sort(
                    key=lambda n: (n.chapter_window[0], n.metadata.get("beat_index", 0), n.node_id)
                )

                node_seq: List[str] = []
                structural_skeleton: List[StructuralRole] = []

                for s_idx, node in enumerate(selected_nodes):
                    node_seq.append(node.node_id)

                    # 註冊多線程歸屬
                    if thread_id not in node.thread_memberships:
                        node.thread_memberships.append(thread_id)
                    if node.story_contract and thread_id not in node.story_contract.thread_memberships:
                        node.story_contract.thread_memberships.append(thread_id)
                    node.metadata["thread_memberships"] = list(node.thread_memberships)

                    # 向後相容 primary_thread
                    if not node.primary_thread or t_type == ThreadType.MAIN:
                        node.primary_thread = thread_id
                        if node.story_contract:
                            node.story_contract.primary_thread = thread_id

                    if s_idx == 0:
                        s_role = StructuralRole.OPEN_THREAD
                    elif s_idx == len(selected_nodes) - 1:
                        s_role = StructuralRole.PAYOFF if t_type in (ThreadType.MAIN, ThreadType.SUBPLOT) else StructuralRole.CLOSE
                    elif s_idx == len(selected_nodes) - 2 and t_type in (ThreadType.MAIN, ThreadType.SUBPLOT):
                        s_role = StructuralRole.CONVERGE
                    else:
                        s_role = node.structural_role

                    structural_skeleton.append(s_role)

                # 線程內部時序因果推進邊 (CAUSES / ENABLES)
                for i in range(len(selected_nodes) - 1):
                    src = selected_nodes[i]
                    tgt = selected_nodes[i + 1]
                    dist = abs(tgt.chapter_window[0] - src.chapter_window[0])
                    edge_type = EdgeType.CAUSES if dist <= 3 else EdgeType.ENABLES

                    graph.add_edge(GeometryEdge(
                        edge_id=f"ET_{thread_id}_{i:02d}",
                        source=src.node_id,
                        target=tgt.node_id,
                        edge_type=edge_type,
                        distance=dist,
                        metadata={"thread_id": thread_id, "is_thread_spine": True},
                    ))

                geometry_thread = GeometryThread(
                    thread_id=thread_id,
                    thread_type=t_type,
                    node_sequence=node_seq,
                    structural_skeleton=structural_skeleton,
                    semantic=None,
                    metadata={"chapter_span": (t_start, t_end)},
                )
                graph.add_thread(geometry_thread)

        # 保證全圖 100% 節點皆擁有至少一個線程歸屬
        main_thread_ids = [f"TM{i:02d}" for i in range(1, self.params.main_thread_count + 1)] if self.params.main_thread_count > 0 else ["TM01"]
        for node in all_nodes:
            if not node.thread_memberships:
                t_idx = (node.chapter_window[0] % len(main_thread_ids))
                assigned_tid = main_thread_ids[t_idx]
                node.thread_memberships.append(assigned_tid)
                node.primary_thread = assigned_tid
                if node.story_contract:
                    node.story_contract.thread_memberships.append(assigned_tid)
                    node.story_contract.primary_thread = assigned_tid
                node.metadata["thread_memberships"] = list(node.thread_memberships)

    def _ensure_connectivity(self, graph: GeometryGraph) -> None:
        """
        確保全圖無完全孤立的節點。
        """
        all_nodes = sorted(
            graph.nodes.values(),
            key=lambda n: (n.chapter_window[0], n.metadata.get("beat_index", 0), n.node_id)
        )
        for idx, node in enumerate(all_nodes):
            edges = graph.get_edges_for_node(node.node_id, direction="both")
            if not edges:
                if idx > 0:
                    prev_node = all_nodes[idx - 1]
                    dist = abs(node.chapter_window[0] - prev_node.chapter_window[0])
                    graph.add_edge(GeometryEdge(
                        edge_id=f"EC_PREV_{node.node_id}",
                        source=prev_node.node_id,
                        target=node.node_id,
                        edge_type=EdgeType.ENABLES,
                        distance=dist,
                        metadata={"auto_connected": True},
                    ))
                if idx < len(all_nodes) - 1:
                    next_node = all_nodes[idx + 1]
                    dist = abs(next_node.chapter_window[0] - node.chapter_window[0])
                    graph.add_edge(GeometryEdge(
                        edge_id=f"EC_NEXT_{node.node_id}",
                        source=node.node_id,
                        target=next_node.node_id,
                        edge_type=EdgeType.CAUSES,
                        distance=dist,
                        metadata={"auto_connected": True},
                    ))

    def _enforce_causal_dag_ordering(self, graph: GeometryGraph) -> None:
        """
        強制規範全圖因果約束邊 (CAUSES, ENABLES, ESCALATES) 遵循嚴格敘事拓撲順序。
        1. 移除無效或端點缺失的邊。
        2. 移除任何自環邊 (source == target)。
        3. 若因果約束邊逆向 (source > target)，反轉其方向使其順應敘事因果推進。
        4. 消除完全重複的平行邊。
        保證圖論數學層面 100% 無環 (cycle_count == 0)。
        """
        def node_order(nid: str) -> Tuple[int, int, str]:
            n = graph.nodes.get(nid)
            if not n:
                return (0, 0, nid)
            beat = n.metadata.get("beat_index", 0) if n.metadata else 0
            return (n.chapter_window[0], beat, n.node_id)

        seen_edges = set()
        clean_edges: List[GeometryEdge] = []

        for edge in graph.edges:
            if edge.source not in graph.nodes or edge.target not in graph.nodes:
                continue
            if edge.source == edge.target:
                continue

            if edge.edge_type in CAUSAL_EDGE_TYPES:
                order_src = node_order(edge.source)
                order_tgt = node_order(edge.target)
                if order_src > order_tgt:
                    edge.source, edge.target = edge.target, edge.source
                    n_s = graph.nodes[edge.source]
                    n_t = graph.nodes[edge.target]
                    edge.distance = abs(n_t.chapter_window[0] - n_s.chapter_window[0])

            edge_key = (edge.source, edge.target, edge.edge_type)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                clean_edges.append(edge)

        graph.edges = clean_edges
