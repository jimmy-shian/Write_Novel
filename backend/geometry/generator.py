# -*- coding: utf-8 -*-
"""
程式化幾何生成器 (Programmatic Geometry Generator)

核心職責：
1. 完全不依賴 LLM，純粹以程式演算法 + 敘事結構 Motif 生成完整、高複雜度、長距離關聯的故事骨架。
2. 根據 GeometryParams（規模、題材密度、線程數量等），一次性產生全書的：
   - 層級容器（Volumes -> Arcs -> Sequences）
   - 章節事件節點（GeometryNode，semantic=None）
   - 線程骨架（GeometryThread，包含角色弧線、副線、主線）
   - 結構 Motif 邊（長距離回收、分岔合流、交織、匯聚、情節角色耦合、主題對比）
3. 輸出符合 Geometry-First 標準的完整 GeometryGraph。
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional, Tuple

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
    SequenceContainer,
    StructuralRole,
    ThreadType,
    VolumeContainer,
)
from backend.geometry.motifs import MotifApplicator


class GeometryGenerator:
    """
    純程式碼幾何生成器。
    一次性為全書（例如 800 章）生成無語義內容但具備高度拓撲結構的空骨架圖。
    """

    def __init__(self, params: GeometryParams):
        self.params = params

        # 隨機數種子保證可重現性
        if params.seed_for_rng:
            seed_int = int(hashlib.md5(params.seed_for_rng.encode("utf-8")).hexdigest(), 16) % (2**32)
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

        return graph

    def _build_hierarchy(self, graph: GeometryGraph) -> None:
        """
        構建篇卷、弧線、序列的層級劃分。
        """
        target_chapters = self.params.target_chapters
        chapters_per_vol = max(1, self.params.chapters_per_volume)
        volume_count = self.params.volume_count

        if volume_count <= 0:
            volume_count = max(1, target_chapters // chapters_per_vol)

        global_arc_idx = 1
        global_seq_idx = 1

        for v_idx in range(1, volume_count + 1):
            v_start = (v_idx - 1) * chapters_per_vol + 1
            v_end = min(v_idx * chapters_per_vol, target_chapters) if v_idx == volume_count else v_idx * chapters_per_vol
            if v_start > target_chapters:
                break
            if v_end > target_chapters:
                v_end = target_chapters

            vol_id = f"V{v_idx:02d}"
            vol_arc_ids: List[str] = []

            # 每個 Volume 分割為 3 到 4 個 Arc（通常對應 起、承/激化、轉/危機、合/收束）
            arcs_in_vol = 4 if (v_end - v_start + 1) >= 20 else 3
            ch_span = max(1, (v_end - v_start + 1) // arcs_in_vol)

            for a_sub_idx in range(1, arcs_in_vol + 1):
                a_start = v_start + (a_sub_idx - 1) * ch_span
                a_end = v_end if a_sub_idx == arcs_in_vol else min(a_start + ch_span - 1, v_end)
                if a_start > v_end:
                    break

                arc_id = f"A{global_arc_idx:02d}"
                global_arc_idx += 1
                vol_arc_ids.append(arc_id)

                # 每個 Arc 包含 2 到 3 個 Sequence
                seq_count = 2 if (a_end - a_start + 1) < 8 else 3
                s_span = max(1, (a_end - a_start + 1) // seq_count)

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
        根據密度配置為每一章產生具備 structural_role 的空幾何節點。
        """
        # 依複雜度決定每章節點基準數量
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
                # 決定該章產生的節點數
                count = int(nodes_per_chapter) + (1 if self.rng.random() < (nodes_per_chapter % 1) else 0)
                count = max(1, count)

                for beat_idx in range(count):
                    node_id = f"G{node_counter:04d}"
                    node_counter += 1

                    # 依節點在 Sequence/Arc 裡的位置賦予預設結構角色
                    role = self._determine_structural_role(ch, beat_idx, count, s_start, s_end, a_idx)

                    # 重要度判定：弧末或卷末高潮點重要度較高
                    is_climax = (ch == s_end and a_idx in (3, 4))
                    importance = 0.85 if is_climax else round(self.rng.uniform(0.4, 0.7), 2)

                    node = GeometryNode(
                        node_id=node_id,
                        hierarchy=hierarchy,
                        chapter_window=(ch, ch),
                        structural_role=role,
                        primary_thread="",  # 在 _build_threads 綁定
                        importance=importance,
                        semantic=None,
                        metadata={
                            "beat_index": beat_idx,
                            "is_climax_candidate": is_climax,
                        },
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

        # 中間節點角色分佈
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
        線程只定義 node sequence 與 structural skeleton，不包含語義。
        """
        target_chapters = self.params.target_chapters
        all_nodes = sorted(graph.nodes.values(), key=lambda n: (n.chapter_window[0], n.node_id))
        if not all_nodes:
            return

        thread_specs = [
            (ThreadType.MAIN, self.params.main_thread_count, "TM"),
            (ThreadType.SUBPLOT, self.params.subplot_count, "TS"),
            (ThreadType.CHARACTER_ARC, self.params.character_arc_count, "TC"),
            (ThreadType.RELATIONSHIP_ARC, self.params.relationship_arc_count, "TR"),
            (ThreadType.THEMATIC, self.params.thematic_thread_count, "TT"),
        ]

        thread_counter = 1

        for t_type, count, prefix in thread_specs:
            for _ in range(count):
                thread_id = f"{prefix}{thread_counter:02d}"
                thread_counter += 1

                # 決定線程覆蓋的章節跨度
                if t_type == ThreadType.MAIN:
                    # 主線通常貫穿全書 70%~100%
                    t_start = 1
                    t_end = target_chapters
                elif t_type == ThreadType.THEMATIC:
                    # 主題線跨越全書多個關鍵轉折
                    t_start = 1
                    t_end = target_chapters
                elif t_type == ThreadType.CHARACTER_ARC:
                    # 角色弧線跨越 2 到 8 卷
                    v_span = self.rng.randint(2, max(3, len(graph.volumes)))
                    v_start_idx = self.rng.randint(1, max(1, len(graph.volumes) - v_span + 1))
                    t_start = (v_start_idx - 1) * self.params.chapters_per_volume + 1
                    t_end = min(target_chapters, (v_start_idx + v_span - 1) * self.params.chapters_per_volume)
                else:
                    # 副線或關係線，較局部或中程
                    span_ch = self.rng.randint(15, max(30, target_chapters // 4))
                    t_start = self.rng.randint(1, max(1, target_chapters - span_ch))
                    t_end = min(target_chapters, t_start + span_ch)

                # 從跨度內篩選節點加入線程
                candidate_nodes = [
                    n for n in all_nodes
                    if t_start <= n.chapter_window[0] <= t_end
                ]

                # 採樣節點形成線程序列
                sample_step = max(2, len(candidate_nodes) // self.rng.randint(6, 18))
                selected_nodes = candidate_nodes[::sample_step]

                if len(selected_nodes) < 3:
                    selected_nodes = candidate_nodes[:min(5, len(candidate_nodes))]

                node_seq: List[str] = []
                structural_skeleton: List[StructuralRole] = []

                for idx, node in enumerate(selected_nodes):
                    node_seq.append(node.node_id)

                    # 若節點尚未指派 primary_thread，或是主線，則指派
                    if not node.primary_thread or t_type == ThreadType.MAIN:
                        node.primary_thread = thread_id

                    # 設定線程骨架的預期角色進展
                    if idx == 0:
                        s_role = StructuralRole.OPEN_THREAD
                    elif idx == len(selected_nodes) - 1:
                        s_role = StructuralRole.PAYOFF if t_type in (ThreadType.MAIN, ThreadType.SUBPLOT) else StructuralRole.CLOSE
                    elif idx == len(selected_nodes) - 2 and t_type in (ThreadType.MAIN, ThreadType.SUBPLOT):
                        s_role = StructuralRole.CONVERGE
                    else:
                        s_role = node.structural_role

                    structural_skeleton.append(s_role)

                # 線程內部相鄰節點建立時序推進邊 (CAUSES / ENABLES)
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

    def _ensure_connectivity(self, graph: GeometryGraph) -> None:
        """
        確保全圖無完全孤立的節點。
        若節點既無 incoming 也無 outgoing，連至相鄰章節的節點。
        """
        all_nodes = sorted(graph.nodes.values(), key=lambda n: (n.chapter_window[0], n.node_id))
        for idx, node in enumerate(all_nodes):
            edges = graph.get_edges_for_node(node.node_id, direction="both")
            if not edges:
                # 連接至前一個節點
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
                # 若還有下一個節點，也建立後續連線
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
