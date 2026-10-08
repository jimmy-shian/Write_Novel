"""
幾何圖核心資料模型 (Geometry Core Data Models & Narrative Contracts)。
定義了節點（Node）、邊（Edge）、線索（Thread）以及容器（Volume, Arc, Sequence），
並提供了主結構 GeometryGraph 管理這些元素的關聯。
包含九維故事契約（StoryEventContract）、Master Graph 節點契約（NodeStoryContract）、
邊契約實體（MasterGraphEdgeContract / MASTER_GRAPH_EDGES）、雙軌狀態與有向無環圖 (DAG) 因果驗證。
"""

import copy
import uuid
from collections import deque
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple, Any, Set, Union


class StructuralRole(str, Enum):
    """節點的結構角色"""
    OPEN_THREAD = 'OPEN_THREAD'
    DEVELOP = 'DEVELOP'
    ESCALATE = 'ESCALATE'
    BRANCH = 'BRANCH'
    REVISIT = 'REVISIT'
    ECHO = 'ECHO'
    CONVERGE = 'CONVERGE'
    CHARACTER_SHIFT = 'CHARACTER_SHIFT'
    RELATIONSHIP_CHANGE = 'RELATIONSHIP_CHANGE'
    PAYOFF = 'PAYOFF'
    TRANSITION = 'TRANSITION'
    CLOSE = 'CLOSE'


class EdgeType(str, Enum):
    """節點間的關聯邊類型"""
    CAUSES = 'CAUSES'
    ENABLES = 'ENABLES'
    SETS_UP = 'SETS_UP'
    ECHOES = 'ECHOES'
    PAYS_OFF = 'PAYS_OFF'
    CONVERGES = 'CONVERGES'
    RELATIONSHIP_CHANGE = 'RELATIONSHIP_CHANGE'
    CHARACTER_ARC = 'CHARACTER_ARC'
    CONTRASTS = 'CONTRASTS'
    PARALLELS = 'PARALLELS'
    SHARED_ENTITY = 'SHARED_ENTITY'
    REACTIVATES = 'REACTIVATES'
    ESCALATES = 'ESCALATES'
    TRANSFORMS = 'TRANSFORMS'


class ThreadType(str, Enum):
    """線索類型"""
    MAIN = 'MAIN'
    SUBPLOT = 'SUBPLOT'
    CHARACTER_ARC = 'CHARACTER_ARC'
    RELATIONSHIP_ARC = 'RELATIONSHIP_ARC'
    THEMATIC = 'THEMATIC'


class GeometryComplexity(str, Enum):
    """幾何圖複雜度設定"""
    SPARSE = 'SPARSE'
    STANDARD = 'STANDARD'
    DENSE = 'DENSE'
    VERY_DENSE = 'VERY_DENSE'


class RepairOperation(str, Enum):
    """修復操作類型"""
    SPLIT = 'SPLIT'
    EXPAND = 'EXPAND'
    INSERT = 'INSERT'
    COMPRESS = 'COMPRESS'


class PlanningStatus(str, Enum):
    """
    軌道 A: Master Graph 節點規劃生命週期狀態
    DRAFT -> GATE_PASSED -> STORY_CANON_LOCKED <-> REVISION_PENDING
    """
    DRAFT = "DRAFT"
    GATE_PASSED = "GATE_PASSED"
    STORY_CANON_LOCKED = "STORY_CANON_LOCKED"
    REVISION_PENDING = "REVISION_PENDING"


class RealizationStatus(str, Enum):
    """
    軌道 B: 正文實現生命週期狀態
    PENDING -> PARTIAL -> REALIZED
    """
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    REALIZED = "REALIZED"


class NodeType(str, Enum):
    """Master Graph 節點敘事類型"""
    FACTION_COLLISION = "FACTION_COLLISION"
    CRISIS = "CRISIS"
    SECRET_REVEAL = "SECRET_REVEAL"
    TRANSFORMATION = "TRANSFORMATION"
    TURNING_POINT = "TURNING_POINT"
    CLIMAX = "CLIMAX"
    DEVELOPMENT = "DEVELOPMENT"


class ForeshadowingDemand(str, Enum):
    """伏筆需求類型"""
    NONE = "NONE"
    REQUIRES_PLANT = "REQUIRES_PLANT"
    MUST_PAYOFF = "MUST_PAYOFF"
    TURN_SITE = "TURN_SITE"


# 因果邊集合 (受嚴格有向無環圖 DAG 約束)
CAUSAL_EDGE_TYPES: Set[EdgeType] = {
    EdgeType.CAUSES,
    EdgeType.ENABLES,
    EdgeType.ESCALATES,
}

# 非因果邊集合 (高級敘事、主題、對比與伏筆回響，不受 DAG 無環約束)
NON_CAUSAL_EDGE_TYPES: Set[EdgeType] = {
    EdgeType.SETS_UP,
    EdgeType.ECHOES,
    EdgeType.PAYS_OFF,
    EdgeType.CONVERGES,
    EdgeType.RELATIONSHIP_CHANGE,
    EdgeType.CHARACTER_ARC,
    EdgeType.CONTRASTS,
    EdgeType.PARALLELS,
    EdgeType.SHARED_ENTITY,
    EdgeType.REACTIVATES,
    EdgeType.TRANSFORMS,
}


def is_causal_edge(edge_type: Union[EdgeType, str]) -> bool:
    """判斷指定邊類型是否為因果約束邊"""
    if isinstance(edge_type, str):
        try:
            edge_type = EdgeType(edge_type)
        except ValueError:
            return False
    return edge_type in CAUSAL_EDGE_TYPES


@dataclass
class StoryEventContract:
    """
    單一節點內具體發生的九維故事事件契約 (The 9-Dimension Story Event Contract)
    Single Source of Truth 具體劇情承載體。
    """
    event_id: str                              # 事件唯一識別碼，如 "EV_G0038_01"
    node_id: str                               # 所屬節點編號，如 "G0038"
    event_summary: str                         # 1. 具體發生了什麼事 (清晰場景核心事件)
    participant_entities: List[Dict[str, Any]] = field(default_factory=list) # 2. 參與角色與勢力
    action_motives: List[Dict[str, Any]] = field(default_factory=list)       # 3. 核心行動動機
    causal_preconditions: List[str] = field(default_factory=list)            # 4. 前置促發事件清單
    core_conflict: str = ""                    # 5. 正面衝突焦點
    direct_outcome: str = ""                   # 6. 事件直接結果
    state_mutations: List[Dict[str, Any]] = field(default_factory=list)      # 7. 狀態改變清單
    downstream_impact: List[str] = field(default_factory=list)               # 8. 後續引發之必然反應與危機
    clue_bindings: List[str] = field(default_factory=list)                   # 9. 關聯之伏筆編號

    def validate_nine_dimensions(self, strict: bool = False) -> Tuple[bool, List[str]]:
        """
        驗證九維故事契約是否完整填滿 (供 TwistGate 驗收使用)。
        strict=True 時要求 state_mutations, downstream_impact, clue_bindings 必須非空。
        """
        defects = []
        if not self.event_summary or not str(self.event_summary).strip():
            defects.append("event_summary (事件具體內容) 為空")
        if not isinstance(self.participant_entities, list):
            defects.append("participant_entities 必須為清單")
        elif not self.participant_entities:
            defects.append("participant_entities (參與實體) 為空")
        if not isinstance(self.action_motives, list):
            defects.append("action_motives 必須為清單")
        elif not self.action_motives:
            defects.append("action_motives (核心行動動機) 為空")
        if not isinstance(self.causal_preconditions, list):
            defects.append("causal_preconditions 必須為清單")
        if not self.core_conflict or not str(self.core_conflict).strip():
            defects.append("core_conflict (正面衝突焦點) 為空")
        if not self.direct_outcome or not str(self.direct_outcome).strip():
            defects.append("direct_outcome (事件直接結果) 為空")
        if not isinstance(self.state_mutations, list):
            defects.append("state_mutations 必須為清單")
        elif strict and len(self.state_mutations) == 0:
            defects.append("state_mutations (狀態改變清單) 為空")
        if not isinstance(self.downstream_impact, list):
            defects.append("downstream_impact 必須為清單")
        elif strict and len(self.downstream_impact) == 0:
            defects.append("downstream_impact (後續引發危機) 為空")
        if not isinstance(self.clue_bindings, list):
            defects.append("clue_bindings 必須為清單")
        elif strict and len(self.clue_bindings) == 0:
            defects.append("clue_bindings (關聯伏筆清單) 為空")

        return (len(defects) == 0, defects)

    def validate_9_dimensions(self, strict: bool = False) -> List[str]:
        """驗證方法別名，直接返回缺陷列表。"""
        _, defects = self.validate_nine_dimensions(strict=strict)
        return defects

    def is_complete(self, strict: bool = False) -> bool:
        """判定九維契約是否完備無缺。"""
        valid, _ = self.validate_nine_dimensions(strict=strict)
        return valid

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        participants = []
        if isinstance(self.participant_entities, list):
            for p in self.participant_entities:
                participants.append(dict(p) if isinstance(p, dict) else p)
        else:
            participants = self.participant_entities

        motives = []
        if isinstance(self.action_motives, list):
            for m in self.action_motives:
                motives.append(dict(m) if isinstance(m, dict) else m)
        else:
            motives = self.action_motives

        mutations = []
        if isinstance(self.state_mutations, list):
            for s in self.state_mutations:
                mutations.append(dict(s) if isinstance(s, dict) else s)
        else:
            mutations = self.state_mutations

        return {
            "event_id": self.event_id,
            "node_id": self.node_id,
            "event_summary": self.event_summary,
            "participant_entities": participants,
            "action_motives": motives,
            "causal_preconditions": list(self.causal_preconditions) if isinstance(self.causal_preconditions, list) else self.causal_preconditions,
            "core_conflict": self.core_conflict,
            "direct_outcome": self.direct_outcome,
            "state_mutations": mutations,
            "downstream_impact": list(self.downstream_impact) if isinstance(self.downstream_impact, list) else self.downstream_impact,
            "clue_bindings": list(self.clue_bindings) if isinstance(self.clue_bindings, list) else self.clue_bindings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryEventContract":
        """從字典反序列化"""
        return cls(
            event_id=data.get("event_id", ""),
            node_id=data.get("node_id", ""),
            event_summary=data.get("event_summary", ""),
            participant_entities=list(data.get("participant_entities", [])),
            action_motives=list(data.get("action_motives", [])),
            causal_preconditions=list(data.get("causal_preconditions", [])),
            core_conflict=data.get("core_conflict", ""),
            direct_outcome=data.get("direct_outcome", ""),
            state_mutations=list(data.get("state_mutations", [])),
            downstream_impact=list(data.get("downstream_impact", [])),
            clue_bindings=list(data.get("clue_bindings", [])),
        )


@dataclass
class MasterGraphEdgeContract:
    """Master Graph 邊契約實體 (MASTER_GRAPH_EDGES)"""
    edge_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    graph_revision: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    semantic: Optional[Dict[str, Any]] = None

    @property
    def is_causal(self) -> bool:
        """判斷是否為因果約束邊"""
        return self.edge_type in CAUSAL_EDGE_TYPES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value if hasattr(self.edge_type, "value") else str(self.edge_type),
            "graph_revision": self.graph_revision,
            "metadata": self.metadata,
            "semantic": self.semantic,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MasterGraphEdgeContract":
        e_type = data.get("edge_type", EdgeType.CAUSES)
        if isinstance(e_type, str):
            e_type = EdgeType(e_type)
        return cls(
            edge_id=data["edge_id"],
            source_id=data.get("source_id") or data.get("source", ""),
            target_id=data.get("target_id") or data.get("target", ""),
            edge_type=e_type,
            graph_revision=int(data.get("graph_revision", 1)),
            metadata=dict(data.get("metadata", {})),
            semantic=data.get("semantic"),
        )

    def to_geometry_edge(self, distance: int = 0) -> "GeometryEdge":
        return GeometryEdge(
            edge_id=self.edge_id,
            source=self.source_id,
            target=self.target_id,
            edge_type=self.edge_type,
            distance=distance,
            semantic=self.semantic,
            metadata=self.metadata,
            graph_revision=self.graph_revision,
        )

    @classmethod
    def from_geometry_edge(cls, edge: "GeometryEdge") -> "MasterGraphEdgeContract":
        return cls(
            edge_id=edge.edge_id,
            source_id=edge.source,
            target_id=edge.target,
            edge_type=edge.edge_type,
            graph_revision=getattr(edge, "graph_revision", 1),
            metadata=dict(edge.metadata),
            semantic=edge.semantic,
        )


# Contract alias mapping
MASTER_GRAPH_EDGES = MasterGraphEdgeContract


@dataclass
class NodeStoryContract:
    """Master Graph 節點完整契約 (Single Source of Truth)"""
    # --- 拓樸純演算法生成 (Structural Function) ---
    node_id: str                               # 唯一識別碼，如 "G0038"
    volume_index: int                          # 所屬卷次 (1 ~ 10+)
    arc_index: int                             # 卷內弧線 (1 ~ 4)
    thread_memberships: List[str] = field(default_factory=list) # 多對多線程歸屬 (如 ["TM01", "TM03", "TS07"])
    structural_role: Union[StructuralRole, str] = StructuralRole.DEVELOP   # 結構功能
    node_type: Union[NodeType, str] = NodeType.FACTION_COLLISION           # 抽象事件類型
    foreshadowing_demand: Union[ForeshadowingDemand, str] = ForeshadowingDemand.NONE # 伏筆需求類型

    # --- 各 Agent 依序回填之故事要素槽位 (Concrete Story Fillings) ---
    worldview_slot: Optional[Dict[str, Any]] = None
    character_slots: List[Dict[str, Any]] = field(default_factory=list)
    story_events: List[StoryEventContract] = field(default_factory=list)
    destiny_events: List[Dict[str, Any]] = field(default_factory=list)
    foreshadowing_tasks: List[Dict[str, Any]] = field(default_factory=list)
    chapter_mappings: List[Dict[str, Any]] = field(default_factory=list)

    # --- 雙軌生命週期狀態與版本控制 (Dual-Track Lifecycle Status & Versioning) ---
    planning_status: Union[PlanningStatus, str] = PlanningStatus.DRAFT
    realization_status: Union[RealizationStatus, str] = RealizationStatus.PENDING
    graph_revision: int = 1

    def __post_init__(self):
        if isinstance(self.structural_role, str):
            try:
                self.structural_role = StructuralRole(self.structural_role)
            except ValueError:
                self.structural_role = StructuralRole.DEVELOP
        if isinstance(self.node_type, str):
            try:
                self.node_type = NodeType(self.node_type)
            except ValueError:
                self.node_type = NodeType.FACTION_COLLISION
        if isinstance(self.foreshadowing_demand, str):
            try:
                self.foreshadowing_demand = ForeshadowingDemand(self.foreshadowing_demand)
            except ValueError:
                self.foreshadowing_demand = ForeshadowingDemand.NONE
        if isinstance(self.planning_status, str):
            try:
                self.planning_status = PlanningStatus(self.planning_status)
            except ValueError:
                self.planning_status = PlanningStatus.DRAFT
        if isinstance(self.realization_status, str):
            try:
                self.realization_status = RealizationStatus(self.realization_status)
            except ValueError:
                self.realization_status = RealizationStatus.PENDING

        converted_events = []
        for ev in self.story_events:
            if isinstance(ev, dict):
                converted_events.append(StoryEventContract.from_dict(ev))
            elif isinstance(ev, StoryEventContract):
                converted_events.append(ev)
        self.story_events = converted_events

    @property
    def primary_thread(self) -> str:
        """向後相容 primary_thread：返回 thread_memberships 第一個"""
        return self.thread_memberships[0] if self.thread_memberships else ""

    @primary_thread.setter
    def primary_thread(self, val: str) -> None:
        if not val:
            return
        if val in self.thread_memberships:
            self.thread_memberships.remove(val)
        self.thread_memberships.insert(0, val)

    def belongs_to_thread(self, thread_id: str) -> bool:
        """判定該節點是否屬於指定線程"""
        return thread_id in self.thread_memberships

    def add_thread_membership(self, thread_id: str) -> None:
        """安全添加線程歸屬（防重複）"""
        if thread_id and thread_id not in self.thread_memberships:
            self.thread_memberships.append(thread_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "volume_index": self.volume_index,
            "arc_index": self.arc_index,
            "thread_memberships": list(self.thread_memberships),
            "structural_role": self.structural_role.value if hasattr(self.structural_role, "value") else str(self.structural_role),
            "node_type": self.node_type.value if hasattr(self.node_type, "value") else str(self.node_type),
            "foreshadowing_demand": self.foreshadowing_demand.value if hasattr(self.foreshadowing_demand, "value") else str(self.foreshadowing_demand),
            "worldview_slot": self.worldview_slot,
            "character_slots": self.character_slots,
            "story_events": [ev.to_dict() for ev in self.story_events],
            "destiny_events": self.destiny_events,
            "foreshadowing_tasks": self.foreshadowing_tasks,
            "chapter_mappings": self.chapter_mappings,
            "planning_status": self.planning_status.value if hasattr(self.planning_status, "value") else str(self.planning_status),
            "realization_status": self.realization_status.value if hasattr(self.realization_status, "value") else str(self.realization_status),
            "graph_revision": self.graph_revision,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeStoryContract":
        events_raw = data.get("story_events", [])
        events = [
            StoryEventContract.from_dict(ev) if isinstance(ev, dict) else ev
            for ev in events_raw
        ]
        return cls(
            node_id=data["node_id"],
            volume_index=data.get("volume_index", 1),
            arc_index=data.get("arc_index", 1),
            thread_memberships=list(data.get("thread_memberships", [])),
            structural_role=data.get("structural_role", StructuralRole.DEVELOP),
            node_type=data.get("node_type", NodeType.FACTION_COLLISION),
            foreshadowing_demand=data.get("foreshadowing_demand", ForeshadowingDemand.NONE),
            worldview_slot=data.get("worldview_slot"),
            character_slots=list(data.get("character_slots", [])),
            story_events=events,
            destiny_events=list(data.get("destiny_events", [])),
            foreshadowing_tasks=list(data.get("foreshadowing_tasks", [])),
            chapter_mappings=list(data.get("chapter_mappings", [])),
            planning_status=data.get("planning_status", PlanningStatus.DRAFT),
            realization_status=data.get("realization_status", RealizationStatus.PENDING),
            graph_revision=int(data.get("graph_revision", 1)),
        )

    def to_geometry_node(
        self,
        chapter_window: Optional[Tuple[int, int]] = None,
        sequence_index: int = 1,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "GeometryNode":
        """轉換為向後相容的 GeometryNode"""
        if chapter_window is None:
            if self.chapter_mappings:
                chs = [m.get("chapter_index", 1) for m in self.chapter_mappings if "chapter_index" in m]
                chapter_window = (min(chs), max(chs)) if chs else (1, 1)
            else:
                chapter_window = (1, 1)

        primary_thread = self.primary_thread
        meta = dict(metadata or {})
        meta["planning_status"] = self.planning_status.value if hasattr(self.planning_status, "value") else str(self.planning_status)
        meta["realization_status"] = self.realization_status.value if hasattr(self.realization_status, "value") else str(self.realization_status)
        meta["graph_revision"] = self.graph_revision
        meta["node_type"] = self.node_type.value if hasattr(self.node_type, "value") else str(self.node_type)
        meta["foreshadowing_demand"] = self.foreshadowing_demand.value if hasattr(self.foreshadowing_demand, "value") else str(self.foreshadowing_demand)
        meta["thread_memberships"] = list(self.thread_memberships)
        meta["_story_contract"] = self.to_dict()

        return GeometryNode(
            node_id=self.node_id,
            hierarchy=NodeHierarchy(
                volume_index=self.volume_index,
                arc_index=self.arc_index,
                sequence_index=sequence_index,
            ),
            chapter_window=chapter_window,
            structural_role=self.structural_role if isinstance(self.structural_role, StructuralRole) else StructuralRole(self.structural_role),
            primary_thread=primary_thread,
            importance=importance,
            semantic=self.worldview_slot,
            metadata=meta,
            thread_memberships=list(self.thread_memberships),
            node_type=self.node_type,
            foreshadowing_demand=self.foreshadowing_demand,
            story_contract=self,
        )

    @classmethod
    def from_geometry_node(cls, node: "GeometryNode") -> "NodeStoryContract":
        """從 GeometryNode 反向生成 NodeStoryContract"""
        if node.story_contract is not None:
            return node.story_contract
        if "_story_contract" in node.metadata:
            try:
                return cls.from_dict(node.metadata["_story_contract"])
            except Exception:
                pass

        threads = list(node.thread_memberships) if node.thread_memberships else []
        if not threads and node.primary_thread:
            threads = [node.primary_thread]
        if not threads and "thread_memberships" in node.metadata:
            threads = list(node.metadata["thread_memberships"])

        return cls(
            node_id=node.node_id,
            volume_index=node.hierarchy.volume_index if node.hierarchy else 1,
            arc_index=node.hierarchy.arc_index if node.hierarchy else 1,
            thread_memberships=threads,
            structural_role=node.structural_role,
            node_type=node.node_type if hasattr(node, "node_type") else node.metadata.get("node_type", NodeType.FACTION_COLLISION),
            foreshadowing_demand=node.foreshadowing_demand if hasattr(node, "foreshadowing_demand") else node.metadata.get("foreshadowing_demand", ForeshadowingDemand.NONE),
            worldview_slot=node.semantic,
            planning_status=node.metadata.get("planning_status", PlanningStatus.DRAFT),
            realization_status=node.metadata.get("realization_status", RealizationStatus.PENDING),
            graph_revision=int(node.metadata.get("graph_revision", 1)),
        )


@dataclass
class NodeHierarchy:
    """節點層級結構"""
    volume_index: int
    arc_index: int
    sequence_index: int


@dataclass
class GeometryNode:
    """幾何圖中的一個敘事節點 (相容擴充版本)"""
    node_id: str
    hierarchy: NodeHierarchy
    chapter_window: Tuple[int, int]
    structural_role: StructuralRole
    primary_thread: str
    importance: float = 0.5
    semantic: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    thread_memberships: List[str] = field(default_factory=list)
    node_type: Union[NodeType, str] = NodeType.FACTION_COLLISION
    foreshadowing_demand: Union[ForeshadowingDemand, str] = ForeshadowingDemand.NONE
    story_contract: Optional["NodeStoryContract"] = None

    def __post_init__(self):
        # 1. 自動反序列化 story_contract (若 metadata 存在快照)
        if self.story_contract is None and "_story_contract" in self.metadata:
            try:
                self.story_contract = NodeStoryContract.from_dict(self.metadata["_story_contract"])
            except Exception:
                pass

        # 2. 優先從契約或 metadata 還原多線歸屬 (防止被 primary_thread 覆寫截斷)
        if not self.thread_memberships:
            if self.story_contract is not None and self.story_contract.thread_memberships:
                self.thread_memberships = list(self.story_contract.thread_memberships)
            elif "_story_contract" in self.metadata and isinstance(self.metadata["_story_contract"], dict):
                raw_sc = self.metadata["_story_contract"]
                if raw_sc.get("thread_memberships"):
                    self.thread_memberships = list(raw_sc["thread_memberships"])
            elif "thread_memberships" in self.metadata and self.metadata["thread_memberships"]:
                self.thread_memberships = list(self.metadata["thread_memberships"])

        # 3. 雙向同步 primary_thread 與 thread_memberships (若依然為空才回退到 primary_thread)
        if self.primary_thread and not self.thread_memberships:
            self.thread_memberships = [self.primary_thread]
        elif self.thread_memberships and not self.primary_thread:
            self.primary_thread = self.thread_memberships[0]

        # 4. 確保契約中的多線歸屬同步一致
        if self.story_contract is not None:
            if self.thread_memberships and not self.story_contract.thread_memberships:
                self.story_contract.thread_memberships = list(self.thread_memberships)
            elif self.thread_memberships and self.story_contract.thread_memberships != self.thread_memberships:
                if len(self.thread_memberships) > len(self.story_contract.thread_memberships):
                    self.story_contract.thread_memberships = list(self.thread_memberships)
                else:
                    self.thread_memberships = list(self.story_contract.thread_memberships)
            if not self.primary_thread and self.story_contract.thread_memberships:
                self.primary_thread = self.story_contract.thread_memberships[0]

    @property
    def planning_status(self) -> PlanningStatus:
        if self.story_contract:
            return self.story_contract.planning_status
        status_val = self.metadata.get("planning_status", PlanningStatus.DRAFT.value)
        return PlanningStatus(status_val) if isinstance(status_val, str) else status_val

    @planning_status.setter
    def planning_status(self, val: Union[PlanningStatus, str]) -> None:
        status_enum = PlanningStatus(val) if isinstance(val, str) else val
        self.metadata["planning_status"] = status_enum.value
        if self.story_contract:
            self.story_contract.planning_status = status_enum
            self.metadata["_story_contract"] = self.story_contract.to_dict()

    @property
    def realization_status(self) -> RealizationStatus:
        if self.story_contract:
            return self.story_contract.realization_status
        status_val = self.metadata.get("realization_status", RealizationStatus.PENDING.value)
        return RealizationStatus(status_val) if isinstance(status_val, str) else status_val

    @realization_status.setter
    def realization_status(self, val: Union[RealizationStatus, str]) -> None:
        status_enum = RealizationStatus(val) if isinstance(val, str) else val
        self.metadata["realization_status"] = status_enum.value
        if self.story_contract:
            self.story_contract.realization_status = status_enum
            self.metadata["_story_contract"] = self.story_contract.to_dict()

    @property
    def graph_revision(self) -> int:
        if self.story_contract:
            return self.story_contract.graph_revision
        return int(self.metadata.get("graph_revision", 1))

    @graph_revision.setter
    def graph_revision(self, val: int) -> None:
        self.metadata["graph_revision"] = val
        if self.story_contract:
            self.story_contract.graph_revision = val
            self.metadata["_story_contract"] = self.story_contract.to_dict()

    @property
    def story_events(self) -> List[StoryEventContract]:
        if self.story_contract:
            return self.story_contract.story_events
        return []

    def ensure_story_contract(self) -> "NodeStoryContract":
        """確保該節點擁有 NodeStoryContract，若無則自動生成並綁定"""
        if self.story_contract is None:
            self.story_contract = NodeStoryContract.from_geometry_node(self)
        else:
            if self.thread_memberships and self.story_contract.thread_memberships != self.thread_memberships:
                self.story_contract.thread_memberships = list(self.thread_memberships)
        self.metadata["_story_contract"] = self.story_contract.to_dict()
        self.metadata["thread_memberships"] = list(self.thread_memberships)
        return self.story_contract


@dataclass
class GeometryEdge:
    """幾何圖中連接節點的邊 (相容擴充版本)"""
    edge_id: str
    source: str
    target: str
    edge_type: EdgeType
    distance: int
    semantic: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    graph_revision: int = 1

    @property
    def source_id(self) -> str:
        return self.source

    @property
    def target_id(self) -> str:
        return self.target

    @property
    def is_causal(self) -> bool:
        return self.edge_type in CAUSAL_EDGE_TYPES

    def to_contract(self) -> MasterGraphEdgeContract:
        return MasterGraphEdgeContract.from_geometry_edge(self)


@dataclass
class GeometryThread:
    """貫穿多個節點的故事線索"""
    thread_id: str
    thread_type: ThreadType
    node_sequence: List[str]
    structural_skeleton: List[StructuralRole]
    semantic: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VolumeContainer:
    """卷（Volume）容器，包含多個 Arc"""
    volume_id: str = ""
    volume_index: int = 1
    chapter_range: Tuple[int, int] = (1, 1)
    arc_ids: List[str] = field(default_factory=list)
    semantic: Optional[Dict[str, Any]] = None
    title: str = ""
    summary: str = ""

    def __post_init__(self):
        if not self.volume_id:
            self.volume_id = f"V{self.volume_index:02d}"
        if not self.title and self.semantic and isinstance(self.semantic, dict):
            self.title = str(self.semantic.get("title", ""))
        if not self.summary and self.semantic and isinstance(self.semantic, dict):
            self.summary = str(self.semantic.get("summary", ""))

    @property
    def start_chapter(self) -> int:
        return self.chapter_range[0] if self.chapter_range else 1

    @start_chapter.setter
    def start_chapter(self, val: int) -> None:
        end = self.chapter_range[1] if self.chapter_range else val
        self.chapter_range = (val, end)

    @property
    def end_chapter(self) -> int:
        return self.chapter_range[1] if self.chapter_range else 1

    @end_chapter.setter
    def end_chapter(self, val: int) -> None:
        start = self.chapter_range[0] if self.chapter_range else 1
        self.chapter_range = (start, val)


@dataclass
class ArcContainer:
    """弧（Arc）容器，包含多個序列和線索"""
    arc_id: str
    volume_index: int
    arc_index: int
    chapter_range: Tuple[int, int]
    thread_ids: List[str]
    semantic: Optional[Dict[str, Any]] = None


@dataclass
class SequenceContainer:
    """序列（Sequence）容器，包含多個節點"""
    sequence_id: str
    arc_id: str
    sequence_index: int
    chapter_range: Tuple[int, int]
    node_ids: List[str]


@dataclass
class GeometryParams:
    """幾何圖生成參數"""
    target_chapters: int = 500
    volume_count: int = 10
    chapters_per_volume: int = 50
    complexity: GeometryComplexity = GeometryComplexity.DENSE
    main_thread_count: int = 6               # 6 main threads TM01-TM06
    subplot_count: int = 18                  # 18 sub-branches TS01-TS18
    character_arc_count: int = 8
    relationship_arc_count: int = 6
    thematic_thread_count: int = 4
    cross_thread_ratio: float = 0.5
    long_distance_chain_count: int = 15
    convergence_point_count: int = 8
    contrast_pair_count: int = 6
    seed_for_rng: Optional[str] = None


@dataclass
class RepairProposal:
    """針對不合理結構的修復建議"""
    operation: RepairOperation
    target_nodes: List[str]
    reason: str
    detail: Dict[str, Any]
    approved: bool = False


class VolumeDict(dict):
    """
    卷容器專用字典：
    1. 內部以 volume_id (如 'V01', 'V02') 作為唯一鍵，保證 keys() 全為字串、len() 精確無重複。
    2. 支援整數索引訪問與包含性檢測：
       - volumes[1] 或 volumes['V01'] 皆能取得第 1 卷。
       - 1 in volumes 或 'V01' in volumes 皆為 True。
       - volumes.get(1) 或 volumes.get('V01') 皆能取得第 1 卷。
    """
    def _normalize_key(self, key: Any) -> Any:
        if isinstance(key, int):
            v_str = f"V{key:02d}"
            if super().__contains__(v_str):
                return v_str
            s_str = str(key)
            if super().__contains__(s_str):
                return s_str
        return key

    def __getitem__(self, key: Any) -> VolumeContainer:
        norm = self._normalize_key(key)
        return super().__getitem__(norm)

    def __contains__(self, key: Any) -> bool:
        if super().__contains__(key):
            return True
        norm = self._normalize_key(key)
        return super().__contains__(norm)

    def get(self, key: Any, default: Any = None) -> Any:
        norm = self._normalize_key(key)
        return super().get(norm, default)

    def __setitem__(self, key: Any, value: VolumeContainer) -> None:
        if isinstance(key, int):
            key = getattr(value, "volume_id", None) or f"V{key:02d}"
        super().__setitem__(key, value)


class GeometryGraph:
    """
    敘事幾何圖 (Single Source of Truth Core)。
    管理節點、邊、線索、卷、弧與序列的集合，並提供查詢、嚴格因果 DAG 驗證與九維契約掛接。
    """
    def __init__(self, params: GeometryParams):
        self.params: GeometryParams = params
        self.nodes: Dict[str, GeometryNode] = {}
        self.edges: List[GeometryEdge] = []
        self.threads: Dict[str, GeometryThread] = {}
        self.volumes: Dict[str, VolumeContainer] = VolumeDict()
        self.arcs: Dict[str, ArcContainer] = {}
        self.sequences: Dict[str, SequenceContainer] = {}
        self.graph_revision: int = 1
        self.story_contracts: Dict[str, NodeStoryContract] = {}

    def add_node(self, node: GeometryNode) -> None:
        """新增節點並同步故事契約"""
        self.nodes[node.node_id] = node
        if node.story_contract is not None:
            self.story_contracts[node.node_id] = node.story_contract
        elif "_story_contract" in node.metadata:
            try:
                contract = NodeStoryContract.from_dict(node.metadata["_story_contract"])
                node.story_contract = contract
                self.story_contracts[node.node_id] = contract
            except Exception:
                pass

    def add_edge(self, edge: GeometryEdge) -> None:
        """新增邊"""
        self.edges.append(edge)

    def add_thread(self, thread: GeometryThread) -> None:
        """新增線索"""
        self.threads[thread.thread_id] = thread

    def add_volume(self, vol: VolumeContainer) -> None:
        """新增卷容器"""
        self.volumes[vol.volume_id] = vol

    def add_arc(self, arc: ArcContainer) -> None:
        """新增弧容器"""
        self.arcs[arc.arc_id] = arc

    def add_sequence(self, seq: SequenceContainer) -> None:
        """新增序列容器"""
        self.sequences[seq.sequence_id] = seq

    def get_node(self, node_id: str) -> Optional[GeometryNode]:
        """根據 ID 獲取節點"""
        return self.nodes.get(node_id)

    def get_story_contract(self, node_id: str) -> Optional[NodeStoryContract]:
        """獲取節點的 NodeStoryContract"""
        if node_id in self.story_contracts:
            return self.story_contracts[node_id]
        node = self.get_node(node_id)
        if node:
            contract = node.ensure_story_contract()
            self.story_contracts[node_id] = contract
            return contract
        return None

    def set_story_contract(self, contract: NodeStoryContract) -> None:
        """設置或更新節點的故事契約"""
        self.story_contracts[contract.node_id] = contract
        node = self.get_node(contract.node_id)
        if node:
            node.story_contract = contract
            node.metadata["_story_contract"] = contract.to_dict()

    def ensure_story_contracts(self) -> None:
        """為圖中所有節點建立並掛接 NodeStoryContract"""
        for nid, node in self.nodes.items():
            if nid not in self.story_contracts:
                contract = node.ensure_story_contract()
                self.story_contracts[nid] = contract

    def get_causal_edges(self) -> List[GeometryEdge]:
        """獲取所有因果約束邊 (CAUSES, ENABLES, ESCALATES)"""
        return [e for e in self.edges if e.edge_type in CAUSAL_EDGE_TYPES]

    def get_non_causal_edges(self) -> List[GeometryEdge]:
        """獲取所有非因果邊"""
        return [e for e in self.edges if e.edge_type in NON_CAUSAL_EDGE_TYPES]

    def get_causal_predecessors(self, node_id: str) -> List[str]:
        """獲取指定節點的所有因果前置節點 ID"""
        return [e.source for e in self.edges if e.target == node_id and e.edge_type in CAUSAL_EDGE_TYPES]

    def get_causal_successors(self, node_id: str) -> List[str]:
        """獲取指定節點的所有因果後續節點 ID"""
        return [e.target for e in self.edges if e.source == node_id and e.edge_type in CAUSAL_EDGE_TYPES]

    def validate_causal_dag(self) -> List[str]:
        """
        驗證因果邊 (CAUSES, ENABLES, ESCALATES) 構成的子圖是否為嚴格有向無環圖 (DAG)。
        使用 Kahn 演算法 (拓撲排序) 檢測環狀依賴。
        非因果邊不參與此項驗證。
        回傳錯誤列表，無環時回傳空列表 []。
        """
        errors = []
        causal_edges = self.get_causal_edges()

        # 1. 驗證端點有效性
        for e in causal_edges:
            if e.source not in self.nodes:
                errors.append(f"Causal edge {e.edge_id} has invalid source: {e.source}")
            if e.target not in self.nodes:
                errors.append(f"Causal edge {e.edge_id} has invalid target: {e.target}")
        if errors:
            return errors

        # 2. 構建入度表與鄰接表
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}

        for e in causal_edges:
            if e.source == e.target:
                errors.append(f"Causal self-loop cycle detected on node: {e.source}")
                return errors
            adj[e.source].append(e.target)
            in_degree[e.target] += 1

        # 3. Kahn 演算法
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            curr = queue.popleft()
            visited_count += 1
            for nxt in adj[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        # 4. 環狀依賴判定
        if visited_count < len(self.nodes):
            cycle_nodes = [nid for nid, deg in in_degree.items() if deg > 0]
            errors.append(
                f"Causal DAG contains directed cycle(s): {len(cycle_nodes)} nodes involved in causal loop: {cycle_nodes[:8]}"
            )

        return errors

    def get_edges_for_node(self, node_id: str, direction: str = 'both') -> List[GeometryEdge]:
        """獲取與節點相關的邊。direction 可為 'incoming', 'outgoing', 或 'both'"""
        if direction == 'incoming':
            return self.get_incoming_edges(node_id)
        elif direction == 'outgoing':
            return self.get_outgoing_edges(node_id)
        else:
            return [e for e in self.edges if e.source == node_id or e.target == node_id]

    def get_incoming_edges(self, node_id: str) -> List[GeometryEdge]:
        """獲取指向該節點的邊"""
        return [e for e in self.edges if e.target == node_id]

    def get_outgoing_edges(self, node_id: str) -> List[GeometryEdge]:
        """獲取從該節點出發的邊"""
        return [e for e in self.edges if e.source == node_id]

    def get_thread_nodes(self, thread_id: str) -> List[GeometryNode]:
        """獲取指定線索下的所有節點"""
        thread = self.threads.get(thread_id)
        if not thread:
            return []
        nodes = []
        for nid in thread.node_sequence:
            n = self.get_node(nid)
            if n:
                nodes.append(n)
        return nodes

    def get_chapter_nodes(self, chapter: int) -> List[GeometryNode]:
        """獲取範圍包含指定章節的所有節點"""
        return [
            n for n in self.nodes.values()
            if n.chapter_window[0] <= chapter <= n.chapter_window[1]
        ]

    def get_nodes_in_range(self, start_ch: int, end_ch: int) -> List[GeometryNode]:
        """獲取章節範圍有交集的所有節點"""
        nodes = []
        for n in self.nodes.values():
            n_start, n_end = n.chapter_window
            if not (n_end < start_ch or n_start > end_ch):
                nodes.append(n)
        return nodes

    def get_remote_connections(self, node_id: str, max_distance: Optional[int] = None) -> List[Tuple[GeometryEdge, GeometryNode]]:
        """獲取與指定節點的遠程連接。回傳 (Edge, 目標/來源節點) 列表"""
        remote_conns = []
        for e in self.get_edges_for_node(node_id, 'both'):
            if max_distance is not None and e.distance <= max_distance:
                continue
            other_id = e.target if e.source == node_id else e.source
            other_node = self.get_node(other_id)
            if other_node:
                remote_conns.append((e, other_node))
        return remote_conns

    def get_future_obligations(self, node_id: str) -> List[GeometryEdge]:
        """獲取未來義務，即作為來源且需在未來 PAY_OFF, CONVERGES 或 ENABLES 的邊"""
        obligation_types = {EdgeType.PAYS_OFF, EdgeType.CONVERGES, EdgeType.ENABLES}
        return [e for e in self.get_outgoing_edges(node_id) if e.edge_type in obligation_types]

    def get_filling_progress(self) -> Dict[str, int]:
        """計算並回傳語義填充的進度。"""
        total_nodes = len(self.nodes)
        total_edges = len(self.edges)
        total_threads = len(self.threads)

        filled_nodes = sum(1 for n in self.nodes.values() if n.semantic is not None)
        filled_edges = sum(1 for e in self.edges if e.semantic is not None)
        filled_threads = sum(1 for t in self.threads.values() if t.semantic is not None)

        return {
            'total_nodes': total_nodes,
            'filled_nodes': filled_nodes,
            'unfilled_nodes': total_nodes - filled_nodes,
            'total_edges': total_edges,
            'filled_edges': filled_edges,
            'unfilled_edges': total_edges - filled_edges,
            'total_threads': total_threads,
            'filled_threads': filled_threads,
            'unfilled_threads': total_threads - filled_threads
        }

    def to_dict(self) -> Dict[str, Any]:
        """將圖結構序列化為字典"""
        return {
            'params': asdict(self.params),
            'nodes': {k: asdict(v) for k, v in self.nodes.items()},
            'edges': [asdict(e) for e in self.edges],
            'threads': {k: asdict(v) for k, v in self.threads.items()},
            'volumes': {k: asdict(v) for k, v in self.volumes.items()},
            'arcs': {k: asdict(v) for k, v in self.arcs.items()},
            'sequences': {k: asdict(v) for k, v in self.sequences.items()},
            'graph_revision': self.graph_revision,
            'story_contracts': {k: v.to_dict() for k, v in self.story_contracts.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeometryGraph':
        """從字典反序列化為 GeometryGraph 實例"""
        params_data = data.get('params', {})
        if 'complexity' in params_data and isinstance(params_data['complexity'], str):
            params_data['complexity'] = GeometryComplexity(params_data['complexity'])
        params = GeometryParams(**params_data)

        graph = cls(params)
        graph.graph_revision = int(data.get('graph_revision', 1))

        # 載入 story_contracts
        for k, v in data.get('story_contracts', {}).items():
            graph.story_contracts[k] = NodeStoryContract.from_dict(v)

        for k, v in data.get('nodes', {}).items():
            if 'hierarchy' in v and isinstance(v['hierarchy'], dict):
                v['hierarchy'] = NodeHierarchy(**v['hierarchy'])
            if 'chapter_window' in v and isinstance(v['chapter_window'], list):
                v['chapter_window'] = tuple(v['chapter_window'])
            if 'structural_role' in v and isinstance(v['structural_role'], str):
                v['structural_role'] = StructuralRole(v['structural_role'])
            if 'node_type' in v and isinstance(v['node_type'], str):
                try:
                    v['node_type'] = NodeType(v['node_type'])
                except ValueError:
                    pass
            if 'foreshadowing_demand' in v and isinstance(v['foreshadowing_demand'], str):
                try:
                    v['foreshadowing_demand'] = ForeshadowingDemand(v['foreshadowing_demand'])
                except ValueError:
                    pass
            if 'story_contract' in v and isinstance(v['story_contract'], dict):
                v['story_contract'] = NodeStoryContract.from_dict(v['story_contract'])
            node = GeometryNode(**v)
            graph.nodes[k] = node
            if node.story_contract:
                graph.story_contracts[k] = node.story_contract
            elif k in graph.story_contracts:
                node.story_contract = graph.story_contracts[k]

        for v in data.get('edges', []):
            if 'edge_type' in v and isinstance(v['edge_type'], str):
                v['edge_type'] = EdgeType(v['edge_type'])
            graph.edges.append(GeometryEdge(**v))

        for k, v in data.get('threads', {}).items():
            if 'thread_type' in v and isinstance(v['thread_type'], str):
                v['thread_type'] = ThreadType(v['thread_type'])
            if 'structural_skeleton' in v:
                v['structural_skeleton'] = [StructuralRole(r) if isinstance(r, str) else r for r in v['structural_skeleton']]
            graph.threads[k] = GeometryThread(**v)

        for k, v in data.get('volumes', {}).items():
            if 'chapter_range' in v and isinstance(v['chapter_range'], list):
                v['chapter_range'] = tuple(v['chapter_range'])
            vol_obj = VolumeContainer(**v)
            graph.volumes[vol_obj.volume_id or k] = vol_obj

        for k, v in data.get('arcs', {}).items():
            if 'chapter_range' in v and isinstance(v['chapter_range'], list):
                v['chapter_range'] = tuple(v['chapter_range'])
            graph.arcs[k] = ArcContainer(**v)

        for k, v in data.get('sequences', {}).items():
            if 'chapter_range' in v and isinstance(v['chapter_range'], list):
                v['chapter_range'] = tuple(v['chapter_range'])
            graph.sequences[k] = SequenceContainer(**v)

        return graph

    def validate(self) -> List[str]:
        """驗證幾何圖的完整性與合法性，包含因果邊 DAG 無環檢測，回傳錯誤訊息列表"""
        errors = []
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge {edge.edge_id} has invalid source node: {edge.source}")
            if edge.target not in self.nodes:
                errors.append(f"Edge {edge.edge_id} has invalid target node: {edge.target}")

        for thread_id, thread in self.threads.items():
            for nid in thread.node_sequence:
                if nid not in self.nodes:
                    errors.append(f"Thread {thread_id} refers to non-existent node: {nid}")

        errors.extend(self.validate_causal_dag())
        return errors
