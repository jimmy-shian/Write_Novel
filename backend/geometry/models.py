"""
幾何圖核心資料模型。
定義了節點（Node）、邊（Edge）、線索（Thread）以及容器（Volume, Arc, Sequence），
並提供了主結構 GeometryGraph 管理這些元素的關聯。
"""

import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any

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

@dataclass
class NodeHierarchy:
    """節點層級結構"""
    volume_index: int
    arc_index: int
    sequence_index: int

@dataclass
class GeometryNode:
    """幾何圖中的一個敘事節點"""
    node_id: str
    hierarchy: NodeHierarchy
    chapter_window: Tuple[int, int]
    structural_role: StructuralRole
    primary_thread: str
    importance: float = 0.5
    semantic: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GeometryEdge:
    """幾何圖中連接節點的邊"""
    edge_id: str
    source: str
    target: str
    edge_type: EdgeType
    distance: int
    semantic: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

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
    volume_id: str
    volume_index: int
    chapter_range: Tuple[int, int]
    arc_ids: List[str]
    semantic: Optional[Dict[str, Any]] = None

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
    target_chapters: int
    volume_count: int
    chapters_per_volume: int = 50
    complexity: GeometryComplexity = GeometryComplexity.DENSE
    main_thread_count: int = 4
    subplot_count: int = 12
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

class GeometryGraph:
    """
    敘事幾何圖。
    管理節點、邊、線索、卷、弧與序列的集合，並提供查詢與驗證方法。
    """
    def __init__(self, params: GeometryParams):
        self.params: GeometryParams = params
        self.nodes: Dict[str, GeometryNode] = {}
        self.edges: List[GeometryEdge] = []
        self.threads: Dict[str, GeometryThread] = {}
        self.volumes: Dict[str, VolumeContainer] = {}
        self.arcs: Dict[str, ArcContainer] = {}
        self.sequences: Dict[str, SequenceContainer] = {}

    def add_node(self, node: GeometryNode) -> None:
        """新增節點"""
        self.nodes[node.node_id] = node

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
        from dataclasses import asdict
        
        return {
            'params': asdict(self.params),
            'nodes': {k: asdict(v) for k, v in self.nodes.items()},
            'edges': [asdict(e) for e in self.edges],
            'threads': {k: asdict(v) for k, v in self.threads.items()},
            'volumes': {k: asdict(v) for k, v in self.volumes.items()},
            'arcs': {k: asdict(v) for k, v in self.arcs.items()},
            'sequences': {k: asdict(v) for k, v in self.sequences.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeometryGraph':
        """從字典反序列化為 GeometryGraph 實例"""
        params_data = data.get('params', {})
        if 'complexity' in params_data and isinstance(params_data['complexity'], str):
            params_data['complexity'] = GeometryComplexity(params_data['complexity'])
        params = GeometryParams(**params_data)
        
        graph = cls(params)
        
        for k, v in data.get('nodes', {}).items():
            if 'hierarchy' in v and isinstance(v['hierarchy'], dict):
                v['hierarchy'] = NodeHierarchy(**v['hierarchy'])
            if 'chapter_window' in v and isinstance(v['chapter_window'], list):
                v['chapter_window'] = tuple(v['chapter_window'])
            if 'structural_role' in v and isinstance(v['structural_role'], str):
                v['structural_role'] = StructuralRole(v['structural_role'])
            graph.nodes[k] = GeometryNode(**v)
            
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
            graph.volumes[k] = VolumeContainer(**v)
            
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
        """驗證幾何圖的完整性與合法性，回傳錯誤訊息列表"""
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
                    
        return errors
