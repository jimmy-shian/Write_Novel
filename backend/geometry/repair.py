# -*- coding: utf-8 -*-
"""
幾何修復引擎 (Geometry Repair Engine)

根據 vNext 架構定義，在故事編排或總監審核時，如果發現既有幾何框架
無法容納充實的劇情推進，必須經過嚴格判定後，才能調用 Repair 操作調整幾何結構。

【重大判定準則（Gatekeeper Rules）】
只有符合以下 4 種情況之一，才允許透過 Repair 工具調整或增加幾何節點；
否則一律不准更動結構，改走既有的 evaluate_output / supplement_content 打回重寫：
  1. 密度超載 (DENSITY_OVERLOAD):
     - 1 個骨架節點要塞 >=3 個 turning_points，或 >=4 個 plant/payoff，
     - 或 1 章要寫完 2 個場景跳躍 + 1 個人物轉折。
  2. 因果斷層 (CAUSAL_GAP):
     - A -> C 中間缺 B，沒有 B 讀者看不懂，必須 INSERT 橋接章。
  3. 收束撞車 (CONVERGENCE_COLLISION):
     - 同卷要收 >=2 條大線 + 卷末高潮，3 節點收不完，必須 EXPAND 3 -> 5。
  4. 章數膨脹 (CHAPTER_EXPANSION):
     - volume.chapter_count 需要調整，全書 chapter_index 連續性需要平移重排。

【支援的 4 種修復操作 (RepairOperation)】:
  - SPLIT: 單節點拆分成 2 或 3 個子節點 (1 -> 2/3)
  - EXPAND: 節點群擴增 (例如 3 -> 5)
  - INSERT: 插入橋接章節點，後續章號自動順延
  - COMPRESS: 水章/冗餘節點壓縮合併
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.geometry.models import (
    EdgeType,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    NodeHierarchy,
    RepairOperation,
    RepairProposal,
    StructuralRole,
)


class GeometryRepairCondition(str, Enum):
    """允許調用幾何修復的 4 大重大條件"""
    DENSITY_OVERLOAD = "DENSITY_OVERLOAD"              # 密度超載 (1 -> 2/3)
    CAUSAL_GAP = "CAUSAL_GAP"                          # 因果斷層 (INSERT 橋接)
    CONVERGENCE_COLLISION = "CONVERGENCE_COLLISION"    # 收束撞車 (EXPAND 3 -> 5)
    CHAPTER_EXPANSION = "CHAPTER_EXPANSION"            # 章數膨脹 (平移順延)


@dataclass
class GeometryRepairResult:
    """修復執行結果"""
    success: bool
    operation: RepairOperation
    condition: Optional[GeometryRepairCondition]
    affected_nodes: List[str] = field(default_factory=list)
    new_nodes: List[str] = field(default_factory=list)
    removed_nodes: List[str] = field(default_factory=list)
    chapter_delta: int = 0
    message: str = ""


class GeometryRepairGatekeeper:
    """
    幾何修復門禁判定器。
    驗證請求是否真正符合 4 大重大條件，杜絕隨意加節點破壞拓撲骨架。
    """

    @staticmethod
    def verify_condition(
        condition: GeometryRepairCondition,
        context: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        校驗是否滿足指定的門禁條件。
        context 提供校驗所需的指標數據。
        """
        if condition == GeometryRepairCondition.DENSITY_OVERLOAD:
            tp_count = context.get("turning_points_count", 0)
            foreshadow_count = context.get("foreshadowing_tasks_count", 0)
            scene_jumps = context.get("scene_jumps_count", 0)
            char_arcs = context.get("character_turns_count", 0)

            if tp_count >= 3:
                return True, f"符合密度超載：單一節點包含 {tp_count} 個轉折點 (門檻 >=3)"
            if foreshadow_count >= 4:
                return True, f"符合密度超載：單一節點包含 {foreshadow_count} 個伏筆任務 (門檻 >=4)"
            if scene_jumps >= 2 and char_arcs >= 1:
                return True, f"符合密度超載：單章包含 {scene_jumps} 次場景跳躍與 {char_arcs} 個人物轉折"

            return False, "未達密度超載門檻（需滿足 >=3 turning_points 或 >=4伏筆 或 2場景跳躍+1人物轉折）"

        elif condition == GeometryRepairCondition.CAUSAL_GAP:
            gap_detected = context.get("causal_gap_detected", False)
            missing_cause = context.get("missing_cause_description", "")
            if gap_detected and missing_cause:
                return True, f"符合因果斷層：缺少必要因果鏈接「{missing_cause}」"
            return False, "未提供明確的因果斷層證據與缺失事件說明"

        elif condition == GeometryRepairCondition.CONVERGENCE_COLLISION:
            converging_threads = context.get("converging_threads_count", 0)
            has_volume_climax = context.get("has_volume_climax", False)
            available_nodes = context.get("available_nodes_count", 3)

            if converging_threads >= 2 and has_volume_climax and available_nodes <= 3:
                return True, f"符合收束撞車：同卷需收 {converging_threads} 條大線並處理卷末高潮，{available_nodes} 個節點不足"
            return False, "未達收束撞車門檻（需同卷 >=2 條大線 + 卷末高潮且目前節點 <=3）"

        elif condition == GeometryRepairCondition.CHAPTER_EXPANSION:
            new_chapter_count = context.get("new_chapter_count")
            current_chapter_count = context.get("current_chapter_count")
            if new_chapter_count and current_chapter_count and new_chapter_count != current_chapter_count:
                return True, f"符合章數膨脹：篇卷章數由 {current_chapter_count} 變更為 {new_chapter_count}"
            return False, "章數無實質改變，不符合章數膨脹"

        return False, "未知的修復條件"


class GeometryRepairEngine:
    """
    幾何修復執行引擎。
    在通過門禁後，對 GeometryGraph 實施拓撲重構。
    """

    def __init__(self, graph: GeometryGraph):
        self.graph = graph

    def execute_repair(
        self,
        proposal: RepairProposal,
        condition: GeometryRepairCondition,
        gatekeeper_context: Dict[str, Any],
    ) -> GeometryRepairResult:
        """
        執行修復提案：
        1. 嚴格驗證門禁條件
        2. 根據 operation 派發至對應拓撲操作
        3. 維持圖譜約束與指針合法性
        """
        # 1. 門禁判定
        passed, reason = GeometryRepairGatekeeper.verify_condition(condition, gatekeeper_context)
        if not passed:
            return GeometryRepairResult(
                success=False,
                operation=proposal.operation,
                condition=condition,
                message=f"修復請求遭駁回：{reason}。請改走 evaluate_output / supplement_content 重寫。",
            )

        # 2. 派發操作
        if proposal.operation == RepairOperation.SPLIT:
            return self._op_split(proposal, condition)
        elif proposal.operation == RepairOperation.EXPAND:
            return self._op_expand(proposal, condition)
        elif proposal.operation == RepairOperation.INSERT:
            return self._op_insert(proposal, condition)
        elif proposal.operation == RepairOperation.COMPRESS:
            return self._op_compress(proposal, condition)
        else:
            return GeometryRepairResult(
                success=False,
                operation=proposal.operation,
                condition=condition,
                message=f"不支援的修復操作：{proposal.operation}",
            )

    def _op_split(self, proposal: RepairProposal, condition: GeometryRepairCondition) -> GeometryRepairResult:
        """
        SPLIT (1 -> 2/3):
        將 1 個過載的節點拆分成 2 個或 3 個連續節點。
        繼承層級與 primary_thread，重新分發 incoming/outgoing 邊。
        """
        if not proposal.target_nodes:
            return GeometryRepairResult(success=False, operation=RepairOperation.SPLIT, condition=condition, message="未指定目標節點")

        target_node_id = proposal.target_nodes[0]
        original_node = self.graph.get_node(target_node_id)
        if not original_node:
            return GeometryRepairResult(success=False, operation=RepairOperation.SPLIT, condition=condition, message=f"找不到節點 {target_node_id}")

        split_count = proposal.detail.get("split_count", 2)
        split_count = max(2, min(3, split_count))

        incoming_edges = self.graph.get_incoming_edges(target_node_id)
        outgoing_edges = self.graph.get_outgoing_edges(target_node_id)

        new_node_ids = []
        new_nodes = []

        # 建立拆分後的新節點
        for i in range(split_count):
            sub_id = f"{target_node_id}_{chr(ord('A') + i)}"
            sub_role = original_node.structural_role if i == split_count - 1 else StructuralRole.DEVELOP
            sub_node = GeometryNode(
                node_id=sub_id,
                hierarchy=copy.deepcopy(original_node.hierarchy),
                chapter_window=original_node.chapter_window,
                structural_role=sub_role,
                primary_thread=original_node.primary_thread,
                importance=original_node.importance,
                semantic=None,
                metadata={
                    "split_from": target_node_id,
                    "split_sub_index": i,
                },
            )
            self.graph.add_node(sub_node)
            new_node_ids.append(sub_id)
            new_nodes.append(sub_node)

        # 串接拆分子節點之間的內部推進邊
        for i in range(len(new_nodes) - 1):
            self.graph.add_edge(GeometryEdge(
                edge_id=f"E_SPLIT_{new_nodes[i].node_id}_{new_nodes[i+1].node_id}",
                source=new_nodes[i].node_id,
                target=new_nodes[i + 1].node_id,
                edge_type=EdgeType.CAUSES,
                distance=0,
                metadata={"split_internal": True},
            ))

        # 重新定向外部邊：
        # 原 incoming 全部導向第一個子節點
        for in_e in incoming_edges:
            in_e.target = new_node_ids[0]

        # 原 outgoing 全部由最後一個子節點出發
        for out_e in outgoing_edges:
            out_e.source = new_node_ids[-1]

        # 更新線程序列中的節點參照
        for thread in self.graph.threads.values():
            if target_node_id in thread.node_sequence:
                idx = thread.node_sequence.index(target_node_id)
                thread.node_sequence[idx:idx + 1] = new_node_ids
                # 擴充骨架角色
                if idx < len(thread.structural_skeleton):
                    base_role = thread.structural_skeleton[idx]
                    thread.structural_skeleton[idx:idx + 1] = [StructuralRole.DEVELOP] * (split_count - 1) + [base_role]

        # 移除原節點
        del self.graph.nodes[target_node_id]

        return GeometryRepairResult(
            success=True,
            operation=RepairOperation.SPLIT,
            condition=condition,
            affected_nodes=[target_node_id],
            new_nodes=new_node_ids,
            removed_nodes=[target_node_id],
            message=f"成功將節點 {target_node_id} 拆分為 {len(new_node_ids)} 個子節點: {', '.join(new_node_ids)}",
        )

    def _op_expand(self, proposal: RepairProposal, condition: GeometryRepairCondition) -> GeometryRepairResult:
        """
        EXPAND (3 -> 5):
        在收束或高潮區間，將過度緊湊的 3 個節點擴增為 5 個節點，
        讓多條線程有足夠空間逐一交會。
        """
        targets = proposal.target_nodes
        if len(targets) < 2:
            return GeometryRepairResult(success=False, operation=RepairOperation.EXPAND, condition=condition, message="EXPAND 至少需要指定 2 個目標節點範圍")

        nodes = [self.graph.get_node(nid) for nid in targets if self.graph.get_node(nid)]
        if len(nodes) < len(targets):
            return GeometryRepairResult(success=False, operation=RepairOperation.EXPAND, condition=condition, message="包含無效的目標節點 ID")

        nodes.sort(key=lambda n: (n.chapter_window[0], n.node_id))
        first_node = nodes[0]
        last_node = nodes[-1]

        # 新增 2 個過渡/收束中間節點
        add_count = proposal.detail.get("add_count", 2)
        new_node_ids = []

        for i in range(add_count):
            new_id = f"G_EXP_{first_node.node_id}_{i+1}"
            ch_mid = (first_node.chapter_window[0] + last_node.chapter_window[1]) // 2
            new_node = GeometryNode(
                node_id=new_id,
                hierarchy=copy.deepcopy(first_node.hierarchy),
                chapter_window=(ch_mid, ch_mid),
                structural_role=StructuralRole.CONVERGE if i == 0 else StructuralRole.ESCALATE,
                primary_thread=first_node.primary_thread,
                importance=0.8,
                semantic=None,
                metadata={"expanded_node": True},
            )
            self.graph.add_node(new_node)
            new_node_ids.append(new_id)

            # 連接前驅與後繼
            prev_id = nodes[i].node_id if i < len(nodes) else first_node.node_id
            self.graph.add_edge(GeometryEdge(
                edge_id=f"E_EXP_{prev_id}_{new_id}",
                source=prev_id,
                target=new_id,
                edge_type=EdgeType.ENABLES,
                distance=abs(new_node.chapter_window[0] - self.graph.get_node(prev_id).chapter_window[0]),
            ))

        # 最後一個新節點連到 last_node
        if new_node_ids:
            self.graph.add_edge(GeometryEdge(
                edge_id=f"E_EXP_{new_node_ids[-1]}_{last_node.node_id}",
                source=new_node_ids[-1],
                target=last_node.node_id,
                edge_type=EdgeType.CONVERGES,
                distance=abs(last_node.chapter_window[0] - self.graph.get_node(new_node_ids[-1]).chapter_window[0]),
            ))

        return GeometryRepairResult(
            success=True,
            operation=RepairOperation.EXPAND,
            condition=condition,
            affected_nodes=targets,
            new_nodes=new_node_ids,
            message=f"成功在節點 {targets[0]}..{targets[-1]} 區間擴增 {len(new_node_ids)} 個結構節點",
        )

    def _op_insert(self, proposal: RepairProposal, condition: GeometryRepairCondition) -> GeometryRepairResult:
        """
        INSERT (橋接章節點 + 後續章號順延):
        在節點 A 與 B 之間插入橋接節點 C。
        若造成章節總數增加，後續所有章節的 chapter_window 自動平移順延。
        """
        after_node_id = proposal.detail.get("after_node_id")
        before_node_id = proposal.detail.get("before_node_id")

        if not after_node_id or not before_node_id:
            return GeometryRepairResult(success=False, operation=RepairOperation.INSERT, condition=condition, message="INSERT 必須同時指定 after_node_id 與 before_node_id")

        node_a = self.graph.get_node(after_node_id)
        node_b = self.graph.get_node(before_node_id)

        if not node_a or not node_b:
            return GeometryRepairResult(success=False, operation=RepairOperation.INSERT, condition=condition, message="指定的橋接錨點節點不存在")

        is_new_chapter = proposal.detail.get("is_new_chapter", False)
        insert_chapter = node_a.chapter_window[1] + 1 if is_new_chapter else node_a.chapter_window[1]

        bridge_id = f"G_BRIDGE_{node_a.node_id}_{node_b.node_id}"
        bridge_node = GeometryNode(
            node_id=bridge_id,
            hierarchy=copy.deepcopy(node_a.hierarchy),
            chapter_window=(insert_chapter, insert_chapter),
            structural_role=StructuralRole.DEVELOP,
            primary_thread=node_a.primary_thread,
            importance=0.6,
            semantic=None,
            metadata={"is_bridge_node": True, "bridge_between": [after_node_id, before_node_id]},
        )
        self.graph.add_node(bridge_node)

        # 建立 A -> Bridge -> B 連線
        self.graph.add_edge(GeometryEdge(
            edge_id=f"E_BR_{node_a.node_id}_{bridge_id}",
            source=node_a.node_id,
            target=bridge_id,
            edge_type=EdgeType.CAUSES,
            distance=0 if not is_new_chapter else 1,
        ))
        self.graph.add_edge(GeometryEdge(
            edge_id=f"E_BR_{bridge_id}_{node_b.node_id}",
            source=bridge_id,
            target=node_b.node_id,
            edge_type=EdgeType.ENABLES,
            distance=0 if not is_new_chapter else 1,
        ))

        # 若增加了章節，平移後續章節
        delta = 1 if is_new_chapter else 0
        if delta > 0:
            self.shift_downstream_chapters(after_chapter=node_a.chapter_window[1], delta=delta, exclude_node_ids={bridge_id})

        return GeometryRepairResult(
            success=True,
            operation=RepairOperation.INSERT,
            condition=condition,
            affected_nodes=[after_node_id, before_node_id],
            new_nodes=[bridge_id],
            chapter_delta=delta,
            message=f"成功在 {after_node_id} 與 {before_node_id} 之間插入橋接節點 {bridge_id}" + (f"，後續章節自動平移順延 +{delta} 章" if delta else ""),
        )

    def _op_compress(self, proposal: RepairProposal, condition: GeometryRepairCondition) -> GeometryRepairResult:
        """
        COMPRESS (壓縮水章):
        將指定的 2 個連續冗餘/灌水節點合併為 1 個節點。
        整併邊關聯，並釋放冗餘結構。
        """
        targets = proposal.target_nodes
        if len(targets) < 2:
            return GeometryRepairResult(success=False, operation=RepairOperation.COMPRESS, condition=condition, message="COMPRESS 至少需要指定 2 個待合併節點")

        node_a = self.graph.get_node(targets[0])
        node_b = self.graph.get_node(targets[1])
        if not node_a or not node_b:
            return GeometryRepairResult(success=False, operation=RepairOperation.COMPRESS, condition=condition, message="待合併節點不存在")

        # 保留 node_a，將 node_b 的邊轉移給 node_a，並刪除 node_b
        incoming_b = self.graph.get_incoming_edges(node_b.node_id)
        outgoing_b = self.graph.get_outgoing_edges(node_b.node_id)

        for e in incoming_b:
            if e.source != node_a.node_id:
                e.target = node_a.node_id

        for e in outgoing_b:
            if e.target != node_a.node_id:
                e.source = node_a.node_id

        # 擴大 node_a 的 chapter_window 以覆蓋 node_b
        node_a.chapter_window = (
            min(node_a.chapter_window[0], node_b.chapter_window[0]),
            max(node_a.chapter_window[1], node_b.chapter_window[1]),
        )
        node_a.metadata["compressed_from"] = [targets[0], targets[1]]

        # 移除連線與節點
        self.graph.edges = [
            e for e in self.graph.edges
            if not (e.source == node_a.node_id and e.target == node_a.node_id)
            and e.source != node_b.node_id and e.target != node_b.node_id
        ]
        del self.graph.nodes[node_b.node_id]

        return GeometryRepairResult(
            success=True,
            operation=RepairOperation.COMPRESS,
            condition=condition,
            affected_nodes=targets,
            new_nodes=[],
            removed_nodes=[node_b.node_id],
            message=f"成功將節點 {targets[1]} 壓縮合併入 {targets[0]}",
        )

    def shift_downstream_chapters(self, after_chapter: int, delta: int, exclude_node_ids: Optional[Set[str]] = None) -> None:
        """
        平移指定章節之後所有節點、篇卷、弧線的章節座標。
        """
        exclude_node_ids = exclude_node_ids or set()

        for node in self.graph.nodes.values():
            if node.node_id in exclude_node_ids:
                continue
            start, end = node.chapter_window
            if start > after_chapter:
                node.chapter_window = (start + delta, end + delta)
            elif end > after_chapter:
                node.chapter_window = (start, end + delta)

        for vol in self.graph.volumes.values():
            start, end = vol.chapter_range
            if start > after_chapter:
                vol.chapter_range = (start + delta, end + delta)
            elif end >= after_chapter:
                vol.chapter_range = (start, end + delta)

        for arc in self.graph.arcs.values():
            start, end = arc.chapter_range
            if start > after_chapter:
                arc.chapter_range = (start + delta, end + delta)
            elif end >= after_chapter:
                arc.chapter_range = (start, end + delta)

        for seq in self.graph.sequences.values():
            start, end = seq.chapter_range
            if start > after_chapter:
                seq.chapter_range = (start + delta, end + delta)
            elif end >= after_chapter:
                seq.chapter_range = (start, end + delta)

        self.graph.params.target_chapters += delta
