# -*- coding: utf-8 -*-
"""
敘事幾何 Motif 庫 (Narrative Geometry Motif Library)

定義 6 種核心 Narrative Geometry Motif，每種 motif 負責產生一組
具有特定敘事結構功能的 GeometryEdge 和（可選的）GeometryNode。

Motif 只處理拓撲結構，不涉及任何語義內容。

6 種 Motif：
  A — 長距離回收 (Long-distance Payoff)
  B — 分岔與合流 (Fork / Rejoin)
  C — 線程交織 (Thread Braid)
  D — 多源匯聚 (Multi-source Convergence)
  E — 角色/情節耦合 (Character-Plot Coupling)
  F — 長距離對比 (Long-distance Contrast)
"""

from __future__ import annotations

import uuid
from random import Random
from typing import TYPE_CHECKING, List, Optional, Tuple

from backend.geometry.models import (
    EdgeType,
    GeometryEdge,
    GeometryNode,
    NodeHierarchy,
    StructuralRole,
)

if TYPE_CHECKING:
    from backend.geometry.models import GeometryGraph


def _edge_id() -> str:
    """產生唯一的 edge ID。"""
    return f"E{uuid.uuid4().hex[:8]}"


def _chapter_distance(source: GeometryNode, target: GeometryNode) -> int:
    """計算兩個 node 之間的章節距離。"""
    return abs(target.chapter_window[0] - source.chapter_window[0])


# ---------------------------------------------------------------------------
# Motif A — 長距離回收 (Long-distance Payoff)
# ---------------------------------------------------------------------------
#
# 模式：
#   SETUP_NODE
#       │ SETS_UP
#       ▼
#   ECHO_NODE_1
#       │ ECHOES
#       ▼
#   ECHO_NODE_2  (可選)
#       │ ECHOES
#       ▼
#   PAYOFF_NODE
#       └── PAYS_OFF (從 SETUP_NODE)
#
# 適用場景：伏筆種植 → 中間提醒 → 最終回收
# ---------------------------------------------------------------------------

def motif_long_distance_payoff(
    setup_node: GeometryNode,
    echo_nodes: List[GeometryNode],
    payoff_node: GeometryNode,
) -> List[GeometryEdge]:
    """
    Motif A — 長距離回收。

    在 setup_node 與 payoff_node 之間建立 SETS_UP → ECHOES → PAYS_OFF 鏈。
    中間的 echo_nodes 逐站 ECHOES 呼應。

    Args:
        setup_node: 伏筆種植節點
        echo_nodes: 中間呼應節點（0-N 個）
        payoff_node: 最終回收節點

    Returns:
        生成的 edge 列表
    """
    edges: List[GeometryEdge] = []

    # SETS_UP: setup → 第一個 echo（若有）或直接到 payoff
    first_target = echo_nodes[0] if echo_nodes else payoff_node
    edges.append(GeometryEdge(
        edge_id=_edge_id(),
        source=setup_node.node_id,
        target=first_target.node_id,
        edge_type=EdgeType.SETS_UP,
        distance=_chapter_distance(setup_node, first_target),
    ))

    # ECHOES chain: echo[i] → echo[i+1]
    for i in range(len(echo_nodes) - 1):
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=echo_nodes[i].node_id,
            target=echo_nodes[i + 1].node_id,
            edge_type=EdgeType.ECHOES,
            distance=_chapter_distance(echo_nodes[i], echo_nodes[i + 1]),
        ))

    # 最後一個 echo → payoff 或 setup 直接到 payoff（若無 echo）
    if echo_nodes:
        last_echo = echo_nodes[-1]
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=last_echo.node_id,
            target=payoff_node.node_id,
            edge_type=EdgeType.ECHOES,
            distance=_chapter_distance(last_echo, payoff_node),
        ))

    # PAYS_OFF: setup → payoff（長距離直連）
    edges.append(GeometryEdge(
        edge_id=_edge_id(),
        source=setup_node.node_id,
        target=payoff_node.node_id,
        edge_type=EdgeType.PAYS_OFF,
        distance=_chapter_distance(setup_node, payoff_node),
    ))

    return edges


# ---------------------------------------------------------------------------
# Motif B — 分岔與合流 (Fork / Rejoin)
# ---------------------------------------------------------------------------
#
# 模式：
#        BRANCH_POINT
#       /             \
#   FORK_A           FORK_B
#      │                │
#   DEV_A            DEV_B
#       \             /
#        MERGE_POINT
#
# 適用場景：故事線分岔後合流，例如兩組人分頭行動後會合
# ---------------------------------------------------------------------------

def motif_fork_rejoin(
    branch_point: GeometryNode,
    fork_chains: List[List[GeometryNode]],
    merge_point: GeometryNode,
) -> List[GeometryEdge]:
    """
    Motif B — 分岔與合流。

    從 branch_point 分成多條分支（fork_chains），每條分支是一系列節點，
    最終所有分支匯合到 merge_point。

    Args:
        branch_point: 分岔起點
        fork_chains: 各分支的節點序列（至少 2 條）
        merge_point: 合流終點

    Returns:
        生成的 edge 列表
    """
    edges: List[GeometryEdge] = []

    for chain in fork_chains:
        if not chain:
            continue

        # branch_point → 分支第一個節點
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=branch_point.node_id,
            target=chain[0].node_id,
            edge_type=EdgeType.ENABLES,
            distance=_chapter_distance(branch_point, chain[0]),
        ))

        # 分支內部鏈式連接
        for i in range(len(chain) - 1):
            edges.append(GeometryEdge(
                edge_id=_edge_id(),
                source=chain[i].node_id,
                target=chain[i + 1].node_id,
                edge_type=EdgeType.CAUSES,
                distance=_chapter_distance(chain[i], chain[i + 1]),
            ))

        # 分支最後一個節點 → merge_point
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=chain[-1].node_id,
            target=merge_point.node_id,
            edge_type=EdgeType.CONVERGES,
            distance=_chapter_distance(chain[-1], merge_point),
        ))

    return edges


# ---------------------------------------------------------------------------
# Motif C — 線程交織 (Thread Braid)
# ---------------------------------------------------------------------------
#
# 模式：
#   T1 ───── A ───────── C ───────── E
#             ╲         ╱
#              ╲       ╱
#   T2 ───────── B ─── D ─────────── F
#
# 兩條 thread 不是只在終點見面，而是彼此多次影響。
# ---------------------------------------------------------------------------

def motif_thread_braid(
    thread_a_nodes: List[GeometryNode],
    thread_b_nodes: List[GeometryNode],
    crossing_pairs: List[Tuple[int, int]],
) -> List[GeometryEdge]:
    """
    Motif C — 線程交織。

    兩條 thread 的節點在指定的 crossing_pairs 位置互相影響。

    Args:
        thread_a_nodes: Thread A 的節點序列
        thread_b_nodes: Thread B 的節點序列
        crossing_pairs: 交叉點索引對 [(a_idx, b_idx), ...]，
                        表示 thread_a_nodes[a_idx] 與 thread_b_nodes[b_idx] 互相影響

    Returns:
        生成的 edge 列表
    """
    edges: List[GeometryEdge] = []

    for a_idx, b_idx in crossing_pairs:
        if a_idx >= len(thread_a_nodes) or b_idx >= len(thread_b_nodes):
            continue

        node_a = thread_a_nodes[a_idx]
        node_b = thread_b_nodes[b_idx]

        # 雙向影響：A → B 和 B → A（用不同的 edge type 區分方向）
        # 按時間順序決定誰影響誰
        if node_a.chapter_window[0] <= node_b.chapter_window[0]:
            edges.append(GeometryEdge(
                edge_id=_edge_id(),
                source=node_a.node_id,
                target=node_b.node_id,
                edge_type=EdgeType.ENABLES,
                distance=_chapter_distance(node_a, node_b),
            ))
        else:
            edges.append(GeometryEdge(
                edge_id=_edge_id(),
                source=node_b.node_id,
                target=node_a.node_id,
                edge_type=EdgeType.ENABLES,
                distance=_chapter_distance(node_b, node_a),
            ))

    return edges


# ---------------------------------------------------------------------------
# Motif D — 多源匯聚 (Multi-source Convergence)
# ---------------------------------------------------------------------------
#
# 模式：
#   T1 ────────┐
#              │
#   T2 ────────┼────→ X (convergence point)
#              │
#   T3 ────────┘
#
# 多條 thread 匯聚到一個關鍵節點
# ---------------------------------------------------------------------------

def motif_multi_source_convergence(
    source_nodes: List[GeometryNode],
    convergence_node: GeometryNode,
) -> List[GeometryEdge]:
    """
    Motif D — 多源匯聚。

    多條 thread 的代表節點匯聚到一個 convergence_node。

    Args:
        source_nodes: 各 thread 的代表節點（至少 2 個）
        convergence_node: 匯聚目標節點

    Returns:
        生成的 edge 列表
    """
    edges: List[GeometryEdge] = []

    for source in source_nodes:
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=source.node_id,
            target=convergence_node.node_id,
            edge_type=EdgeType.CONVERGES,
            distance=_chapter_distance(source, convergence_node),
        ))

    return edges


# ---------------------------------------------------------------------------
# Motif E — 角色/情節耦合 (Character-Plot Coupling)
# ---------------------------------------------------------------------------
#
# 模式：
#   Plot node A
#        │
#        ▼
#   Character state B (CHARACTER_ARC)
#        │
#        ▼
#   Plot decision C (CAUSES)
#        │
#        ▼
#   Relationship D (RELATIONSHIP_CHANGE)
#        │
#        └──────→ Plot E (ENABLES)
#
# 情節事件觸發角色內在變化，角色變化反過來驅動新的情節決策
# ---------------------------------------------------------------------------

def motif_character_plot_coupling(
    plot_trigger: GeometryNode,
    character_state_node: GeometryNode,
    plot_decision_node: GeometryNode,
    relationship_node: Optional[GeometryNode] = None,
    downstream_plot_node: Optional[GeometryNode] = None,
) -> List[GeometryEdge]:
    """
    Motif E — 角色/情節耦合。

    情節事件觸發角色內在變化，角色變化驅動新的情節決策，
    可能影響人際關係，最終推動後續情節。

    Args:
        plot_trigger: 觸發事件的情節節點
        character_state_node: 角色狀態變化節點
        plot_decision_node: 因角色變化而產生的情節決策節點
        relationship_node: （可選）人際關係變化節點
        downstream_plot_node: （可選）後續情節節點

    Returns:
        生成的 edge 列表
    """
    edges: List[GeometryEdge] = []

    # Plot → Character state change
    edges.append(GeometryEdge(
        edge_id=_edge_id(),
        source=plot_trigger.node_id,
        target=character_state_node.node_id,
        edge_type=EdgeType.CHARACTER_ARC,
        distance=_chapter_distance(plot_trigger, character_state_node),
    ))

    # Character state → Plot decision
    edges.append(GeometryEdge(
        edge_id=_edge_id(),
        source=character_state_node.node_id,
        target=plot_decision_node.node_id,
        edge_type=EdgeType.CAUSES,
        distance=_chapter_distance(character_state_node, plot_decision_node),
    ))

    # Plot decision → Relationship change
    if relationship_node:
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=plot_decision_node.node_id,
            target=relationship_node.node_id,
            edge_type=EdgeType.RELATIONSHIP_CHANGE,
            distance=_chapter_distance(plot_decision_node, relationship_node),
        ))

        # Relationship → Downstream plot
        if downstream_plot_node:
            edges.append(GeometryEdge(
                edge_id=_edge_id(),
                source=relationship_node.node_id,
                target=downstream_plot_node.node_id,
                edge_type=EdgeType.ENABLES,
                distance=_chapter_distance(relationship_node, downstream_plot_node),
            ))
    elif downstream_plot_node:
        # 無 relationship node 時直接從 decision → downstream
        edges.append(GeometryEdge(
            edge_id=_edge_id(),
            source=plot_decision_node.node_id,
            target=downstream_plot_node.node_id,
            edge_type=EdgeType.ENABLES,
            distance=_chapter_distance(plot_decision_node, downstream_plot_node),
        ))

    return edges


# ---------------------------------------------------------------------------
# Motif F — 長距離對比 (Long-distance Contrast)
# ---------------------------------------------------------------------------
#
# 模式：
#   A ────────────────── CONTRASTS ────────────────── D
#
# 兩個相距很遠的節點形成主題對比。
# 例如：A = 主角第一次為救陌生人冒險，D = 主角後來為大局犧牲陌生人。
# 程式只知道 A CONTRASTS D，語義由 LLM 填充。
# ---------------------------------------------------------------------------

def motif_long_distance_contrast(
    node_early: GeometryNode,
    node_late: GeometryNode,
) -> GeometryEdge:
    """
    Motif F — 長距離對比。

    在兩個相距較遠的節點之間建立 CONTRASTS 關係。

    Args:
        node_early: 較早的節點
        node_late: 較晚的節點

    Returns:
        單條 CONTRASTS edge
    """
    return GeometryEdge(
        edge_id=_edge_id(),
        source=node_early.node_id,
        target=node_late.node_id,
        edge_type=EdgeType.CONTRASTS,
        distance=_chapter_distance(node_early, node_late),
    )


# ---------------------------------------------------------------------------
# Motif Applicator — 將 motif 批量應用到 GeometryGraph
# ---------------------------------------------------------------------------

class MotifApplicator:
    """
    批量將 Narrative Motif 應用到 GeometryGraph 上。

    根據 GeometryParams 的密度設定，從圖中選取合適的節點，
    按各 motif 的要求生成 cross-thread edges。
    """

    def __init__(self, rng: Random):
        self.rng = rng

    def apply_all_motifs(self, graph: 'GeometryGraph') -> None:
        """
        對已建好 hierarchy 和 thread skeleton 的 graph 應用所有 motif。

        順序：
        1. Motif A — 為每條 thread 建立 setup/echo/payoff chain
        2. Motif B — 在適當的 arc 邊界建立 fork/rejoin
        3. Motif C — 在重疊的 thread 之間建立 braid
        4. Motif D — 在 volume/arc climax 建立 multi-source convergence
        5. Motif E — 為 character_arc thread 建立 character-plot coupling
        6. Motif F — 在全書範圍建立 long-distance contrast pairs
        """
        self._apply_payoff_chains(graph)
        self._apply_fork_rejoin(graph)
        self._apply_thread_braids(graph)
        self._apply_convergence_points(graph)
        self._apply_character_plot_coupling(graph)
        self._apply_contrast_pairs(graph)

    def _apply_payoff_chains(self, graph: 'GeometryGraph') -> None:
        """Motif A: 為每條非 thematic thread 建立 setup → echo → payoff chain。"""
        from backend.geometry.models import ThreadType

        for thread in graph.threads.values():
            if thread.thread_type == ThreadType.THEMATIC:
                continue
            nodes = [graph.get_node(nid) for nid in thread.node_sequence if graph.get_node(nid)]
            if len(nodes) < 3:
                continue

            # 挑選 chain 的節點：第一個作 setup，最後一個作 payoff，中間隨機選 1-3 個作 echo
            setup = nodes[0]
            payoff = nodes[-1]
            middle = nodes[1:-1]
            echo_count = min(len(middle), self.rng.randint(1, 3))
            echoes = sorted(
                self.rng.sample(middle, echo_count),
                key=lambda n: n.chapter_window[0],
            )

            edges = motif_long_distance_payoff(setup, echoes, payoff)
            for edge in edges:
                graph.add_edge(edge)

    def _apply_fork_rejoin(self, graph: 'GeometryGraph') -> None:
        """Motif B: 在 volume 邊界尋找適合的分岔/合流點。"""
        from backend.geometry.models import ThreadType

        # 對每個 volume 的尾端，嘗試從主線建立 fork/rejoin
        volumes = sorted(graph.volumes.values(), key=lambda v: v.volume_index)
        main_threads = [t for t in graph.threads.values()
                        if t.thread_type == ThreadType.MAIN]

        if len(main_threads) < 2:
            return

        # 每隔 2-3 個 volume 嘗試一次 fork/rejoin
        for i in range(0, len(volumes) - 1, self.rng.randint(2, 3)):
            vol = volumes[i]
            next_vol = volumes[min(i + 1, len(volumes) - 1)]

            # 從 vol 的末端找 branch point
            vol_nodes = graph.get_nodes_in_range(vol.chapter_range[0], vol.chapter_range[1])
            if not vol_nodes:
                continue

            branch = self.rng.choice(vol_nodes[-3:]) if len(vol_nodes) >= 3 else vol_nodes[-1]

            # 從 next_vol 的前端找 merge point
            next_vol_nodes = graph.get_nodes_in_range(
                next_vol.chapter_range[0], next_vol.chapter_range[1]
            )
            if not next_vol_nodes:
                continue

            merge = self.rng.choice(next_vol_nodes[:3]) if len(next_vol_nodes) >= 3 else next_vol_nodes[0]

            # 從不同 thread 中各選 1-2 個中間節點作為 fork chains
            fork_chains: List[List[GeometryNode]] = []
            selected_threads = self.rng.sample(
                main_threads, min(2, len(main_threads))
            )
            for t in selected_threads:
                t_nodes = [
                    graph.get_node(nid)
                    for nid in t.node_sequence
                    if graph.get_node(nid)
                    and branch.chapter_window[0] < graph.get_node(nid).chapter_window[0] < merge.chapter_window[0]
                ]
                if t_nodes:
                    fork_chains.append(t_nodes[:2])

            if len(fork_chains) >= 2:
                edges = motif_fork_rejoin(branch, fork_chains, merge)
                for edge in edges:
                    graph.add_edge(edge)

    def _apply_thread_braids(self, graph: 'GeometryGraph') -> None:
        """Motif C: 在重疊區間的 thread 對之間建立交織。"""
        from backend.geometry.models import ThreadType

        threads = [t for t in graph.threads.values()
                   if t.thread_type in (ThreadType.MAIN, ThreadType.SUBPLOT)]

        # 對每對有重疊的 thread，建立 1-3 個交叉點
        for i in range(len(threads)):
            for j in range(i + 1, len(threads)):
                t_a = threads[i]
                t_b = threads[j]

                a_nodes = [graph.get_node(nid) for nid in t_a.node_sequence if graph.get_node(nid)]
                b_nodes = [graph.get_node(nid) for nid in t_b.node_sequence if graph.get_node(nid)]

                if not a_nodes or not b_nodes:
                    continue

                # 檢查章節範圍是否有重疊
                a_start = a_nodes[0].chapter_window[0]
                a_end = a_nodes[-1].chapter_window[1]
                b_start = b_nodes[0].chapter_window[0]
                b_end = b_nodes[-1].chapter_window[1]

                overlap_start = max(a_start, b_start)
                overlap_end = min(a_end, b_end)

                if overlap_end <= overlap_start:
                    continue

                # 在重疊區間內各選 1-2 個節點作交叉
                a_overlap = [idx for idx, n in enumerate(a_nodes)
                             if overlap_start <= n.chapter_window[0] <= overlap_end]
                b_overlap = [idx for idx, n in enumerate(b_nodes)
                             if overlap_start <= n.chapter_window[0] <= overlap_end]

                if not a_overlap or not b_overlap:
                    continue

                cross_count = min(
                    self.rng.randint(1, 2),
                    len(a_overlap),
                    len(b_overlap),
                )
                a_selected = sorted(self.rng.sample(a_overlap, cross_count))
                b_selected = sorted(self.rng.sample(b_overlap, cross_count))
                crossing_pairs = list(zip(a_selected, b_selected))

                edges = motif_thread_braid(a_nodes, b_nodes, crossing_pairs)
                for edge in edges:
                    graph.add_edge(edge)

    def _apply_convergence_points(self, graph: 'GeometryGraph') -> None:
        """Motif D: 在 volume climax 位置建立多源匯聚。"""
        target_count = graph.params.convergence_point_count
        volumes = sorted(graph.volumes.values(), key=lambda v: v.volume_index)

        if not volumes:
            return

        # 在偶數卷或最後一卷建立 convergence
        convergence_indices = list(range(1, len(volumes), max(1, len(volumes) // target_count)))
        if len(convergence_indices) > target_count:
            convergence_indices = self.rng.sample(convergence_indices, target_count)

        for vol_idx in convergence_indices:
            if vol_idx >= len(volumes):
                continue

            vol = volumes[vol_idx]
            vol_nodes = graph.get_nodes_in_range(vol.chapter_range[0], vol.chapter_range[1])

            if len(vol_nodes) < 3:
                continue

            # 選擇卷的 80% 位置附近的節點作為 convergence point
            climax_idx = int(len(vol_nodes) * 0.8)
            convergence_node = vol_nodes[min(climax_idx, len(vol_nodes) - 1)]

            # 從不同 thread 各選一個節點作為 source
            source_threads = set()
            source_nodes = []
            for node in vol_nodes[:climax_idx]:
                if node.primary_thread and node.primary_thread not in source_threads:
                    source_threads.add(node.primary_thread)
                    source_nodes.append(node)
                if len(source_nodes) >= 3:
                    break

            if len(source_nodes) >= 2:
                edges = motif_multi_source_convergence(source_nodes, convergence_node)
                for edge in edges:
                    graph.add_edge(edge)

                # 標記 convergence node 的 structural_role
                convergence_node.structural_role = StructuralRole.CONVERGE

    def _apply_character_plot_coupling(self, graph: 'GeometryGraph') -> None:
        """Motif E: 為 CHARACTER_ARC thread 建立與 plot thread 的耦合。"""
        from backend.geometry.models import ThreadType

        char_threads = [t for t in graph.threads.values()
                        if t.thread_type == ThreadType.CHARACTER_ARC]
        plot_threads = [t for t in graph.threads.values()
                        if t.thread_type in (ThreadType.MAIN, ThreadType.SUBPLOT)]

        if not char_threads or not plot_threads:
            return

        for char_thread in char_threads:
            char_nodes = [graph.get_node(nid) for nid in char_thread.node_sequence
                          if graph.get_node(nid)]
            if len(char_nodes) < 2:
                continue

            # 隨機選一個 plot thread 做耦合
            plot_thread = self.rng.choice(plot_threads)
            plot_nodes = [graph.get_node(nid) for nid in plot_thread.node_sequence
                          if graph.get_node(nid)]
            if len(plot_nodes) < 2:
                continue

            # 選取 coupling 節點：plot trigger, character shift, plot decision
            # 在 character thread 的前半段找 trigger，中間找 shift，後半段找 decision
            if len(char_nodes) >= 3 and len(plot_nodes) >= 3:
                trigger_idx = self.rng.randint(0, len(plot_nodes) // 3)
                char_shift = char_nodes[len(char_nodes) // 2]
                decision_idx = self.rng.randint(len(plot_nodes) * 2 // 3, len(plot_nodes) - 1)

                edges = motif_character_plot_coupling(
                    plot_trigger=plot_nodes[trigger_idx],
                    character_state_node=char_shift,
                    plot_decision_node=plot_nodes[decision_idx],
                )
                for edge in edges:
                    graph.add_edge(edge)

    def _apply_contrast_pairs(self, graph: 'GeometryGraph') -> None:
        """Motif F: 在全書範圍內建立長距離對比。"""
        target_count = graph.params.contrast_pair_count
        all_nodes = sorted(graph.nodes.values(), key=lambda n: n.chapter_window[0])

        if len(all_nodes) < 20:
            return

        total = len(all_nodes)
        # 前 1/3 和後 1/3 各選一個節點形成對比
        first_third = all_nodes[:total // 3]
        last_third = all_nodes[total * 2 // 3:]

        for _ in range(min(target_count, len(first_third), len(last_third))):
            early = self.rng.choice(first_third)
            late = self.rng.choice(last_third)

            # 確保距離足夠遠
            if _chapter_distance(early, late) >= graph.params.target_chapters // 4:
                edge = motif_long_distance_contrast(early, late)
                graph.add_edge(edge)
