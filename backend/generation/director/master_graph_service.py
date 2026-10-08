# -*- coding: utf-8 -*-
"""
Master Graph 服務層 (Master Graph Service Layer).

提供 Master Graph 單一真相核心 (Single Source of Truth, SSOT) 的權威操作中樞：
1. 槽位原子回填 (Slot Backfilling):
   - backfill_worldview_slot: 世界觀、版圖與衝突誘因
   - backfill_character_slots: 客觀角色群像（無劇透）
   - backfill_story_events: 九維具體故事事件契約 (StoryEventContract)
   - backfill_destiny_events: 角色重大命運變遷
   - backfill_foreshadowing_tasks: 伏筆任務 (Plant / Turn / Payoff)
   - backfill_chapter_mappings: 多對多章節拍點映射與覆蓋率
   - backfill_slot: 通用槽位分派器
2. 作用域上下文投影與防劇透護盾 (Scoped Context Projection & Strict Spoiler Wall):
   - 針對 chapter_writer: 屏蔽未來卷大綱、下游未至轉折與事件、未到期 Payoff 核心真相、角色未來命運劇透。
   - 針對 editor: 注入事實保全基準線 (Fact Diff Guard Baseline)。
   - 動態 Token 預算評估與 5 級精準剪裁 (Token Pruning Engine)。
3. 草稿補丁暫存與原子版本提交 (Draft Patch Staging & Atomic Revision Commit):
   - 支援四級局部修復與 Agent 階段隔離，不提前污染版本號。
   - 樂觀並發控制、DAG 無環合法性驗證、graph_revision 單調遞增、快照原子回滾。
4. 故事正典鎖定 (Canon Locking):
   - 終極門禁通過後一鍵將全圖節點鎖定為 STORY_CANON_LOCKED。
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from backend.geometry.models import (
    CAUSAL_EDGE_TYPES,
    NON_CAUSAL_EDGE_TYPES,
    EdgeType,
    ForeshadowingDemand,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    MasterGraphEdgeContract,
    NodeStoryContract,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
    StructuralRole,
)


# =============================================================================
# 1. DraftGraphPatch (草稿補丁資料容器)
# =============================================================================

@dataclass
class DraftGraphPatch:
    """
    Master Graph 變更草稿補丁 (Staging Container for Graph Modifications)。
    用於局部修復與各 Agent 階段的 Slot 回填暫存，
    在通過門禁驗收前保持主圖穩定，提交時原子寫入並推進版本號。
    """
    patch_id: str = field(default_factory=lambda: f"PATCH_{uuid.uuid4().hex[:12]}")
    base_revision: int = 1
    novel_id: str = ""
    status: str = "PENDING"  # PENDING, APPLIED, COMMITTED, DISCARDED
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    # 節點欄位更新: node_id -> {slot_name: data}
    node_updates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # 節點新增/重構: node_id -> NodeStoryContract
    node_additions: Dict[str, NodeStoryContract] = field(default_factory=dict)
    
    # 待刪除節點 ID 清單
    node_deletions: List[str] = field(default_factory=list)
    
    # 邊新增清單
    edge_additions: List[MasterGraphEdgeContract] = field(default_factory=list)
    
    # 待刪除邊 ID 清單
    edge_deletions: List[str] = field(default_factory=list)
    
    # 內部回滾備份快照 (僅於 apply 時產生，commit/discard 時釋放)
    _snapshot: Optional[GeometryGraph] = field(default=None, repr=False)
    
    # 門禁驗證或審計報告
    validation_report: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def stage_node_update(self, node_id: str, field_name: str, field_value: Any) -> None:
        """暫存單一節點的特定槽位更新。"""
        if node_id not in self.node_updates:
            self.node_updates[node_id] = {}
        self.node_updates[node_id][field_name] = field_value

    def stage_worldview_slot(self, node_id: str, worldview_data: Dict[str, Any]) -> None:
        self.stage_node_update(node_id, "worldview_slot", worldview_data)

    def stage_character_slots(self, node_id: str, character_slots: List[Dict[str, Any]]) -> None:
        self.stage_node_update(node_id, "character_slots", character_slots)

    def stage_story_events(self, node_id: str, story_events: List[Union[StoryEventContract, Dict[str, Any]]]) -> None:
        ev_dicts = [e.to_dict() if isinstance(e, StoryEventContract) else e for e in story_events]
        self.stage_node_update(node_id, "story_events", ev_dicts)

    def stage_destiny_events(self, node_id: str, destiny_events: List[Dict[str, Any]]) -> None:
        self.stage_node_update(node_id, "destiny_events", destiny_events)

    def stage_foreshadowing_tasks(self, node_id: str, tasks: List[Dict[str, Any]]) -> None:
        self.stage_node_update(node_id, "foreshadowing_tasks", tasks)

    def stage_chapter_mappings(self, node_id: str, mappings: List[Dict[str, Any]]) -> None:
        self.stage_node_update(node_id, "chapter_mappings", mappings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "base_revision": self.base_revision,
            "novel_id": self.novel_id,
            "status": self.status,
            "created_at": self.created_at,
            "node_updates": self.node_updates,
            "node_additions": {k: v.to_dict() for k, v in self.node_additions.items()},
            "node_deletions": self.node_deletions,
            "edge_additions": [e.to_dict() for e in self.edge_additions],
            "edge_deletions": self.edge_deletions,
            "validation_report": self.validation_report,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftGraphPatch":
        additions = {}
        for k, v in data.get("node_additions", {}).items():
            additions[k] = NodeStoryContract.from_dict(v) if isinstance(v, dict) else v
        edge_adds = [
            MasterGraphEdgeContract.from_dict(e) if isinstance(e, dict) else e
            for e in data.get("edge_additions", [])
        ]
        return cls(
            patch_id=data.get("patch_id", f"PATCH_{uuid.uuid4().hex[:12]}"),
            base_revision=data.get("base_revision", 1),
            novel_id=data.get("novel_id", ""),
            status=data.get("status", "PENDING"),
            created_at=data.get("created_at", datetime.utcnow().isoformat() + "Z"),
            node_updates=dict(data.get("node_updates", {})),
            node_additions=additions,
            node_deletions=list(data.get("node_deletions", [])),
            edge_additions=edge_adds,
            edge_deletions=list(data.get("edge_deletions", [])),
            validation_report=data.get("validation_report"),
            metadata=dict(data.get("metadata", {})),
        )


# =============================================================================
# 2. Token Estimation & Pruning Utilities (Token 預算與剪裁)
# =============================================================================

def estimate_tokens(obj: Any) -> int:
    """
    估算序列化物件的 Token 數量。
    中文字元每 1.2 個約為 1 Token；英文字元與代碼符號每 3.5 個約為 1 Token。
    """
    if isinstance(obj, str):
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False)
    
    chinese_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_count = len(text) - chinese_count
    tokens = int(chinese_count / 1.2 + other_count / 3.5)
    return max(1, tokens)


def prune_context_by_budget(
    context: Dict[str, Any],
    token_budget: int,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    當投影上下文超出 token_budget 時，依優先級實施五級安全剪裁：
      Tier 1: 移除遠程非因果邊與主題關聯
      Tier 2: 剪裁超過 1 跳的歷史前置節點 (保留最近前置)
      Tier 3: 精簡登場角色資料（保留 ID、姓名、當前節點身份、初始狀態，省略詳細背景）
      Tier 4: 精簡前置節點結果描述（壓縮為單行摘要）
      Tier 5: 精簡當前節點九維事件之次要欄位 (行動動機與後續影響)，嚴格保留核心衝突、結果與摘要
    """
    pruned = copy.deepcopy(context)
    applied_tiers: List[str] = []

    if estimate_tokens(pruned) <= token_budget:
        return pruned, applied_tiers

    # Tier 1: 移除遠程邊或輔助連結
    if "remote_connections" in pruned:
        del pruned["remote_connections"]
        applied_tiers.append("TIER_1_PRUNE_REMOTE_LINKS")
        if estimate_tokens(pruned) <= token_budget:
            return pruned, applied_tiers

    # Tier 2: 剪裁過遠的前置節點 (保留最近 2 個)
    if "upstream_predecessors" in pruned:
        preds = pruned["upstream_predecessors"]
        if len(preds) > 2:
            pruned["upstream_predecessors"] = preds[:2]
            applied_tiers.append("TIER_2_PRUNE_DISTANT_ANCESTORS")
            if estimate_tokens(pruned) <= token_budget:
                return pruned, applied_tiers

    # Tier 3: 精簡角色檔案
    scene = pruned.get("current_scene_contract", {})
    if "participating_characters" in scene:
        condensed_chars = []
        for ch in scene["participating_characters"]:
            condensed_chars.append({
                "character_id": ch.get("character_id", ch.get("char_id")),
                "name": ch.get("name", ""),
                "role_in_node": ch.get("role_in_node", "PARTICIPANT"),
                "initial_status": ch.get("initial_status", "NORMAL"),
            })
        scene["participating_characters"] = condensed_chars
        applied_tiers.append("TIER_3_CONDENSE_CHARACTERS")
        if estimate_tokens(pruned) <= token_budget:
            return pruned, applied_tiers

    # Tier 4: 精簡前置節點結果
    if "upstream_predecessors" in pruned:
        condensed_preds = []
        for p in pruned["upstream_predecessors"]:
            condensed_preds.append({
                "node_id": p.get("node_id"),
                "outcomes": [str(o)[:80] for o in p.get("outcomes", [])],
                "state_mutations": p.get("state_mutations", [])[:2],
            })
        pruned["upstream_predecessors"] = condensed_preds
        applied_tiers.append("TIER_4_CONDENSE_PREDECESSORS")
        if estimate_tokens(pruned) <= token_budget:
            return pruned, applied_tiers

    # Tier 5: 精簡當前九維事件次要欄位
    if "story_events" in scene:
        condensed_events = []
        for ev in scene["story_events"]:
            ev_copy = dict(ev)
            ev_copy.pop("action_motives", None)
            ev_copy.pop("downstream_impact", None)
            condensed_events.append(ev_copy)
        scene["story_events"] = condensed_events
        applied_tiers.append("TIER_5_CONDENSE_SECONDARY_EVENT_FIELDS")

    return pruned, applied_tiers


# =============================================================================
# 3. MasterGraphService 服務類
# =============================================================================

class MasterGraphService:
    """
    Master Graph 單一真相核心服務。
    提供槽位回填、防劇透上下文投影、草稿暫存與原子提交、正典鎖定全套生命週期方法。
    """

    # -------------------------------------------------------------------------
    # A. 槽位原子回填 (Slot Backfilling Methods)
    # -------------------------------------------------------------------------

    @staticmethod
    def backfill_worldview_slot(
        graph: GeometryGraph,
        node_id: str,
        worldview_data: Dict[str, Any],
        overwrite: bool = True,
    ) -> NodeStoryContract:
        """
        Stage 03: 回填世界觀槽位 (faction_ids, location_id, conflict_cause, rules)。
        同步更新 node.semantic 以相容既有幾何查詢。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")
        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        if contract.worldview_slot and not overwrite:
            merged = dict(contract.worldview_slot)
            merged.update(worldview_data)
            contract.worldview_slot = merged
        else:
            contract.worldview_slot = dict(worldview_data)

        # 雙向同步
        node.semantic = contract.worldview_slot
        node.metadata["_story_contract"] = contract.to_dict()
        graph.story_contracts[node_id] = contract
        return contract

    @staticmethod
    def backfill_character_slots(
        graph: GeometryGraph,
        node_id: str,
        character_slots: List[Dict[str, Any]],
        append: bool = False,
    ) -> NodeStoryContract:
        """
        Stage 04: 回填角色槽位 (客觀屬性、當前節點身份、初始狀態，無劇透)。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")
        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        if append:
            existing_map = {
                c.get("character_id", c.get("char_id")): c
                for c in contract.character_slots
                if isinstance(c, dict)
            }
            for char_item in character_slots:
                cid = char_item.get("character_id", char_item.get("char_id"))
                if cid and cid in existing_map:
                    existing_map[cid].update(char_item)
                else:
                    contract.character_slots.append(dict(char_item))
        else:
            contract.character_slots = [dict(c) for c in character_slots]

        node.metadata["_story_contract"] = contract.to_dict()
        graph.story_contracts[node_id] = contract
        return contract

    @staticmethod
    def backfill_story_events(
        graph: GeometryGraph,
        node_id: str,
        story_events: List[Union[StoryEventContract, Dict[str, Any]]],
        append: bool = False,
        validate: bool = False,
        strict: bool = False,
    ) -> NodeStoryContract:
        """
        Stage 05: 回填九維具體故事事件契約 (StoryEventContract)。
        可選擇性執行 validate_nine_dimensions 驗證。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")
        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        converted_events: List[StoryEventContract] = []
        for item in story_events:
            if isinstance(item, dict):
                ev = StoryEventContract.from_dict(item)
            elif isinstance(item, StoryEventContract):
                ev = item
            else:
                raise TypeError(f"Unsupported story event type: {type(item)}")
            
            if not ev.node_id:
                ev.node_id = node_id

            if validate:
                valid, defects = ev.validate_nine_dimensions(strict=strict)
                if not valid and strict:
                    raise ValueError(f"StoryEvent {ev.event_id} validation failed: {defects}")
            converted_events.append(ev)

        if append:
            id_to_idx = {e.event_id: i for i, e in enumerate(contract.story_events)}
            for new_ev in converted_events:
                if new_ev.event_id in id_to_idx:
                    contract.story_events[id_to_idx[new_ev.event_id]] = new_ev
                else:
                    contract.story_events.append(new_ev)
        else:
            contract.story_events = converted_events

        node.metadata["_story_contract"] = contract.to_dict()
        graph.story_contracts[node_id] = contract
        return contract

    @staticmethod
    def backfill_destiny_events(
        graph: GeometryGraph,
        node_id: str,
        destiny_events: List[Dict[str, Any]],
        append: bool = False,
    ) -> NodeStoryContract:
        """
        Stage 05: 回填角色重大命運變遷記錄 (BETRAYAL, DEATH, TRANSFORMATION)。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")
        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        if append:
            existing_keys = {
                (d.get("char_id"), d.get("type")): i
                for i, d in enumerate(contract.destiny_events)
                if isinstance(d, dict)
            }
            for item in destiny_events:
                k = (item.get("char_id"), item.get("type"))
                if k in existing_keys:
                    contract.destiny_events[existing_keys[k]].update(item)
                else:
                    contract.destiny_events.append(dict(item))
        else:
            contract.destiny_events = [dict(d) for d in destiny_events]

        node.metadata["_story_contract"] = contract.to_dict()
        graph.story_contracts[node_id] = contract
        return contract

    @staticmethod
    def backfill_foreshadowing_tasks(
        graph: GeometryGraph,
        node_id: str,
        foreshadowing_tasks: List[Dict[str, Any]],
        append: bool = False,
    ) -> NodeStoryContract:
        """
        Stage 05: 回填伏筆任務 (clue_id, role=PLANT/TURN/PAYOFF, summary, bindings)。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")
        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        if append:
            existing_map = {
                t.get("clue_id"): i
                for i, t in enumerate(contract.foreshadowing_tasks)
                if isinstance(t, dict) and "clue_id" in t
            }
            for item in foreshadowing_tasks:
                cid = item.get("clue_id")
                if cid and cid in existing_map:
                    contract.foreshadowing_tasks[existing_map[cid]].update(item)
                else:
                    contract.foreshadowing_tasks.append(dict(item))
        else:
            contract.foreshadowing_tasks = [dict(t) for t in foreshadowing_tasks]

        node.metadata["_story_contract"] = contract.to_dict()
        graph.story_contracts[node_id] = contract
        return contract

    @staticmethod
    def backfill_chapter_mappings(
        graph: GeometryGraph,
        node_id: str,
        chapter_mappings: List[Dict[str, Any]],
        append: bool = False,
    ) -> NodeStoryContract:
        """
        Stage 07: 回填多對多章節拍點映射 (chapter_index, beat_index, coverage_ratio)。
        自動同步更新 node.chapter_window 座標範圍。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")
        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        if append:
            existing_map = {
                (m.get("chapter_index"), m.get("beat_index")): i
                for i, m in enumerate(contract.chapter_mappings)
                if isinstance(m, dict)
            }
            for item in chapter_mappings:
                k = (item.get("chapter_index"), item.get("beat_index"))
                if k in existing_map:
                    contract.chapter_mappings[existing_map[k]].update(item)
                else:
                    contract.chapter_mappings.append(dict(item))
        else:
            contract.chapter_mappings = [dict(m) for m in chapter_mappings]

        # 同步更新 node.chapter_window
        chs = [
            m["chapter_index"]
            for m in contract.chapter_mappings
            if isinstance(m, dict) and "chapter_index" in m and isinstance(m["chapter_index"], int)
        ]
        if chs:
            node.chapter_window = (min(chs), max(chs))

        node.metadata["_story_contract"] = contract.to_dict()
        graph.story_contracts[node_id] = contract
        return contract

    @classmethod
    def backfill_slot(
        cls,
        graph: GeometryGraph,
        node_id: str,
        slot_name: str,
        slot_data: Any,
        append: bool = False,
        **kwargs,
    ) -> NodeStoryContract:
        """
        通用槽位分派器，自動路由至對應型別之專屬回填方法。
        """
        s = slot_name.lower().strip()
        if s in ("worldview", "worldview_slot"):
            return cls.backfill_worldview_slot(graph, node_id, slot_data, overwrite=not append)
        elif s in ("character", "characters", "character_slots"):
            data_list = slot_data if isinstance(slot_data, list) else [slot_data]
            return cls.backfill_character_slots(graph, node_id, data_list, append=append)
        elif s in ("story_events", "story_event", "events"):
            data_list = slot_data if isinstance(slot_data, list) else [slot_data]
            return cls.backfill_story_events(graph, node_id, data_list, append=append, **kwargs)
        elif s in ("destiny", "destiny_events"):
            data_list = slot_data if isinstance(slot_data, list) else [slot_data]
            return cls.backfill_destiny_events(graph, node_id, data_list, append=append)
        elif s in ("foreshadowing", "foreshadowing_tasks", "clues"):
            data_list = slot_data if isinstance(slot_data, list) else [slot_data]
            return cls.backfill_foreshadowing_tasks(graph, node_id, data_list, append=append)
        elif s in ("chapter_mappings", "beats", "chapters"):
            data_list = slot_data if isinstance(slot_data, list) else [slot_data]
            return cls.backfill_chapter_mappings(graph, node_id, data_list, append=append)
        else:
            node = graph.nodes[node_id]
            node.metadata[slot_name] = slot_data
            contract = graph.get_story_contract(node_id) or node.ensure_story_contract()
            return contract

    # -------------------------------------------------------------------------
    # B. 作用域上下文投影與防劇透護盾 (Scoped Context Projection & Spoiler Wall)
    # -------------------------------------------------------------------------

    @staticmethod
    def project_node_context(
        graph: GeometryGraph,
        node_id: str,
        target_agent: str,
        token_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        依據調用者角色派發具備精確權限邊界的節點上下文：
        - chapter_writer: 啟用嚴格防劇透牆 (Strict Spoiler Wall)。
          1. 遮蔽未來卷次大綱與摘要 (subsequent volumes masked)
          2. 遮蔽下游因果後續節點之重大轉折、具體事件與結果 (masked downstream twists)
          3. 遮蔽未到期伏筆之回收核心真相 (future payoffs masked)
          4. 遮蔽角色未來命運終局 (future destiny masked)
        - editor: 提供場景原料與事實保全基準線 (fact_preservation_baseline)，供 Fact Diff Guard 守衛。
        - director / gate / admin: 全域透明無遮蔽。
        - 支援動態 token_budget 精確剪裁。
        """
        if node_id not in graph.nodes:
            raise KeyError(f"Node '{node_id}' does not exist in graph.")

        node = graph.nodes[node_id]
        contract = graph.get_story_contract(node_id) or node.ensure_story_contract()

        target = target_agent.lower().strip()
        is_writer = target in ("chapter_writer", "writer")
        is_editor = target in ("editor", "stylistic_editor")

        current_vol = node.hierarchy.volume_index if node.hierarchy else 1
        current_arc = node.hierarchy.arc_index if node.hierarchy else 1
        current_chs = node.chapter_window

        # 1. 伏筆任務防劇透過濾
        projected_foreshadowing = []
        for task in contract.foreshadowing_tasks:
            t_copy = dict(task)
            role = str(t_copy.get("role", "")).upper()
            if is_writer:
                if role == "PLANT":
                    # 保留當前埋設指令與表面線索，遮蔽未來揭密與結局
                    t_copy["future_payoff_target"] = "[SPOILER_PROTECTED_FUTURE_PAYOFF]"
                    t_copy.pop("secret_core_truth", None)
                    t_copy.pop("payoff_chapter", None)
                    t_copy.pop("payoff_node_id", None)
                    projected_foreshadowing.append(t_copy)
                elif role == "PAYOFF":
                    # 僅當回收章節落入當前節點章節範圍時才曝光
                    payoff_ch = t_copy.get("chapter_index", current_chs[0])
                    if current_chs[0] <= payoff_ch <= current_chs[1]:
                        projected_foreshadowing.append(t_copy)
                elif role == "TURN":
                    turn_ch = t_copy.get("chapter_index", current_chs[0])
                    if current_chs[0] <= turn_ch <= current_chs[1]:
                        projected_foreshadowing.append(t_copy)
            else:
                projected_foreshadowing.append(t_copy)

        # 2. 角色去命運化投影
        projected_characters = []
        for ch in contract.character_slots:
            ch_copy = dict(ch)
            if is_writer:
                # 剔除未來命運劇透
                ch_copy.pop("future_destiny", None)
                ch_copy.pop("ultimate_fate", None)
            projected_characters.append(ch_copy)

        # 3. 歷史前置因果連續性 (Upstream Causal Predecessors)
        upstream_preds = []
        for pred_id in graph.get_causal_predecessors(node_id):
            pnode = graph.get_node(pred_id)
            if not pnode:
                continue
            pcontract = graph.get_story_contract(pred_id) or pnode.ensure_story_contract()
            upstream_preds.append({
                "node_id": pred_id,
                "structural_role": pnode.structural_role.value if hasattr(pnode.structural_role, "value") else str(pnode.structural_role),
                "chapter_window": pnode.chapter_window,
                "outcomes": [ev.direct_outcome for ev in pcontract.story_events if ev.direct_outcome],
                "state_mutations": [m for ev in pcontract.story_events for m in ev.state_mutations],
            })

        # 4. 後續走勢防劇透 (Downstream Trajectory)
        downstream_trajectory = []
        for succ_id in graph.get_causal_successors(node_id):
            snode = graph.get_node(succ_id)
            if not snode:
                continue
            if is_writer:
                # 嚴格防劇透牆：不暴露未來具體劇情事件
                downstream_trajectory.append({
                    "node_id": succ_id,
                    "structural_role": snode.structural_role.value if hasattr(snode.structural_role, "value") else str(snode.structural_role),
                    "spoiler_shield": "SPOILER_WALL_ACTIVE: Content masked to preserve organic narrative tension.",
                })
            else:
                scontract = graph.get_story_contract(succ_id) or snode.ensure_story_contract()
                downstream_trajectory.append({
                    "node_id": succ_id,
                    "structural_role": snode.structural_role.value if hasattr(snode.structural_role, "value") else str(snode.structural_role),
                    "volume_index": snode.hierarchy.volume_index if snode.hierarchy else 1,
                    "event_summaries": [ev.event_summary for ev in scontract.story_events],
                    "core_conflicts": [ev.core_conflict for ev in scontract.story_events],
                })

        # 5. 篇卷上下文 (Volume Context)
        volume_context: Dict[str, Any] = {}
        curr_vol_container = graph.volumes.get(f"vol_{current_vol:02d}") or graph.volumes.get(str(current_vol))
        if curr_vol_container:
            volume_context["current_volume"] = {
                "volume_index": curr_vol_container.volume_index,
                "chapter_range": curr_vol_container.chapter_range,
                "semantic": curr_vol_container.semantic,
            }
        else:
            volume_context["current_volume"] = {
                "volume_index": current_vol,
                "chapter_range": current_chs,
            }

        if is_writer:
            # 遮蔽未來卷大綱
            volume_context["subsequent_volumes"] = "[PROTECTED_BY_SPOILER_WALL]"
        else:
            volume_context["all_volumes"] = {
                vid: {"volume_index": v.volume_index, "chapter_range": v.chapter_range}
                for vid, v in graph.volumes.items()
            }

        projected = {
            "target_agent": target_agent,
            "projected_at": datetime.utcnow().isoformat() + "Z",
            "graph_revision": graph.graph_revision,
            "node_id": node_id,
            "chapter_window": node.chapter_window,
            "volume_index": current_vol,
            "arc_index": current_arc,
            "structural_role": node.structural_role.value if hasattr(node.structural_role, "value") else str(node.structural_role),
            "node_type": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
            "thread_memberships": list(node.thread_memberships),
            "current_scene_contract": {
                "worldview_context": contract.worldview_slot or {},
                "participating_characters": projected_characters,
                "story_events": [ev.to_dict() for ev in contract.story_events],
                "foreshadowing_tasks": projected_foreshadowing,
                "destiny_events": list(contract.destiny_events),
                "chapter_mappings": contract.chapter_mappings,
            },
            "upstream_predecessors": upstream_preds,
            "downstream_trajectory": downstream_trajectory,
            "volume_context": volume_context,
            "spoiler_wall_active": is_writer,
        }

        # 針對 Editor 提供 Fact Diff Guard 保全基準線
        if is_editor:
            projected["fact_preservation_baseline"] = {
                "required_participants": [
                    p.get("char_id")
                    for ev in contract.story_events
                    for p in ev.participant_entities
                    if isinstance(p, dict) and "char_id" in p
                ],
                "required_core_conflicts": [ev.core_conflict for ev in contract.story_events if ev.core_conflict],
                "required_outcomes": [ev.direct_outcome for ev in contract.story_events if ev.direct_outcome],
                "required_state_mutations": [m for ev in contract.story_events for m in ev.state_mutations],
            }

        # 6. 動態 Token 預算剪裁
        raw_tokens = estimate_tokens(projected)
        if token_budget is not None and raw_tokens > token_budget:
            pruned, applied_tiers = prune_context_by_budget(projected, token_budget)
            final_tokens = estimate_tokens(pruned)
            pruned["token_metrics"] = {
                "initial_tokens": raw_tokens,
                "final_tokens": final_tokens,
                "token_budget": token_budget,
                "pruned": True,
                "pruning_tiers_applied": applied_tiers,
            }
            return pruned
        else:
            projected["token_metrics"] = {
                "initial_tokens": raw_tokens,
                "final_tokens": raw_tokens,
                "token_budget": token_budget,
                "pruned": False,
                "pruning_tiers_applied": [],
            }
            return projected

    # -------------------------------------------------------------------------
    # C. 草稿補丁暫存與原子版本提交 (Draft Patch Staging & Atomic Revision Commit)
    # -------------------------------------------------------------------------

    @staticmethod
    def create_draft_patch(graph: GeometryGraph, novel_id: str = "") -> DraftGraphPatch:
        """建立全新草稿補丁，基準版本鎖定為當前 graph_revision。"""
        return DraftGraphPatch(
            patch_id=f"PATCH_{uuid.uuid4().hex[:12]}",
            base_revision=graph.graph_revision,
            novel_id=novel_id,
            status="PENDING",
        )

    @staticmethod
    def _restore_from_snapshot(graph: GeometryGraph, snapshot: GeometryGraph) -> None:
        """自深拷貝快照原子回滾主圖狀態。"""
        graph.nodes = snapshot.nodes
        graph.edges = snapshot.edges
        graph.threads = snapshot.threads
        graph.volumes = snapshot.volumes
        graph.arcs = snapshot.arcs
        graph.sequences = snapshot.sequences
        graph.graph_revision = snapshot.graph_revision
        graph.story_contracts = snapshot.story_contracts
        graph.params = snapshot.params
        if hasattr(snapshot, "planning_status"):
            graph.planning_status = snapshot.planning_status

    @classmethod
    def apply_draft_patch(cls, graph: GeometryGraph, patch: DraftGraphPatch) -> None:
        """
        將草稿補丁套用至圖譜以供局部門禁驗證。
        自動保存深度快照，失敗時完全原子回滾。
        """
        if patch.status != "PENDING":
            raise ValueError(f"Cannot apply patch with status '{patch.status}' (expected PENDING)")
        if patch.base_revision != graph.graph_revision:
            raise ValueError(
                f"Concurrency conflict: patch base_revision ({patch.base_revision}) "
                f"!= graph_revision ({graph.graph_revision})"
            )

        # 備份快照
        patch._snapshot = copy.deepcopy(graph)

        try:
            # 1. 套用節點新增
            for nid, contract in patch.node_additions.items():
                if nid not in graph.nodes:
                    graph.add_node(contract.to_geometry_node())
                else:
                    graph.set_story_contract(contract)

            # 2. 套用節點槽位更新
            for nid, updates in patch.node_updates.items():
                if nid not in graph.nodes:
                    raise KeyError(f"Patch references non-existent node '{nid}'")
                for field_name, field_val in updates.items():
                    cls.backfill_slot(graph, nid, field_name, field_val, append=False)

            # 3. 套用邊新增
            for edge_contract in patch.edge_additions:
                graph.add_edge(edge_contract.to_geometry_edge())

            # 4. 套用邊刪除
            if patch.edge_deletions:
                del_edges = set(patch.edge_deletions)
                graph.edges = [e for e in graph.edges if e.edge_id not in del_edges]

            # 5. 套用節點刪除
            if patch.node_deletions:
                for del_nid in patch.node_deletions:
                    graph.nodes.pop(del_nid, None)
                    graph.story_contracts.pop(del_nid, None)
                del_nodes_set = set(patch.node_deletions)
                graph.edges = [
                    e for e in graph.edges
                    if e.source not in del_nodes_set and e.target not in del_nodes_set
                ]

            patch.status = "APPLIED"
        except Exception as err:
            if patch._snapshot:
                cls._restore_from_snapshot(graph, patch._snapshot)
                patch._snapshot = None
            patch.status = "DISCARDED"
            raise err

    @classmethod
    def commit_draft_patch(cls, graph: GeometryGraph, patch: DraftGraphPatch) -> int:
        """
        原子提交草稿補丁：
        1. 驗證樂觀並發控制
        2. 驗證因果邊 DAG 嚴格無環 (validate_causal_dag)
        3. 單調遞增 graph_revision (graph_revision += 1)
        4. 將新版本號蓋章至所有受波及的節點與邊
        5. 釋放快照記憶體並將補丁標記為 COMMITTED
        """
        if patch.status == "PENDING":
            cls.apply_draft_patch(graph, patch)
        elif patch.status != "APPLIED":
            raise ValueError(f"Cannot commit patch with status '{patch.status}' (expected APPLIED or PENDING)")

        # 並發版本檢查
        if patch.base_revision != graph.graph_revision:
            cls.discard_draft_patch(patch, graph)
            raise ValueError(
                f"Optimistic concurrency check failed: patch base_revision={patch.base_revision}, "
                f"current graph_revision={graph.graph_revision}"
            )

        # 因果 DAG 嚴格無環驗證
        dag_defects = graph.validate_causal_dag()
        if dag_defects:
            cls.discard_draft_patch(patch, graph)
            raise ValueError(f"Causal DAG validation failed upon commit: {dag_defects}")

        # 單調遞增版本號
        graph.graph_revision += 1
        new_rev = graph.graph_revision

        # 蓋章新版本號
        touched_nodes = set(patch.node_updates.keys()) | set(patch.node_additions.keys())
        for nid in touched_nodes:
            if nid in graph.nodes:
                graph.nodes[nid].graph_revision = new_rev
            if nid in graph.story_contracts:
                graph.story_contracts[nid].graph_revision = new_rev

        for e in patch.edge_additions:
            for ge in graph.edges:
                if ge.edge_id == e.edge_id:
                    ge.graph_revision = new_rev

        patch.status = "COMMITTED"
        patch._snapshot = None  # 釋放快照
        return new_rev

    @classmethod
    def discard_draft_patch(cls, patch: DraftGraphPatch, graph: Optional[GeometryGraph] = None) -> None:
        """丟棄補丁並回滾主圖狀態。"""
        if patch._snapshot is not None and graph is not None:
            cls._restore_from_snapshot(graph, patch._snapshot)
            patch._snapshot = None
        patch.status = "DISCARDED"

    # -------------------------------------------------------------------------
    # D. 故事正典鎖定 (Canon Locking)
    # -------------------------------------------------------------------------

    @staticmethod
    def lock_story_canon(graph: GeometryGraph) -> Dict[str, Any]:
        """
        Stage 08: 故事正典鎖定 (Story Canon Locking)。
        StoryCompletionGate 驗收全書無漏洞後調用，
        將全圖所有節點之 planning_status 標記為 STORY_CANON_LOCKED。
        正文寫作流水線只得以此鎖定版本為唯一真相進行撰寫。
        """
        graph.planning_status = PlanningStatus.STORY_CANON_LOCKED
        count = 0
        for nid, node in graph.nodes.items():
            node.planning_status = PlanningStatus.STORY_CANON_LOCKED
            contract = graph.get_story_contract(nid) or node.ensure_story_contract()
            contract.planning_status = PlanningStatus.STORY_CANON_LOCKED
            node.metadata["planning_status"] = PlanningStatus.STORY_CANON_LOCKED.value
            node.metadata["_story_contract"] = contract.to_dict()
            graph.story_contracts[nid] = contract
            count += 1

        return {
            "success": True,
            "planning_status": PlanningStatus.STORY_CANON_LOCKED.value,
            "nodes_locked": count,
            "graph_revision": graph.graph_revision,
            "locked_at": datetime.utcnow().isoformat() + "Z",
        }


# Module singleton instance
master_graph_service = MasterGraphService()

__all__ = [
    "MasterGraphService",
    "master_graph_service",
    "DraftGraphPatch",
    "estimate_tokens",
    "prune_context_by_budget",
]
