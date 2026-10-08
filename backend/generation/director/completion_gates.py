# -*- coding: utf-8 -*-
"""
Master Graph Completion Gates (Phase 2 / Milestone 2 Gatekeeper Engine)
File: backend/generation/director/completion_gates.py

Implements deterministic, DB-factual and graph-topological verification gates:
1. TopologyGate:
   - Validates Causal DAG acyclicity (CAUSES, ENABLES, ESCALATES) using Kahn's topological sort.
   - Allows in-degree=0 start nodes (root story anchors) and out-degree=0 end nodes (final payoffs).
   - Verifies all 24 threads (TM01-TM06, TS01-TS18) have valid traversable pathways.
   - Isolates non-causal edges (ECHOES, PARALLELS, CONTRASTS, SETS_UP, etc.) from cycle checks.
2. ForeshadowingGate:
   - Validates temporal narrative ordering: Plant < Turn < Payoff (by volume index or chapter index).
   - Decoupled from Causal DAG reachability: clues can bridge across independent threads/volumes without requiring causal edges.
   - Validates 100% clue pairing closure (no orphan payoffs, no unclosed plants).
3. TwistGate:
   - Validates 100% 9-dimension event completeness on StoryEventContract for all core/turning/climax nodes.
4. WorldviewGate & CharacterGate:
   - WorldviewGate: validates slot backfill completeness on collision nodes (factions, locations, conflict causes).
   - CharacterGate: validates character slot backfill and enforces de-destined properties (objective baseline properties, no premature destiny spoilers).
5. StoryCompletionGate:
   - Pre-writing ultimate master gate: audits full 24-thread convergence, 100% clue closure, chapter beat coverage, and locks planning_status to STORY_CANON_LOCKED.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Set, Tuple, Union
from collections import deque
from dataclasses import dataclass

from backend.geometry.models import (
    GeometryGraph,
    GeometryNode,
    GeometryEdge,
    EdgeType,
    CAUSAL_EDGE_TYPES,
    NON_CAUSAL_EDGE_TYPES,
    StructuralRole,
    NodeType,
    ForeshadowingDemand,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
    NodeStoryContract,
)
from backend.generation.core.contracts import GateResult


def make_gate_result(
    stage: str,
    passed: bool,
    structural_ok: bool = True,
    quantitative_ok: bool = True,
    referential_ok: bool = True,
    substantive_ok: bool = True,
    defects: Optional[List[str]] = None,
    remediation_hint: str = "",
    metrics: Optional[Dict[str, Any]] = None,
) -> GateResult:
    """Helper factory for creating fully typed GateResult envelopes without missing required arguments."""
    return GateResult(
        stage=stage,
        passed=passed,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=list(defects or []),
        remediation_hint=remediation_hint,
        metrics=dict(metrics or {}),
    )


class TopologyGate:
    """
    拓撲門禁 (Topology Gate)
    驗證因果有向無環圖 (Causal DAG) 之合法性、起訖點邊界條件、非因果邊隔離以及 24 條敘事線程有效通路。
    """

    EXPECTED_MAIN_THREADS = [f"TM{i:02d}" for i in range(1, 7)]   # TM01 - TM06
    EXPECTED_SUB_THREADS = [f"TS{i:02d}" for i in range(1, 19)]   # TS01 - TS18

    @classmethod
    def evaluate(cls, graph: GeometryGraph) -> GateResult:
        defects: List[str] = []

        if not graph.nodes:
            return make_gate_result(
                stage="topology",
                passed=False,
                structural_ok=False,
                quantitative_ok=False,
                referential_ok=False,
                substantive_ok=False,
                defects=["Master Graph 節點集為空，無法執行拓撲門禁驗證"],
                remediation_hint="請先執行 GeometryGenerator 生成骨架圖譜",
            )

        # 1. 因果邊隔離與 Causal DAG 無環驗證 (Kahn 演算法)
        cycle_errors = graph.validate_causal_dag()
        structural_ok = len(cycle_errors) == 0
        if cycle_errors:
            defects.extend(cycle_errors)

        # 2. 端點入度與出度分析 (允許 in-degree=0 起點與 out-degree=0 終點)
        causal_edges = graph.get_causal_edges()
        in_degree: Dict[str, int] = {nid: 0 for nid in graph.nodes}
        out_degree: Dict[str, int] = {nid: 0 for nid in graph.nodes}

        for edge in causal_edges:
            if edge.source in out_degree:
                out_degree[edge.source] += 1
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        start_nodes = [nid for nid, deg in in_degree.items() if deg == 0]
        end_nodes = [nid for nid, deg in out_degree.items() if deg == 0]

        # 孤立節點檢測 (同時無入度無出度且無任何非因果邊)
        orphan_nodes = []
        if len(graph.nodes) > 1:
            for nid in graph.nodes:
                if in_degree[nid] == 0 and out_degree[nid] == 0:
                    connected_edges = graph.get_edges_for_node(nid, "both")
                    if not connected_edges:
                        orphan_nodes.append(nid)

        referential_ok = len(orphan_nodes) == 0
        if orphan_nodes:
            defects.append(
                f"檢測到 {len(orphan_nodes)} 個完全孤立之懸空節點（無任何因果或關聯邊）：{orphan_nodes[:5]}"
            )

        # 3. 24 條敘事線程 (6 主線 TM01-06, 18 支線 TS01-18) 有效通路驗證
        all_expected_threads = cls.EXPECTED_MAIN_THREADS + cls.EXPECTED_SUB_THREADS
        verified_threads: List[str] = []
        broken_thread_errors: List[str] = []

        # 構建有向圖鄰接表以加速通路可達性判定
        adj: Dict[str, Set[str]] = {nid: set() for nid in graph.nodes}
        for e in graph.edges:
            if e.source in adj and e.target in graph.nodes:
                adj[e.source].add(e.target)

        for tid in all_expected_threads:
            thread = graph.threads.get(tid)
            if not thread:
                broken_thread_errors.append(f"缺少必要線程骨架定義: {tid}")
                continue

            node_seq = thread.node_sequence
            if not node_seq or len(node_seq) < 2:
                broken_thread_errors.append(f"線程 {tid} 節點序列過短 (len={len(node_seq)})")
                continue

            missing_in_graph = [nid for nid in node_seq if nid not in graph.nodes]
            if missing_in_graph:
                broken_thread_errors.append(f"線程 {tid} 引用了不存在的節點: {missing_in_graph}")
                continue

            pathway_intact = True
            for i in range(len(node_seq) - 1):
                u = node_seq[i]
                v = node_seq[i + 1]
                if v in adj[u]:
                    continue
                if not cls._is_reachable(adj, u, v, max_depth=20):
                    pathway_intact = False
                    broken_thread_errors.append(
                        f"線程 {tid} 敘事通路中斷：節點 {u} 無法到達下個序列節點 {v}"
                    )
                    break

            if pathway_intact and not missing_in_graph:
                verified_threads.append(tid)

        quantitative_ok = len(verified_threads) >= len(all_expected_threads)
        if broken_thread_errors:
            defects.extend(broken_thread_errors)

        substantive_ok = len(graph.nodes) >= 10 and len(graph.edges) >= 10
        passed = structural_ok and quantitative_ok and referential_ok and substantive_ok and len(defects) == 0

        metrics = {
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "causal_edges": len(causal_edges),
            "non_causal_edges": len(graph.edges) - len(causal_edges),
            "start_nodes_count": len(start_nodes),
            "end_nodes_count": len(end_nodes),
            "orphan_nodes_count": len(orphan_nodes),
            "total_threads_count": len(graph.threads),
            "expected_24_threads_count": len(all_expected_threads),
            "verified_24_threads_count": len(verified_threads),
            "cycle_errors_count": len(cycle_errors),
        }

        remediation_hint = ""
        if not passed:
            remediation_hint = f"拓撲校驗未通過。請檢視因果無環約束與 24 條線程 ({len(broken_thread_errors)} 項線程缺陷)。"

        return make_gate_result(
            stage="topology",
            passed=passed,
            structural_ok=structural_ok,
            quantitative_ok=quantitative_ok,
            referential_ok=referential_ok,
            substantive_ok=substantive_ok,
            defects=defects,
            remediation_hint=remediation_hint,
            metrics=metrics,
        )

    @staticmethod
    def _is_reachable(adj: Dict[str, Set[str]], start: str, target: str, max_depth: int = 20) -> bool:
        """輕量 BFS 有向圖路徑可達性檢測"""
        if start == target:
            return True
        visited = {start}
        queue = deque([(start, 0)])
        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for nxt in adj.get(curr, ()):
                if nxt == target:
                    return True
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, depth + 1))
        return False


@dataclass
class ClueRecord:
    clue_id: str
    node_id: str
    role: str               # "PLANT", "TURN", "PAYOFF"
    volume_index: int
    arc_index: int
    chapter_index: Optional[int]
    beat_index: int
    summary: str = ""


class ForeshadowingGate:
    """
    伏筆門禁 (Foreshadowing Gate)
    驗證敘事時序 (Plant < Turn < Payoff) 與線索配對閉環。
    與因果 DAG 可達性完全解耦：伏筆跨卷跨線埋設回收無需因果連線。
    """

    @classmethod
    def evaluate(
        cls,
        graph: GeometryGraph,
        chapter_outlines: Optional[List[Dict[str, Any]]] = None,
    ) -> GateResult:
        defects: List[str] = []
        clue_records = cls._extract_clue_records(graph, chapter_outlines)

        if not clue_records:
            nodes_with_demand = [
                n.node_id for n in graph.nodes.values()
                if getattr(n, "foreshadowing_demand", ForeshadowingDemand.NONE) != ForeshadowingDemand.NONE
            ]
            if nodes_with_demand:
                defects.append(
                    f"圖中存在 {len(nodes_with_demand)} 個節點標註了伏筆需求，但尚未回填任何具體線索記錄"
                )
                return make_gate_result(
                    stage="foreshadowing",
                    passed=False,
                    structural_ok=False,
                    quantitative_ok=False,
                    referential_ok=False,
                    substantive_ok=False,
                    defects=defects,
                    remediation_hint="請呼叫 Foreshadowing Orchestrator 回填伏筆任務",
                    metrics={"total_clues": 0, "closed_clues": 0},
                )
            else:
                return make_gate_result(
                    stage="foreshadowing",
                    passed=True,
                    structural_ok=True,
                    quantitative_ok=True,
                    referential_ok=True,
                    substantive_ok=True,
                    metrics={"total_clues": 0, "closed_clues": 0, "closure_rate": 1.0},
                )

        by_clue: Dict[str, List[ClueRecord]] = {}
        for rec in clue_records:
            by_clue.setdefault(rec.clue_id, []).append(rec)

        closed_count = 0
        unclosed_count = 0
        orphan_payoff_count = 0
        temporal_violations_count = 0

        for clue_id, records in by_clue.items():
            plants = [r for r in records if r.role == "PLANT"]
            turns = [r for r in records if r.role == "TURN"]
            payoffs = [r for r in records if r.role == "PAYOFF"]

            # (A) 線索配對閉環校驗
            if payoffs and not plants:
                orphan_payoff_count += 1
                defects.append(
                    f"線索 [{clue_id}] 存在回收節點 {[p.node_id for p in payoffs]} 但缺少埋設 (Plant) 節點（孤立回收）"
                )
                continue

            if plants and not payoffs:
                unclosed_count += 1
                defects.append(
                    f"線索 [{clue_id}] 於節點 {[p.node_id for p in plants]} 埋設，但全書未見任何回收 (Payoff) 節點（未閉環）"
                )
                continue

            # (B) 敘事時序校驗 (Plant < Turn < Payoff)
            has_temporal_defect = False
            earliest_plant = min(plants, key=lambda p: cls._get_temporal_key(p))
            latest_plant = max(plants, key=lambda p: cls._get_temporal_key(p))
            earliest_payoff = min(payoffs, key=lambda y: cls._get_temporal_key(y))
            latest_payoff = max(payoffs, key=lambda y: cls._get_temporal_key(y))

            p_early_key = cls._get_temporal_key(earliest_plant)
            y_early_key = cls._get_temporal_key(earliest_payoff)

            if y_early_key <= p_early_key:
                has_temporal_defect = True
                temporal_violations_count += 1
                defects.append(
                    f"線索 [{clue_id}] 敘事時序倒置：最早回收節點 {earliest_payoff.node_id} (時序 {y_early_key}) 早於或等於最早埋設節點 {earliest_plant.node_id} (時序 {p_early_key})"
                )

            for t in turns:
                t_order = cls._get_temporal_key(t)
                if not (p_early_key < t_order < cls._get_temporal_key(latest_payoff)):
                    has_temporal_defect = True
                    temporal_violations_count += 1
                    defects.append(
                        f"線索 [{clue_id}] 三段式轉折時序違規：轉折節點 {t.node_id} (時序 {t_order}) 未介於最早埋設 {earliest_plant.node_id} ({p_early_key}) 與回收之間"
                    )

            if not has_temporal_defect and plants and payoffs:
                closed_count += 1

        total_clues = len(by_clue)
        closure_rate = closed_count / max(1, total_clues)
        passed = (len(defects) == 0) and (closure_rate == 1.0)

        metrics = {
            "total_clues": total_clues,
            "closed_clues": closed_count,
            "unclosed_clues": unclosed_count,
            "orphan_payoffs": orphan_payoff_count,
            "temporal_violations": temporal_violations_count,
            "closure_rate": closure_rate,
        }

        remediation_hint = ""
        if not passed:
            remediation_hint = f"伏筆閉環與時序校驗失敗。共 {len(defects)} 項缺陷（未閉環: {unclosed_count}, 孤立回收: {orphan_payoff_count}, 時序倒置: {temporal_violations_count}）。"

        return make_gate_result(
            stage="foreshadowing",
            passed=passed,
            structural_ok=(temporal_violations_count == 0),
            quantitative_ok=(closure_rate == 1.0),
            referential_ok=(orphan_payoff_count == 0),
            substantive_ok=(closed_count > 0 or total_clues == 0),
            defects=defects,
            remediation_hint=remediation_hint,
            metrics=metrics,
        )

    @classmethod
    def _extract_clue_records(
        cls,
        graph: GeometryGraph,
        chapter_outlines: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ClueRecord]:
        records: List[ClueRecord] = []

        outline_ch_map: Dict[str, int] = {}
        if chapter_outlines:
            for out in chapter_outlines:
                ch_idx = out.get("chapter_index") or out.get("chapter")
                for nid in out.get("node_ids", []):
                    if ch_idx is not None:
                        outline_ch_map[nid] = int(ch_idx)

        for nid, node in graph.nodes.items():
            contract = node.story_contract or graph.story_contracts.get(nid)
            v_idx = node.hierarchy.volume_index if node.hierarchy else 1
            a_idx = node.hierarchy.arc_index if node.hierarchy else 1
            beat_idx = node.metadata.get("beat_index", 0)

            ch_idx = outline_ch_map.get(nid)
            if ch_idx is None and node.chapter_window and node.chapter_window[0] > 0:
                ch_idx = node.chapter_window[0]
            if ch_idx is None and contract and contract.chapter_mappings:
                for cm in contract.chapter_mappings:
                    if "chapter_index" in cm:
                        ch_idx = cm["chapter_index"]
                        break

            # 1. 檢查 contract.foreshadowing_tasks
            tasks = []
            if contract and contract.foreshadowing_tasks:
                tasks.extend(contract.foreshadowing_tasks)
            elif "foreshadowing_tasks" in node.metadata:
                tasks.extend(node.metadata["foreshadowing_tasks"])

            for task in tasks:
                cid = task.get("clue_id") or task.get("foreshadowing_id")
                if not cid:
                    continue
                raw_role = str(task.get("role") or task.get("task_type", "")).upper()
                if "PLANT" in raw_role or "SEED" in raw_role or "SETUP" in raw_role:
                    role = "PLANT"
                elif "TURN" in raw_role or "TWIST" in raw_role:
                    role = "TURN"
                elif "PAYOFF" in raw_role or "REVEAL" in raw_role or "CLOSE" in raw_role:
                    role = "PAYOFF"
                else:
                    role = "PLANT"

                task_ch_idx = task.get("chapter_index")
                effective_ch_idx = task_ch_idx if task_ch_idx is not None else ch_idx

                records.append(ClueRecord(
                    clue_id=cid,
                    node_id=nid,
                    role=role,
                    volume_index=v_idx,
                    arc_index=a_idx,
                    chapter_index=effective_ch_idx,
                    beat_index=beat_idx,
                    summary=task.get("summary", ""),
                ))

        return records

    @staticmethod
    def _get_temporal_key(rec: ClueRecord) -> Tuple[int, int, int]:
        if rec.chapter_index is not None and rec.chapter_index > 0:
            return (rec.chapter_index, rec.beat_index, 0)
        return (rec.volume_index, rec.arc_index, rec.beat_index)


class TwistGate:
    """
    轉折門禁 (Twist Gate)
    嚴格核查所有核心劇情、轉折點與高潮節點 (Core / Turning / Climax Nodes)，
    要求其 StoryEventContract 必須 100% 填滿九大維度。
    """

    CORE_STRUCTURAL_ROLES = {
        StructuralRole.OPEN_THREAD,
        StructuralRole.CONVERGE,
        StructuralRole.PAYOFF,
        StructuralRole.BRANCH,
        StructuralRole.CHARACTER_SHIFT,
    }

    CORE_NODE_TYPES = {
        NodeType.CRISIS,
        NodeType.CLIMAX,
        NodeType.TURNING_POINT,
        NodeType.SECRET_REVEAL,
        NodeType.TRANSFORMATION,
    }

    @classmethod
    def evaluate(cls, graph: GeometryGraph, strict: bool = True) -> GateResult:
        defects: List[str] = []

        if not graph.nodes:
            return make_gate_result(
                stage="twist",
                passed=False,
                structural_ok=False,
                quantitative_ok=False,
                referential_ok=False,
                substantive_ok=False,
                defects=["Master Graph 節點集為空，無法執行轉折門禁驗證"],
            )

        core_nodes: List[GeometryNode] = []
        for nid, node in graph.nodes.items():
            if cls.is_core_node(node):
                core_nodes.append(node)

        if not core_nodes:
            core_nodes = [n for n in graph.nodes.values() if n.importance >= 0.6]

        total_core = len(core_nodes)
        passed_core = 0
        total_events_checked = 0

        for node in core_nodes:
            nid = node.node_id
            contract = node.story_contract or graph.story_contracts.get(nid)

            if not contract:
                defects.append(f"核心節點 {nid} 缺少 NodeStoryContract 實體")
                continue

            if not contract.story_events:
                defects.append(
                    f"核心節點 {nid} (role={node.structural_role}, type={node.node_type}) 的 story_events 為空，未填入九維故事事件"
                )
                continue

            node_events_ok = True
            for ev in contract.story_events:
                total_events_checked += 1
                if not isinstance(ev, StoryEventContract):
                    defects.append(f"節點 {nid} 包含非法的事件物件類型：{type(ev)}")
                    node_events_ok = False
                    continue

                is_complete, dimension_defects = ev.validate_nine_dimensions(strict=strict)
                if not is_complete:
                    node_events_ok = False
                    for d_err in dimension_defects:
                        defects.append(f"核心節點 {nid} 事件 [{ev.event_id}] 九維合約不完備: {d_err}")

            if node_events_ok:
                passed_core += 1

        completion_rate = passed_core / max(1, total_core)
        passed = (len(defects) == 0) and (completion_rate == 1.0)

        metrics = {
            "core_nodes_total": total_core,
            "core_nodes_passed": passed_core,
            "core_completion_rate": completion_rate,
            "total_events_checked": total_events_checked,
            "defects_count": len(defects),
            "strict_mode": strict,
        }

        remediation_hint = ""
        if not passed:
            remediation_hint = f"轉折與核心劇情門禁未通過。尚有 {total_core - passed_core} 個核心節點未達 100% 九維完備性。"

        return make_gate_result(
            stage="twist",
            passed=passed,
            structural_ok=(total_events_checked > 0),
            quantitative_ok=(completion_rate == 1.0),
            referential_ok=(len(defects) == 0),
            substantive_ok=(passed_core > 0),
            defects=defects,
            remediation_hint=remediation_hint,
            metrics=metrics,
        )

    @classmethod
    def is_core_node(cls, node: GeometryNode) -> bool:
        if node.importance >= 0.75:
            return True
        meta = node.metadata or {}
        if meta.get("is_climax_candidate") or meta.get("is_core") or meta.get("is_turning_point"):
            return True
        if node.node_type in cls.CORE_NODE_TYPES:
            return True
        if node.structural_role in cls.CORE_STRUCTURAL_ROLES:
            return True
        return False


class WorldviewGate:
    """
    世界觀門禁 (Worldview Gate)
    驗證碰撞節點 (Faction Collision Nodes) 與重要結構節點的世界觀槽位 (worldview_slot) 回填完備性。
    包含勢力陣營、地理位置與衝突誘因。
    """

    @classmethod
    def evaluate(cls, graph: GeometryGraph) -> GateResult:
        defects: List[str] = []

        if not graph.nodes:
            return make_gate_result(stage="worldview", passed=False, defects=["節點集為空"])

        collision_nodes = []
        for nid, node in graph.nodes.items():
            if cls._is_collision_node(node):
                collision_nodes.append(node)

        if not collision_nodes:
            collision_nodes = [n for n in graph.nodes.values() if n.importance >= 0.6]

        total_collision = len(collision_nodes)
        filled_count = 0

        for node in collision_nodes:
            nid = node.node_id
            contract = node.story_contract or graph.story_contracts.get(nid)
            slot = contract.worldview_slot if contract else node.semantic

            if not slot or not isinstance(slot, dict):
                defects.append(f"碰撞節點 {nid} (type={node.node_type}) 尚未回填 worldview_slot")
                continue

            has_faction = bool(slot.get("faction_ids") or slot.get("factions") or slot.get("participating_factions"))
            has_location = bool(slot.get("location_id") or slot.get("location") or slot.get("scene_location"))
            has_cause = bool(slot.get("conflict_cause") or slot.get("lore_trigger") or slot.get("conflict_reason"))

            missing_fields = []
            if not has_faction:
                missing_fields.append("faction_ids (衝突勢力)")
            if not has_location:
                missing_fields.append("location_id (地勢場景)")
            if not has_cause:
                missing_fields.append("conflict_cause (碰撞誘因)")

            if missing_fields:
                defects.append(f"節點 {nid} worldview_slot 缺少欄位: {', '.join(missing_fields)}")
            else:
                filled_count += 1

        backfill_rate = filled_count / max(1, total_collision)
        passed = (len(defects) == 0) and (backfill_rate == 1.0)

        metrics = {
            "total_collision_nodes": total_collision,
            "filled_collision_nodes": filled_count,
            "worldview_backfill_rate": backfill_rate,
            "defects_count": len(defects),
        }

        remediation_hint = ""
        if not passed:
            remediation_hint = f"世界觀槽位回填未達 100%。尚有 {total_collision - filled_count} 個碰撞節點未回填。"

        return make_gate_result(
            stage="worldview",
            passed=passed,
            structural_ok=True,
            quantitative_ok=(backfill_rate == 1.0),
            referential_ok=(len(defects) == 0),
            substantive_ok=(filled_count > 0),
            defects=defects,
            remediation_hint=remediation_hint,
            metrics=metrics,
        )

    @staticmethod
    def _is_collision_node(node: GeometryNode) -> bool:
        return (
            node.node_type == NodeType.FACTION_COLLISION
            or len(getattr(node, "thread_memberships", [])) >= 2
            or node.structural_role in (StructuralRole.OPEN_THREAD, StructuralRole.CONVERGE)
        )


class CharacterGate:
    """
    角色門禁 (Character Gate)
    驗證角色槽位 (character_slots) 回填完備性與「去命運化 (De-destined)」客觀屬性準則。
    嚴禁 Stage 04 角色初始資料預先洩露未來生死或背叛劇透。
    """

    TERMINAL_STATUS_SPOILERS = {
        "DEAD", "KILLED", "DECEASED", "BETRAYED", "FALLEN", "CORRUPTED", "SLAIN"
    }
    SPOILER_METADATA_KEYS = {
        "destined_death", "will_betray", "future_fate", "spoiler_death_chapter", "destiny_ending"
    }

    @classmethod
    def evaluate(cls, graph: GeometryGraph, min_roster_count: Optional[int] = None) -> GateResult:
        defects: List[str] = []

        if not graph.nodes:
            return make_gate_result(stage="characters", passed=False, defects=["節點集為空"])

        total_nodes = len(graph.nodes)
        nodes_with_slots = 0
        total_slot_entries = 0
        unique_characters: Set[str] = set()
        spoiler_violations = 0

        for nid, node in graph.nodes.items():
            contract = node.story_contract or graph.story_contracts.get(nid)
            slots = contract.character_slots if contract else node.metadata.get("character_slots", [])

            if slots:
                nodes_with_slots += 1
                for s in slots:
                    total_slot_entries += 1
                    cid = s.get("character_id") or s.get("char_id")
                    if cid:
                        unique_characters.add(cid)

                    if not cid:
                        defects.append(f"節點 {nid} character_slot 缺少 character_id")
                    if not s.get("role_in_node"):
                        defects.append(f"節點 {nid} 角色 [{cid}] 缺少 role_in_node")

                    # 去命運化 (De-destined) 無劇透校驗
                    initial_status = str(s.get("initial_status", "")).upper()
                    if initial_status in cls.TERMINAL_STATUS_SPOILERS:
                        spoiler_violations += 1
                        defects.append(
                            f"節點 {nid} 角色 [{cid}] 違反去命運化原則：初始狀態包含終局劇透狀態 '{initial_status}'"
                        )

                    for sp_key in cls.SPOILER_METADATA_KEYS:
                        if sp_key in s:
                            spoiler_violations += 1
                            defects.append(
                                f"節點 {nid} 角色 [{cid}] 違反無劇透原則：包含命運預言欄位 '{sp_key}'"
                            )

        target_roster = min_roster_count
        if target_roster is None:
            vol_count = len(graph.volumes) if graph.volumes else 10
            target_roster = max(10, min(70, vol_count * 7))

        roster_ok = len(unique_characters) >= target_roster
        if not roster_ok:
            defects.append(
                f"角色群像規模不足：當前獨立角色數 {len(unique_characters)} 未達預期目標 {target_roster}"
            )

        passed = (len(defects) == 0) and (spoiler_violations == 0) and (nodes_with_slots > 0)

        metrics = {
            "total_nodes": total_nodes,
            "nodes_with_character_slots": nodes_with_slots,
            "total_character_slot_entries": total_slot_entries,
            "unique_characters_count": len(unique_characters),
            "target_roster_count": target_roster,
            "spoiler_violations_count": spoiler_violations,
            "de_destined_compliance": (spoiler_violations == 0),
        }

        remediation_hint = ""
        if not passed:
            remediation_hint = f"角色門禁未通過（群像規模: {len(unique_characters)}/{target_roster}, 劇透違規: {spoiler_violations}）。"

        return make_gate_result(
            stage="characters",
            passed=passed,
            structural_ok=(spoiler_violations == 0),
            quantitative_ok=roster_ok,
            referential_ok=(nodes_with_slots > 0),
            substantive_ok=(len(unique_characters) > 0),
            defects=defects,
            remediation_hint=remediation_hint,
            metrics=metrics,
        )


class StoryCompletionGate:
    """
    全書完備性終極門禁 (Story Completion Gate - Stage 08)
    在正式動筆寫作 (Writer Stage 09) 前的全域終極驗收。
    驗收四大核心指標：
    1. 24 條敘事線程 (6 主線 + 18 支線) 100% 收束匯聚。
    2. 100% 伏筆線索配對閉環 (0 未結線索、0 孤立回收)。
    3. 章節拍點 (NODE_CHAPTER_BEATS) 100% 覆蓋所有幾何節點。
    4. 所有前置門禁 (Topology, Foreshadowing, Twist, Worldview, Character) 全部通過。
    驗收通過後，正式將整圖節點鎖定為 STORY_CANON_LOCKED。
    """

    @classmethod
    def evaluate(
        cls,
        graph: GeometryGraph,
        chapter_outlines: Optional[List[Dict[str, Any]]] = None,
        auto_lock: bool = True,
        strict_twist: bool = True,
        min_roster_count: Optional[int] = None,
    ) -> GateResult:
        defects: List[str] = []
        sub_gate_results: Dict[str, GateResult] = {}

        if not graph.nodes:
            return make_gate_result(stage="story_completion", passed=False, defects=["節點集為空"])

        # 1. 執行並彙整所有子門禁
        topo_res = TopologyGate.evaluate(graph)
        sub_gate_results["topology"] = topo_res
        if not topo_res.passed:
            defects.extend([f"[TopologyGate] {d}" for d in topo_res.defects])

        fsh_res = ForeshadowingGate.evaluate(graph, chapter_outlines)
        sub_gate_results["foreshadowing"] = fsh_res
        if not fsh_res.passed:
            defects.extend([f"[ForeshadowingGate] {d}" for d in fsh_res.defects])

        twist_res = TwistGate.evaluate(graph, strict=strict_twist)
        sub_gate_results["twist"] = twist_res
        if not twist_res.passed:
            defects.extend([f"[TwistGate] {d}" for d in twist_res.defects])

        wv_res = WorldviewGate.evaluate(graph)
        sub_gate_results["worldview"] = wv_res
        if not wv_res.passed:
            defects.extend([f"[WorldviewGate] {d}" for d in wv_res.defects])

        char_res = CharacterGate.evaluate(graph, min_roster_count=min_roster_count)
        sub_gate_results["characters"] = char_res
        if not char_res.passed:
            defects.extend([f"[CharacterGate] {d}" for d in char_res.defects])

        # 2. 全 24 線程收束匯聚審計 (Thread Convergence Audit)
        expected_24 = [f"TM{i:02d}" for i in range(1, 7)] + [f"TS{i:02d}" for i in range(1, 19)]
        unconverged_threads = []

        terminal_roles = {StructuralRole.CONVERGE, StructuralRole.PAYOFF, StructuralRole.CLOSE}
        for tid in expected_24:
            thread = graph.threads.get(tid)
            if not thread or not thread.node_sequence:
                unconverged_threads.append(tid)
                continue

            last_node_id = thread.node_sequence[-1]
            last_node = graph.get_node(last_node_id)
            if not last_node:
                unconverged_threads.append(tid)
                continue

            has_terminal_role = (
                (bool(thread.structural_skeleton) and thread.structural_skeleton[-1] in terminal_roles)
                or last_node.structural_role in terminal_roles
                or (last_node.story_contract and last_node.story_contract.structural_role in terminal_roles)
            )
            if not has_terminal_role:
                unconverged_threads.append(tid)

        threads_converged_ok = len(unconverged_threads) == 0
        if unconverged_threads:
            defects.append(
                f"24 條敘事線程中有 {len(unconverged_threads)} 條尚未收束匯聚：{unconverged_threads}"
            )

        # 3. 章節拍點全覆蓋審計 (Chapter Beat Coverage Audit)
        unmapped_nodes = []
        outline_covered_nids = set()
        if chapter_outlines:
            for out in chapter_outlines:
                for nid in out.get("node_ids", []):
                    outline_covered_nids.add(nid)

        for nid, node in graph.nodes.items():
            contract = node.story_contract or graph.story_contracts.get(nid)
            has_mapping = False

            if nid in outline_covered_nids:
                has_mapping = True
            elif contract and contract.chapter_mappings:
                has_mapping = True
            elif node.chapter_window and node.chapter_window[0] > 0 and node.chapter_window[1] > 0:
                has_mapping = True

            if not has_mapping:
                unmapped_nodes.append(nid)

        chapter_coverage_ok = len(unmapped_nodes) == 0
        if unmapped_nodes:
            defects.append(
                f"全書有 {len(unmapped_nodes)} 個節點未映射至任何章節拍點 (NODE_CHAPTER_BEATS)：{unmapped_nodes[:5]}"
            )

        # 4. 決策與鎖定 STORY_CANON_LOCKED
        all_sub_gates_passed = all(r.passed for r in sub_gate_results.values())
        passed = all_sub_gates_passed and threads_converged_ok and chapter_coverage_ok and len(defects) == 0

        canon_locked = False
        if passed and auto_lock:
            cls._lock_story_canon(graph)
            canon_locked = True

        metrics = {
            "all_sub_gates_passed": all_sub_gates_passed,
            "threads_converged_count": len(expected_24) - len(unconverged_threads),
            "total_threads_audited": len(expected_24),
            "unconverged_threads": unconverged_threads,
            "chapter_coverage_rate": (len(graph.nodes) - len(unmapped_nodes)) / max(1, len(graph.nodes)),
            "unmapped_nodes_count": len(unmapped_nodes),
            "canon_locked": canon_locked,
            "sub_gate_metrics": {k: v.metrics for k, v in sub_gate_results.items()},
        }

        remediation_hint = ""
        if not passed:
            remediation_hint = f"全書完備性門禁審計未通過（缺陷數: {len(defects)}）。無法鎖定 STORY_CANON_LOCKED。"

        return make_gate_result(
            stage="story_completion",
            passed=passed,
            structural_ok=threads_converged_ok,
            quantitative_ok=(len(unconverged_threads) == 0 and len(unmapped_nodes) == 0),
            referential_ok=chapter_coverage_ok,
            substantive_ok=all_sub_gates_passed,
            defects=defects,
            remediation_hint=remediation_hint,
            metrics=metrics,
        )

    @classmethod
    def _lock_story_canon(cls, graph: GeometryGraph) -> None:
        """
        將整張 Master Graph 與所有節點狀態原子鎖定為 STORY_CANON_LOCKED。
        標誌著全書架構正式確立，轉交下游 Writer 施工。
        """
        graph.planning_status = PlanningStatus.STORY_CANON_LOCKED

        for nid, node in graph.nodes.items():
            node.planning_status = PlanningStatus.STORY_CANON_LOCKED
            if node.metadata is not None:
                node.metadata["planning_status"] = PlanningStatus.STORY_CANON_LOCKED.value

            contract = node.story_contract or graph.story_contracts.get(nid)
            if contract:
                contract.planning_status = PlanningStatus.STORY_CANON_LOCKED
                node.metadata["_story_contract"] = contract.to_dict()
                graph.story_contracts[nid] = contract


__all__ = [
    "make_gate_result",
    "TopologyGate",
    "ClueRecord",
    "ForeshadowingGate",
    "TwistGate",
    "WorldviewGate",
    "CharacterGate",
    "StoryCompletionGate",
]
