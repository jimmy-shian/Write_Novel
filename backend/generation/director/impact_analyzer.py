# -*- coding: utf-8 -*-
"""
Master Graph 影響分析器與四級局部修復協調器
(Impact Analyzer & 4-Tier Local Repair Coordinator)

職責：
1. ImpactAnalyzer:
   - 動態欄位依賴分析 (Dynamic Field-Based Dependency Impact Analysis):
     * 外觀/表面修辭欄位變更 (Cosmetic fields) -> 影響集合嚴格局限於當前節點 {node_id}
     * 角色屬性欄位變更 (Character attributes) -> 影響當前篇卷內該角色出場的所有場景節點
     * 因果/結構核心欄位變更 (Causal/structural fields: state_mutations, core_conflict, direct_outcome,
       causal_preconditions, destiny_events, causal edges) -> 沿因果邊 CAUSAL_EDGE_TYPES
       (CAUSES, ENABLES, ESCALATES) 遍歷下游影響鏈 + 伏筆線索閉環 (clue bindings)
   - 動態計算精確受影響節點 ID 集合，徹底取代固定 2-5 節點粗暴重跑。

2. LocalRepairCoordinator:
   - 總監四級局部修復政策 (Four-Tier Local Repair Priority Policy):
     * Level 1 (Agent Prompt / Output Fix): 當前生成文字/JSON修復，不改動Master Graph節點
     * Level 2 (Node Slot Fix): 單節點 Slot 修復，保留拓撲骨架與邊連線，僅更新特定Slot
     * Level 3 (Dynamic Impact Subgraph Fix): 呼叫 ImpactAnalyzer 計算最小受牽連子圖，
       草稿補丁暫存 (Draft Patch) + 局部因果 DAG 驗收 + 原子提交 (revision += 1)
     * Level 4 (Structural Repair): 幾何結構重構 (SPLIT, EXPAND, INSERT, COMPRESS)，
       嚴格核查四大門禁條件 (DENSITY_OVERLOAD, CAUSAL_GAP, CONVERGENCE_COLLISION, CHAPTER_EXPANSION)，
       快照原子備份與 DAG 驗證回滾保護。
"""

from __future__ import annotations

import copy
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from backend.geometry.models import (
    CAUSAL_EDGE_TYPES,
    NON_CAUSAL_EDGE_TYPES,
    EdgeType,
    ForeshadowingDemand,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    NodeStoryContract,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    RepairOperation,
    RepairProposal,
    StoryEventContract,
    StructuralRole,
)
from backend.geometry.repair import (
    GeometryRepairCondition,
    GeometryRepairEngine,
    GeometryRepairGatekeeper,
    GeometryRepairResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 欄位類別定義 (Field Classification Definitions)
# =============================================================================

# 1. 外觀與表面修辭欄位 (Cosmetic Fields)
COSMETIC_FIELDS: Set[str] = {
    "title",
    "description",
    "surface_text",
    "surface_dialogue",
    "dialogue",
    "prose",
    "summary",
    "scene_notes",
    "atmosphere",
    "style",
    "tone",
    "rhetoric",
    "pacing",
    "text",
    "content",
}

# 2. 角色屬性與演出欄位 (Character Attribute Fields)
CHARACTER_ATTRIBUTE_FIELDS: Set[str] = {
    "character_slots",
    "character_attributes",
    "character_appearance",
    "character_voice",
    "character_personality",
    "character_catchphrase",
    "appearance",
    "voice",
    "personality",
    "catchphrase",
    "costume",
    "equipment",
    "mannerisms",
    "character_dynamics",
}

# 3. 因果、狀態與結構核心欄位 (Causal & Structural Fields)
CAUSAL_STRUCTURAL_FIELDS: Set[str] = {
    "state_mutations",
    "core_conflict",
    "direct_outcome",
    "causal_preconditions",
    "destiny_events",
    "causal_edge_edits",
    "edges",
    "incoming_edges",
    "outgoing_edges",
    "causal_edges",
    "structural_role",
    "node_type",
    "foreshadowing_demand",
    "foreshadowing_tasks",
    "clue_bindings",
    "downstream_impact",
    "action_motives",
    "worldview_slot",
    "thread_memberships",
    "chapter_mappings",
}


def classify_field(field_name: str) -> str:
    """
    將單一欄位名稱歸類為：'cosmetic' | 'character' | 'causal'
    防禦性設計：未知欄位預設歸入 'causal'，以確保敘事因果防護不遺漏。
    """
    clean_field = field_name.strip().lower()
    if clean_field in COSMETIC_FIELDS:
        return "cosmetic"
    if clean_field in CHARACTER_ATTRIBUTE_FIELDS:
        return "character"
    if clean_field in CAUSAL_STRUCTURAL_FIELDS:
        return "causal"
    return "causal"  # 防禦性預設


# =============================================================================
# 影響分析資料載體 (Impact Analysis Data Structures)
# =============================================================================

@dataclass
class ImpactAnalysisResult:
    """動態影響分析詳細診斷報告"""
    node_id: str
    changed_fields: List[str]
    affected_nodes: Set[str]
    categories_triggered: Set[str] = field(default_factory=set)
    character_ids_found: Set[str] = field(default_factory=set)
    clue_ids_found: Set[str] = field(default_factory=set)
    downstream_causal_nodes: Set[str] = field(default_factory=set)
    volume_index: int = 1
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "changed_fields": self.changed_fields,
            "affected_nodes": sorted(list(self.affected_nodes)),
            "categories_triggered": sorted(list(self.categories_triggered)),
            "character_ids_found": sorted(list(self.character_ids_found)),
            "clue_ids_found": sorted(list(self.clue_ids_found)),
            "downstream_causal_nodes": sorted(list(self.downstream_causal_nodes)),
            "volume_index": self.volume_index,
            "reasoning": self.reasoning,
        }


# =============================================================================
# ImpactAnalyzer 核心類別
# =============================================================================

class ImpactAnalyzer:
    """
    動態欄位依賴影響分析器 (Dynamic Field-Based Impact Analyzer)。
    根據具體變更欄位，動態計算最小受波及之節點集合。
    """

    def analyze_node_impact(
        self,
        graph: Union[GeometryGraph, str],
        node_id: str,
        changed_fields: List[str],
        **kwargs: Any,
    ) -> Set[str]:
        """
        分析節點變更欄位之受影響子圖節點 ID 集合。

        依賴傳播規則：
        1. 若所有欄位皆為外觀/修辭欄位 (`title`, `description`, `surface_text`) -> `{node_id}`
        2. 若涉及角色屬性 (`character_slots`, `appearance`, `voice` 等) -> 當前卷內該角色出場的所有場景節點
        3. 若涉及因果/結構核心欄位 (`state_mutations`, `core_conflict`, `direct_outcome`,
           `causal_preconditions`, `destiny_events`, 因果邊編輯) ->
           沿 `CAUSAL_EDGE_TYPES` (`CAUSES`, `ENABLES`, `ESCALATES`) 遍歷下游子圖 + 伏筆線索閉環 (clue bindings)

        :param graph: GeometryGraph 實例或 novel_id 字串 (若為字串則嘗試由持久層載入)
        :param node_id: 發生變更的節點 ID
        :param changed_fields: 變更的欄位名稱列表
        :return: 確切受影響的節點 ID 集合 (Set[str])
        """
        resolved_graph = self._resolve_graph(graph)
        if resolved_graph is None:
            logger.warning(f"無法解析幾何圖譜，預設僅標記目標節點 {node_id}")
            return {node_id}

        if node_id not in resolved_graph.nodes:
            logger.warning(f"節點 {node_id} 不在圖譜節點集合中，返回目標節點自身")
            return {node_id}

        # 變更欄位為空時，僅返回自身
        if not changed_fields:
            return {node_id}

        # 1. 檢查是否全為外觀修辭欄位
        if self._is_cosmetic_only(changed_fields):
            return {node_id}

        affected: Set[str] = {node_id}

        # 2. 角色屬性變更：波及當前篇卷內該角色活躍之所有場景節點
        if self._has_character_changes(changed_fields):
            char_ids = self._extract_node_character_ids(resolved_graph, node_id)
            extra_chars = kwargs.get("character_ids")
            if extra_chars and isinstance(extra_chars, (list, set)):
                char_ids.update(extra_chars)

            if char_ids:
                volume_nodes = self._find_character_scene_nodes_in_volume(
                    resolved_graph, node_id, char_ids
                )
                affected.update(volume_nodes)

        # 3. 因果或結構核心欄位變更：沿因果邊遍歷下游 + 伏筆線索閉環
        if self._has_causal_changes(changed_fields):
            extra_clues = kwargs.get("clue_ids")
            extra_clue_set = set(extra_clues) if extra_clues and isinstance(extra_clues, (list, set)) else set()

            # 遞迴/傳遞閉包遍歷：因果後繼 + 沿途所有節點之伏筆線索綁定
            causal_and_clue_nodes = self._traverse_causal_and_clues_closure(
                resolved_graph, {node_id}, initial_clues=extra_clue_set
            )
            affected.update(causal_and_clue_nodes)

        return affected

    def detailed_impact_analysis(
        self,
        graph: Union[GeometryGraph, str],
        node_id: str,
        changed_fields: List[str],
        **kwargs: Any,
    ) -> ImpactAnalysisResult:
        """執行影響分析並輸出結構化診斷報告"""
        resolved_graph = self._resolve_graph(graph)
        categories: Set[str] = set()
        reasoning: List[str] = []

        if resolved_graph is None or node_id not in resolved_graph.nodes:
            return ImpactAnalysisResult(
                node_id=node_id,
                changed_fields=changed_fields,
                affected_nodes={node_id},
                categories_triggered={"unknown"},
                reasoning=["圖譜或節點不存在，預設隔離至目標節點"],
            )

        target_node = resolved_graph.get_node(node_id)
        vol_idx = target_node.hierarchy.volume_index if (target_node and target_node.hierarchy) else 1

        if not changed_fields:
            return ImpactAnalysisResult(
                node_id=node_id,
                changed_fields=[],
                affected_nodes={node_id},
                categories_triggered={"none"},
                volume_index=vol_idx,
                reasoning=["無欄位變更，僅保留目標節點"],
            )

        if self._is_cosmetic_only(changed_fields):
            return ImpactAnalysisResult(
                node_id=node_id,
                changed_fields=changed_fields,
                affected_nodes={node_id},
                categories_triggered={"cosmetic"},
                volume_index=vol_idx,
                reasoning=[f"所有變更欄位均屬表面修辭/外觀欄位 ({changed_fields})，嚴格局限於目標節點"],
            )

        affected: Set[str] = {node_id}
        char_ids_found: Set[str] = set()
        clue_ids_found: Set[str] = set()
        downstream_nodes: Set[str] = set()

        if self._has_character_changes(changed_fields):
            categories.add("character")
            char_ids_found = self._extract_node_character_ids(resolved_graph, node_id)
            extra_chars = kwargs.get("character_ids")
            if extra_chars and isinstance(extra_chars, (list, set)):
                char_ids_found.update(extra_chars)

            if char_ids_found:
                vol_scenes = self._find_character_scene_nodes_in_volume(
                    resolved_graph, node_id, char_ids_found
                )
                affected.update(vol_scenes)
                reasoning.append(
                    f"角色屬性變更 ({char_ids_found})，波及第 {vol_idx} 卷內 {len(vol_scenes)} 個登場場景節點"
                )

        if self._has_causal_changes(changed_fields):
            categories.add("causal")
            extra_clues = kwargs.get("clue_ids")
            extra_clue_set = set(extra_clues) if extra_clues and isinstance(extra_clues, (list, set)) else set()

            downstream_nodes = self._traverse_causal_and_clues_closure(
                resolved_graph, {node_id}, initial_clues=extra_clue_set
            )
            affected.update(downstream_nodes)
            clue_ids_found = set()
            for nid in downstream_nodes:
                clue_ids_found.update(self._extract_node_clue_ids(resolved_graph, nid))

            reasoning.append(
                f"因果核心欄位變更，沿因果邊 CAUSAL_EDGE_TYPES 與伏筆線索閉環傳播，波及 {len(downstream_nodes)} 個節點"
            )

        return ImpactAnalysisResult(
            node_id=node_id,
            changed_fields=changed_fields,
            affected_nodes=affected,
            categories_triggered=categories,
            character_ids_found=char_ids_found,
            clue_ids_found=clue_ids_found,
            downstream_causal_nodes=downstream_nodes,
            volume_index=vol_idx,
            reasoning=reasoning,
        )

    # -------------------------------------------------------------------------
    # 內部輔助方法 (Internal Helpers)
    # -------------------------------------------------------------------------

    def _resolve_graph(self, graph: Union[GeometryGraph, str]) -> Optional[GeometryGraph]:
        """解析圖譜物件：若傳入 novel_id 字串則從持久層載入"""
        if isinstance(graph, GeometryGraph):
            return graph
        if isinstance(graph, str):
            try:
                from backend.persistence.repositories.geometry import load_geometry_graph
                return load_geometry_graph(graph)
            except Exception as e:
                logger.error(f"從資料庫載入小說幾何圖失敗 [{graph}]: {e}")
                return None
        return None

    def _is_cosmetic_only(self, changed_fields: List[str]) -> bool:
        """判定變更欄位是否全部為外觀/修辭欄位"""
        if not changed_fields:
            return True
        return all(classify_field(f) == "cosmetic" for f in changed_fields)

    def _has_character_changes(self, changed_fields: List[str]) -> bool:
        """判定是否包含角色屬性相關欄位"""
        return any(classify_field(f) == "character" for f in changed_fields)

    def _has_causal_changes(self, changed_fields: List[str]) -> bool:
        """判定是否包含因果或結構核心欄位"""
        return any(classify_field(f) == "causal" for f in changed_fields)

    def _extract_node_character_ids(self, graph: GeometryGraph, node_id: str) -> Set[str]:
        """擷取指定節點關聯之所有角色 ID"""
        char_ids: Set[str] = set()
        node = graph.get_node(node_id)
        if not node:
            return char_ids

        # 1. 從 NodeStoryContract.character_slots 擷取
        contract = graph.get_story_contract(node_id) or node.story_contract
        if contract:
            if hasattr(contract, "character_slots") and isinstance(contract.character_slots, list):
                for slot in contract.character_slots:
                    if isinstance(slot, dict):
                        cid = slot.get("character_id") or slot.get("char_id") or slot.get("id")
                        if cid:
                            char_ids.add(str(cid))

            # 2. 從 StoryEventContract.participant_entities 擷取
            if hasattr(contract, "story_events") and isinstance(contract.story_events, list):
                for ev in contract.story_events:
                    parts = getattr(ev, "participant_entities", []) if hasattr(ev, "participant_entities") else (ev.get("participant_entities", []) if isinstance(ev, dict) else [])
                    if isinstance(parts, list):
                        for p in parts:
                            if isinstance(p, dict):
                                cid = p.get("char_id") or p.get("character_id") or p.get("id")
                                if cid:
                                    char_ids.add(str(cid))

            # 3. 從 destiny_events 擷取
            if hasattr(contract, "destiny_events") and isinstance(contract.destiny_events, list):
                for d in contract.destiny_events:
                    if isinstance(d, dict):
                        cid = d.get("char_id") or d.get("character_id")
                        if cid:
                            char_ids.add(str(cid))

        # 4. 從 GeometryNode.semantic 擷取
        if node.semantic and isinstance(node.semantic, dict):
            sem_chars = node.semantic.get("characters") or node.semantic.get("participants")
            if isinstance(sem_chars, list):
                for c in sem_chars:
                    if isinstance(c, str):
                        char_ids.add(c)
                    elif isinstance(c, dict):
                        cid = c.get("character_id") or c.get("char_id") or c.get("id")
                        if cid:
                            char_ids.add(str(cid))

        # 5. 從 GeometryNode.metadata 擷取
        if node.metadata and isinstance(node.metadata, dict):
            meta_chars = node.metadata.get("characters")
            if isinstance(meta_chars, list):
                for c in meta_chars:
                    if isinstance(c, str):
                        char_ids.add(c)

        return char_ids

    def _find_character_scene_nodes_in_volume(
        self,
        graph: GeometryGraph,
        node_id: str,
        char_ids: Set[str],
    ) -> Set[str]:
        """尋找當前篇卷內該角色出場的所有場景節點"""
        target_node = graph.get_node(node_id)
        if not target_node or not char_ids:
            return set()

        target_volume = target_node.hierarchy.volume_index if target_node.hierarchy else 1
        scene_nodes: Set[str] = set()

        for other_id, other_node in graph.nodes.items():
            other_vol = other_node.hierarchy.volume_index if other_node.hierarchy else 1
            if other_vol != target_volume:
                continue

            # 檢查 other_node 是否包含任一目標角色
            other_chars = self._extract_node_character_ids(graph, other_id)
            if other_chars.intersection(char_ids):
                scene_nodes.add(other_id)

        return scene_nodes

    def _extract_node_clue_ids(self, graph: GeometryGraph, node_id: str) -> Set[str]:
        """擷取指定節點關聯之所有伏筆/線索 ID"""
        clue_ids: Set[str] = set()
        contract = graph.get_story_contract(node_id)
        node = graph.get_node(node_id)

        if contract:
            # 1. StoryEventContract clue_bindings
            if hasattr(contract, "story_events") and isinstance(contract.story_events, list):
                for ev in contract.story_events:
                    bindings = getattr(ev, "clue_bindings", []) if hasattr(ev, "clue_bindings") else (ev.get("clue_bindings", []) if isinstance(ev, dict) else [])
                    if isinstance(bindings, list):
                        for b in bindings:
                            if b:
                                clue_ids.add(str(b))

            # 2. foreshadowing_tasks
            if hasattr(contract, "foreshadowing_tasks") and isinstance(contract.foreshadowing_tasks, list):
                for t in contract.foreshadowing_tasks:
                    if isinstance(t, dict):
                        cid = t.get("clue_id") or t.get("id")
                        if cid:
                            clue_ids.add(str(cid))

        if node and node.metadata and isinstance(node.metadata, dict):
            m_clues = node.metadata.get("clue_bindings") or node.metadata.get("foreshadowing_clues")
            if isinstance(m_clues, list):
                for c in m_clues:
                    if c:
                        clue_ids.add(str(c))

        return clue_ids

    def _find_clue_bound_nodes(self, graph: GeometryGraph, clue_ids: Set[str]) -> Set[str]:
        """尋找全圖中所有綁定/涉及指定伏筆線索的節點"""
        matched_nodes: Set[str] = set()
        if not clue_ids:
            return matched_nodes

        for nid in graph.nodes.keys():
            node_clues = self._extract_node_clue_ids(graph, nid)
            if node_clues.intersection(clue_ids):
                matched_nodes.add(nid)

        return matched_nodes

    def _traverse_causal_and_clues_closure(
        self,
        graph: GeometryGraph,
        start_nodes: Set[str],
        initial_clues: Optional[Set[str]] = None,
        max_depth: Optional[int] = None,
    ) -> Set[str]:
        """
        傳遞閉包遍歷：沿嚴格因果邊 (CAUSES, ENABLES, ESCALATES) 下游傳播，
        同時雙向閉環關聯所有途經節點涉及的伏筆線索 (clue bindings)。
        """
        visited_nodes: Set[str] = set(start_nodes)
        visited_clues: Set[str] = set(initial_clues or set())
        queue: deque[Tuple[str, int]] = deque((nid, 0) for nid in start_nodes if nid in graph.nodes)

        # 初始線索對應之節點加入
        if visited_clues:
            init_clue_nodes = self._find_clue_bound_nodes(graph, visited_clues)
            for cn in init_clue_nodes:
                if cn not in visited_nodes and cn in graph.nodes:
                    visited_nodes.add(cn)
                    queue.append((cn, 0))

        while queue:
            curr_id, depth = queue.popleft()

            # 1. 探索當前節點之所有伏筆線索
            node_clues = self._extract_node_clue_ids(graph, curr_id)
            new_clues = node_clues - visited_clues
            if new_clues:
                visited_clues.update(new_clues)
                clue_nodes = self._find_clue_bound_nodes(graph, new_clues)
                for cn in clue_nodes:
                    if cn not in visited_nodes and cn in graph.nodes:
                        visited_nodes.add(cn)
                        queue.append((cn, depth + 1))

            if max_depth is not None and depth >= max_depth:
                continue

            # 2. 探索因果後繼節點 (CAUSES, ENABLES, ESCALATES)
            successors = graph.get_causal_successors(curr_id)
            for succ_id in successors:
                if succ_id in graph.nodes and succ_id not in visited_nodes:
                    visited_nodes.add(succ_id)
                    queue.append((succ_id, depth + 1))

        return visited_nodes

    def _traverse_downstream_causal(
        self,
        graph: GeometryGraph,
        start_nodes: Set[str],
        max_depth: Optional[int] = None,
    ) -> Set[str]:
        """
        沿嚴格因果邊 (CAUSES, ENABLES, ESCALATES) 廣度優先 (BFS) 遍歷下游影響鏈。
        防禦性 visited 集合保證防止環路或重疊路徑死循環。
        """
        visited: Set[str] = set(start_nodes)
        queue: deque[Tuple[str, int]] = deque((nid, 0) for nid in start_nodes if nid in graph.nodes)

        while queue:
            curr_id, depth = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue

            successors = graph.get_causal_successors(curr_id)
            for succ_id in successors:
                if succ_id in graph.nodes and succ_id not in visited:
                    visited.add(succ_id)
                    queue.append((succ_id, depth + 1))

        return visited


# =============================================================================
# 四級局部修復政策資料契約 (4-Tier Repair Data Contracts)
# =============================================================================

class RepairTier(IntEnum):
    """
    總監四級局部修復層級 (Four-Tier Local Repair Priority Hierarchy)
    優先順序嚴格遞增：Level 1 -> Level 2 -> Level 3 -> Level 4
    """
    LEVEL_1_AGENT_PROMPT = 1    # 當前生成結果/Prompt修復 (完全不改動圖節點)
    LEVEL_2_NODE_SLOT = 2       # 單節點 Slot 修復 (保留拓撲與連線，僅更新特定Slot)
    LEVEL_3_IMPACT_SUBGRAPH = 3 # 局部子圖修復 (動態依賴分析最小影響集合)
    LEVEL_4_STRUCTURAL = 4      # 上游結構性修復 (SPLIT/EXPAND/INSERT/COMPRESS)


@dataclass
class RepairRequest:
    """修復請求規格載體"""
    novel_id: str = ""
    node_id: Optional[str] = None
    tier: Optional[RepairTier] = None
    defects: List[str] = field(default_factory=list)
    changed_fields: List[str] = field(default_factory=list)
    slot_name: Optional[str] = None
    slot_data: Optional[Any] = None
    agent_name: Optional[str] = None
    agent_output: Optional[Any] = None
    remediation_hint: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    structural_proposal: Optional[RepairProposal] = None
    structural_condition: Optional[GeometryRepairCondition] = None
    gatekeeper_context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairPlan:
    """修復方案規劃 (Repair Plan Specification)"""
    tier: RepairTier
    target_node_id: Optional[str]
    affected_node_ids: Set[str]
    action: str  # "PROMPT_RETRY", "SLOT_BACKFILL", "SUBGRAPH_REVISION", "STRUCTURAL_REPAIR"
    directive: Dict[str, Any] = field(default_factory=dict)
    draft_patch: Optional[Dict[str, Any]] = None
    can_auto_commit: bool = False
    message: str = ""
    escalation_tier: Optional[RepairTier] = None


@dataclass
class RepairExecutionResult:
    """修復執行結果 (Repair Execution Result)"""
    success: bool
    tier: RepairTier
    affected_nodes: Set[str] = field(default_factory=set)
    new_revision: Optional[int] = None
    rolled_back: bool = False
    message: str = ""
    directive: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    recommended_escalation: Optional[RepairTier] = None


# =============================================================================
# LocalRepairCoordinator 核心類別
# =============================================================================

class LocalRepairCoordinator:
    """
    四級局部修復協調中樞 (Four-Tier Local Repair Coordinator)
    落實架構計劃書 §5.1「局部修復優先政策」：
    優先維持 Master Graph 既定拓撲與已驗收事實，嚴禁單點錯誤直接從頭重跑全局。
    層級調度：Level 1 (Prompt) -> Level 2 (Slot) -> Level 3 (Subgraph) -> Level 4 (Structural)。
    """

    def __init__(self, impact_analyzer: Optional[ImpactAnalyzer] = None):
        self.impact_analyzer: ImpactAnalyzer = impact_analyzer or ImpactAnalyzer()

    def diagnose_repair_tier(
        self,
        request: RepairRequest,
        graph: Optional[GeometryGraph] = None,
    ) -> RepairTier:
        """
        自動診斷並裁定最小必要之修復層級 (Diagnose Minimal Sufficient Repair Tier)。
        依據缺陷性質、重試次數與欄位類型，優先指派低層級修復。
        """
        # 若呼叫方已明確指定有效層級，優先遵循
        if request.tier is not None:
            return request.tier

        # 超過重試上限時主動升級
        if request.retry_count >= request.max_retries:
            logger.info(f"重試次數達上限 ({request.retry_count})，自動升級修復層級")
            if request.node_id and request.changed_fields:
                return RepairTier.LEVEL_3_IMPACT_SUBGRAPH
            return RepairTier.LEVEL_2_NODE_SLOT

        # 若明確包含結構性修復提案或門禁條件，且前置層級無法處理
        if request.structural_condition is not None and request.structural_proposal is not None:
            return RepairTier.LEVEL_4_STRUCTURAL

        defects_text = " ".join(request.defects).lower()

        # 1. Level 1: 純生成格式、JSON解析、修辭語言或格式缺陷
        l1_keywords = ["json", "format", "schema", "syntax", "rhetoric", "tone", "prose", "parse", "markdown"]
        if any(kw in defects_text for kw in l1_keywords) and not request.changed_fields:
            return RepairTier.LEVEL_1_AGENT_PROMPT

        # 2. Level 2: 單一節點特定槽位缺失或格式修訂 (無下游因果變更)
        if request.slot_name or (request.node_id and self.impact_analyzer._is_cosmetic_only(request.changed_fields)):
            return RepairTier.LEVEL_2_NODE_SLOT

        # 3. Level 3: 因果/角色/狀態欄位變更 (需動態子圖依賴分析)
        if request.node_id and (
            self.impact_analyzer._has_character_changes(request.changed_fields)
            or self.impact_analyzer._has_causal_changes(request.changed_fields)
        ):
            return RepairTier.LEVEL_3_IMPACT_SUBGRAPH

        # 4. Level 4: 拓撲容量超載或因果斷層
        l4_keywords = ["overload", "density", "causal_gap", "collision", "expand", "insert", "split"]
        if any(kw in defects_text for kw in l4_keywords):
            return RepairTier.LEVEL_4_STRUCTURAL

        # 預設保底：優先嘗試 Level 1
        return RepairTier.LEVEL_1_AGENT_PROMPT

    def create_repair_plan(
        self,
        graph: GeometryGraph,
        request: RepairRequest,
    ) -> RepairPlan:
        """
        為指定請求建立標準化修復方案規劃 (Create Repair Plan)
        """
        tier = self.diagnose_repair_tier(request, graph)

        if tier == RepairTier.LEVEL_1_AGENT_PROMPT:
            prompt_directive = (
                f"生成未達標，請重新調整修復：{request.remediation_hint or '; '.join(request.defects)}"
            )
            return RepairPlan(
                tier=tier,
                target_node_id=request.node_id,
                affected_node_ids=set(),
                action="PROMPT_RETRY",
                directive={
                    "agent_prompt": prompt_directive,
                    "defects": request.defects,
                    "target_agent": request.agent_name,
                },
                can_auto_commit=False,
                message="Level 1修復：指示當前 Agent 原地重試生成輸出，完全不改動圖節點",
                escalation_tier=RepairTier.LEVEL_2_NODE_SLOT,
            )

        elif tier == RepairTier.LEVEL_2_NODE_SLOT:
            target_id = request.node_id or ""
            return RepairPlan(
                tier=tier,
                target_node_id=target_id,
                affected_node_ids={target_id} if target_id else set(),
                action="SLOT_BACKFILL",
                directive={
                    "node_id": target_id,
                    "slot_name": request.slot_name,
                    "remediation_hint": request.remediation_hint,
                },
                draft_patch={
                    "patch_type": "SLOT_UPDATE",
                    "target_nodes": [target_id] if target_id else [],
                    "slot_name": request.slot_name,
                    "slot_data": request.slot_data,
                },
                can_auto_commit=True,
                message=f"Level 2修復：僅重新生成節點 {target_id} 的 Slot [{request.slot_name}]，保留拓撲骨架",
                escalation_tier=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
            )

        elif tier == RepairTier.LEVEL_3_IMPACT_SUBGRAPH:
            target_id = request.node_id or ""
            affected = self.impact_analyzer.analyze_node_impact(
                graph, target_id, request.changed_fields
            )
            return RepairPlan(
                tier=tier,
                target_node_id=target_id,
                affected_node_ids=affected,
                action="SUBGRAPH_REVISION",
                directive={
                    "target_node": target_id,
                    "affected_nodes": sorted(list(affected)),
                    "changed_fields": request.changed_fields,
                    "remediation_hint": request.remediation_hint,
                },
                draft_patch={
                    "patch_type": "SUBGRAPH_REVISION",
                    "base_revision": graph.graph_revision,
                    "target_nodes": sorted(list(affected)),
                },
                can_auto_commit=True,
                message=f"Level 3修復：動態分析節點 {target_id} 影響範圍，波及最小子圖 {len(affected)} 個節點",
                escalation_tier=RepairTier.LEVEL_4_STRUCTURAL,
            )

        else:  # Level 4
            target_nodes = (
                request.structural_proposal.target_nodes
                if request.structural_proposal
                else ([request.node_id] if request.node_id else [])
            )
            return RepairPlan(
                tier=tier,
                target_node_id=request.node_id,
                affected_node_ids=set(target_nodes),
                action="STRUCTURAL_REPAIR",
                directive={
                    "operation": request.structural_proposal.operation.value if request.structural_proposal else None,
                    "condition": request.structural_condition.value if request.structural_condition else None,
                    "target_nodes": target_nodes,
                },
                can_auto_commit=True,
                message="Level 4結構修復：調用 GeometryRepairEngine 實施拓撲重構",
                escalation_tier=None,
            )

    def coordinate_repair(
        self,
        graph: GeometryGraph,
        request: RepairRequest,
    ) -> RepairExecutionResult:
        """
        執行四級局部修復閉環 (Coordinate and Execute Repair)
        提供原子快照備份、分級派發與 DAG 驗證回滾保護。
        """
        tier = self.diagnose_repair_tier(request, graph)

        if tier == RepairTier.LEVEL_1_AGENT_PROMPT:
            return self._execute_level_1(request)
        elif tier == RepairTier.LEVEL_2_NODE_SLOT:
            return self._execute_level_2(graph, request)
        elif tier == RepairTier.LEVEL_3_IMPACT_SUBGRAPH:
            return self._execute_level_3(graph, request)
        elif tier == RepairTier.LEVEL_4_STRUCTURAL:
            return self._execute_level_4(graph, request)
        else:
            return RepairExecutionResult(
                success=False,
                tier=tier,
                message=f"未知的修復層級: {tier}",
            )

    # -------------------------------------------------------------------------
    # 各層級修復具體執行器 (Tier Execution Handlers)
    # -------------------------------------------------------------------------

    def _execute_level_1(self, request: RepairRequest) -> RepairExecutionResult:
        """
        Level 1 執行：完全不修改 Master Graph，生成負反饋提示詞供 Agent 重新生成。
        """
        directive_prompt = (
            f"生成未達標，請重新調整修復：{request.remediation_hint or '; '.join(request.defects)}"
        )
        return RepairExecutionResult(
            success=True,
            tier=RepairTier.LEVEL_1_AGENT_PROMPT,
            affected_nodes=set(),
            new_revision=None,
            rolled_back=False,
            message="Level 1修復成功：已產生負反饋提示詞，Master Graph保持零變更",
            directive={
                "agent_prompt": directive_prompt,
                "defects": request.defects,
                "retry_count": request.retry_count + 1,
            },
            recommended_escalation=RepairTier.LEVEL_2_NODE_SLOT,
        )

    def _execute_level_2(
        self,
        graph: GeometryGraph,
        request: RepairRequest,
    ) -> RepairExecutionResult:
        """
        Level 2 執行：單節點 Slot 修復。保留拓撲與連線，僅更新/重設該節點 Slot。
        """
        target_id = request.node_id
        if not target_id or target_id not in graph.nodes:
            return RepairExecutionResult(
                success=False,
                tier=RepairTier.LEVEL_2_NODE_SLOT,
                message=f"Level 2修復失敗：目標節點 [{target_id}] 不存在於圖譜中",
                recommended_escalation=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
            )

        node = graph.get_node(target_id)
        contract = graph.get_story_contract(target_id) or node.ensure_story_contract()

        # 快照以防異常
        snapshot_contract = copy.deepcopy(contract)

        try:
            slot_name = request.slot_name or "worldview_slot"
            if request.slot_data is not None:
                if slot_name == "worldview_slot":
                    contract.worldview_slot = request.slot_data
                    node.semantic = request.slot_data
                elif slot_name == "character_slots":
                    contract.character_slots = request.slot_data if isinstance(request.slot_data, list) else [request.slot_data]
                elif slot_name == "destiny_events":
                    contract.destiny_events = request.slot_data if isinstance(request.slot_data, list) else [request.slot_data]
                elif slot_name == "foreshadowing_tasks":
                    contract.foreshadowing_tasks = request.slot_data if isinstance(request.slot_data, list) else [request.slot_data]
                elif slot_name == "chapter_mappings":
                    contract.chapter_mappings = request.slot_data if isinstance(request.slot_data, list) else [request.slot_data]

            contract.planning_status = PlanningStatus.REVISION_PENDING
            graph.set_story_contract(contract)

            return RepairExecutionResult(
                success=True,
                tier=RepairTier.LEVEL_2_NODE_SLOT,
                affected_nodes={target_id},
                new_revision=graph.graph_revision,
                message=f"Level 2修復成功：已局部重設節點 {target_id} 的 Slot [{slot_name}]，其餘節點與邊連線凍結保全",
                directive={"target_node": target_id, "slot_name": slot_name},
                recommended_escalation=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
            )
        except Exception as e:
            # 回滾
            graph.set_story_contract(snapshot_contract)
            return RepairExecutionResult(
                success=False,
                tier=RepairTier.LEVEL_2_NODE_SLOT,
                affected_nodes={target_id},
                rolled_back=True,
                message=f"Level 2修復異常已回滾: {str(e)}",
                recommended_escalation=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
            )

    def _execute_level_3(
        self,
        graph: GeometryGraph,
        request: RepairRequest,
    ) -> RepairExecutionResult:
        """
        Level 3 執行：局部子圖修復 (動態依賴分析)。
        計算最小受波及集合，暫存草稿補丁，校驗因果 DAG，原子提交 (revision += 1)。
        """
        target_id = request.node_id
        if not target_id or target_id not in graph.nodes:
            return RepairExecutionResult(
                success=False,
                tier=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
                message=f"Level 3修復失敗：目標節點 [{target_id}] 不存在於圖譜中",
                recommended_escalation=RepairTier.LEVEL_4_STRUCTURAL,
            )

        # 1. 動態影響分析
        affected_nodes = self.impact_analyzer.analyze_node_impact(
            graph, target_id, request.changed_fields
        )

        # 2. 建立原子快照
        snapshot = copy.deepcopy(graph)

        try:
            # 3. 標記受影響節點為修訂中
            for nid in affected_nodes:
                c = graph.get_story_contract(nid)
                if c:
                    c.planning_status = PlanningStatus.REVISION_PENDING
                    c.graph_revision = graph.graph_revision + 1
                    graph.set_story_contract(c)

            # 若有指定 slot_data，應用至 target_id
            if request.slot_name and request.slot_data is not None:
                tc = graph.get_story_contract(target_id)
                if tc and hasattr(tc, request.slot_name):
                    setattr(tc, request.slot_name, request.slot_data)
                    graph.set_story_contract(tc)

            # 4. 局部驗證因果 DAG 無環
            cycle_errors = graph.validate_causal_dag()
            if cycle_errors:
                self._restore_graph_snapshot(graph, snapshot)
                return RepairExecutionResult(
                    success=False,
                    tier=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
                    affected_nodes=affected_nodes,
                    rolled_back=True,
                    message=f"Level 3局部修復導致因果 DAG 環狀違規，操作已原子回滾: {cycle_errors}",
                    recommended_escalation=RepairTier.LEVEL_4_STRUCTURAL,
                )

            # 5. 原子提交：推進版本號
            graph.graph_revision += 1

            return RepairExecutionResult(
                success=True,
                tier=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
                affected_nodes=affected_nodes,
                new_revision=graph.graph_revision,
                message=f"Level 3修復成功：動態依賴分析修復 {len(affected_nodes)} 個節點，版本號推進至 v{graph.graph_revision}",
                directive={
                    "target_node": target_id,
                    "affected_nodes": sorted(list(affected_nodes)),
                    "new_revision": graph.graph_revision,
                },
                details={"affected_node_count": len(affected_nodes)},
                recommended_escalation=RepairTier.LEVEL_4_STRUCTURAL,
            )

        except Exception as e:
            self._restore_graph_snapshot(graph, snapshot)
            return RepairExecutionResult(
                success=False,
                tier=RepairTier.LEVEL_3_IMPACT_SUBGRAPH,
                affected_nodes=affected_nodes,
                rolled_back=True,
                message=f"Level 3修復執行異常已原子回滾: {str(e)}",
                recommended_escalation=RepairTier.LEVEL_4_STRUCTURAL,
            )

    def _execute_level_4(
        self,
        graph: GeometryGraph,
        request: RepairRequest,
    ) -> RepairExecutionResult:
        """
        Level 4 執行：上游結構性修復 (SPLIT, EXPAND, INSERT, COMPRESS)。
        經由 GeometryRepairGatekeeper 嚴格判定四大重大條件，調用 GeometryRepairEngine。
        """
        proposal = request.structural_proposal
        condition = request.structural_condition

        if not proposal or not condition:
            return RepairExecutionResult(
                success=False,
                tier=RepairTier.LEVEL_4_STRUCTURAL,
                message="Level 4結構修復失敗：未提供結構修復提案 (proposal) 或重大修復條件 (condition)",
            )

        # 鎖定小說主幹安全檢查
        target_nodes = proposal.target_nodes or ([request.node_id] if request.node_id else [])
        for nid in target_nodes:
            contract = graph.get_story_contract(nid)
            if contract and contract.planning_status == PlanningStatus.STORY_CANON_LOCKED:
                if not request.metadata.get("allow_canon_modification", False):
                    return RepairExecutionResult(
                        success=False,
                        tier=RepairTier.LEVEL_4_STRUCTURAL,
                        affected_nodes=set(target_nodes),
                        message=f"Level 4結構修復遭拒絕：節點 {nid} 已鎖定 STORY_CANON_LOCKED，未授權禁止靜默破壞已鎖定主幹",
                    )

        # 調用 GeometryRepairEngine
        engine = GeometryRepairEngine(graph)
        repair_res = engine.execute_repair(
            proposal=proposal,
            condition=condition,
            gatekeeper_context=request.gatekeeper_context,
        )

        affected = set(repair_res.affected_nodes) | set(repair_res.new_nodes)

        if repair_res.success:
            return RepairExecutionResult(
                success=True,
                tier=RepairTier.LEVEL_4_STRUCTURAL,
                affected_nodes=affected,
                new_revision=graph.graph_revision,
                message=f"Level 4結構修復成功 [{repair_res.operation.value}]：{repair_res.message}，版本推進至 v{graph.graph_revision}",
                directive={
                    "operation": repair_res.operation.value,
                    "condition": repair_res.condition.value if repair_res.condition else None,
                    "new_nodes": repair_res.new_nodes,
                    "removed_nodes": repair_res.removed_nodes,
                },
                details={
                    "new_nodes": repair_res.new_nodes,
                    "removed_nodes": repair_res.removed_nodes,
                    "chapter_delta": repair_res.chapter_delta,
                },
            )
        else:
            return RepairExecutionResult(
                success=False,
                tier=RepairTier.LEVEL_4_STRUCTURAL,
                affected_nodes=affected,
                rolled_back=True,
                message=f"Level 4結構修復未通過：{repair_res.message}",
            )

    def _restore_graph_snapshot(self, target_graph: GeometryGraph, snapshot: GeometryGraph) -> None:
        """原子回滾圖譜內部物件"""
        target_graph.nodes = snapshot.nodes
        target_graph.edges = snapshot.edges
        target_graph.threads = snapshot.threads
        target_graph.volumes = snapshot.volumes
        target_graph.arcs = snapshot.arcs
        target_graph.sequences = snapshot.sequences
        target_graph.graph_revision = snapshot.graph_revision
        target_graph.story_contracts = snapshot.story_contracts
        target_graph.params = snapshot.params
        if hasattr(snapshot, "planning_status"):
            target_graph.planning_status = snapshot.planning_status


# =============================================================================
# 便捷單例與函式封裝 (Convenience Functions)
# =============================================================================

_global_impact_analyzer: Optional[ImpactAnalyzer] = None
_global_repair_coordinator: Optional[LocalRepairCoordinator] = None


def get_impact_analyzer() -> ImpactAnalyzer:
    """獲取 ImpactAnalyzer 全域單例實例"""
    global _global_impact_analyzer
    if _global_impact_analyzer is None:
        _global_impact_analyzer = ImpactAnalyzer()
    return _global_impact_analyzer


def get_repair_coordinator() -> LocalRepairCoordinator:
    """獲取 LocalRepairCoordinator 全域單例實例"""
    global _global_repair_coordinator
    if _global_repair_coordinator is None:
        _global_repair_coordinator = LocalRepairCoordinator(get_impact_analyzer())
    return _global_repair_coordinator


def analyze_node_impact(
    graph: Union[GeometryGraph, str],
    node_id: str,
    changed_fields: List[str],
    **kwargs: Any,
) -> Set[str]:
    """快捷函式：執行節點變更之動態影響分析"""
    return get_impact_analyzer().analyze_node_impact(graph, node_id, changed_fields, **kwargs)


__all__ = [
    "COSMETIC_FIELDS",
    "CHARACTER_ATTRIBUTE_FIELDS",
    "CAUSAL_STRUCTURAL_FIELDS",
    "classify_field",
    "ImpactAnalysisResult",
    "ImpactAnalyzer",
    "RepairTier",
    "RepairRequest",
    "RepairPlan",
    "RepairExecutionResult",
    "LocalRepairCoordinator",
    "get_impact_analyzer",
    "get_repair_coordinator",
    "analyze_node_impact",
]
