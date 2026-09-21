# -*- coding: utf-8 -*-
"""
總監上下文編譯器 (Director Context Compiler)

核心職責：
實現 vNext 架構中的「導演即編譯器 (Director as Compiler)」原則。
沿著 Geometry Graph 的拓撲邊，自動抓取跨距節點語義、未來義務與交織線程，
編譯出標準的 6 層結構化上下文包裹 (Context Package)：

  LLM_CONTEXT = BASE_CONTEXT
              + LOCAL_CONTEXT
              + GEOMETRY_OVERLAY         (Layer 3)
              + CROSS_RELATION_CONTEXT   (Layer 4)
              + TEMPORAL_REALITY         (Layer 5 - Graphiti)
              + OUTPUT_CONTRACT          (Layer 6)

核心防護原則：
- 過去節點：沿邊抓取已發生的具體語義摘要
- 未來節點：嚴格防劇透，僅傳達「結構義務」（如：此處埋設的種子將在後續產生連鎖反應），禁止提前洩露未來未寫劇情
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend import persistence as db
from backend.geometry.models import EdgeType, GeometryGraph, GeometryNode, StructuralRole


# 結構角色的文學職責指引
ROLE_OBLIGATION_MAP: Dict[str, str] = {
    "OPEN_THREAD": "【起線/拋出懸念】：正式引入新線程、秘密或矛盾焦點，埋下懸念鉤子，引發讀者好奇。",
    "DEVELOP": "【推進進展】：依既有設定穩步推進矛盾，加深衝突，角色在此遭遇新阻礙。",
    "ESCALATE": "【危機升級】：衝突顯著加劇，危險迫近，籌碼提高，形勢逼迫角色必須採取更冒險的行動。",
    "BRANCH": "【情節分岔】：局勢分化為多條支線或角色分頭行動，各自面對不同的局部考驗。",
    "REVISIT": "【重溫舊線】：重訪先前暫歇的線索或角色，必須承接先前已確定的情報與進展，不得視為新發現。",
    "ECHO": "【長距呼應】：以變奏、象徵或情境重現的形式，遙相呼應前文事件，展現命運交疊感。",
    "CONVERGE": "【多線匯聚/合流】：多條線程在此產生劇烈交會與碰撞，不同勢力/角色的利益直接正面衝突。",
    "CHARACTER_SHIFT": "【心境轉向/信念打破】：角色在此經歷價值觀重構、重大代價抉擇或破除假信念 (False Belief)。",
    "RELATIONSHIP_CHANGE": "【關係質變】：人際羈絆發生本質變化（結盟、反目、背叛、信任崩塌或情感確立）。",
    "PAYOFF": "【伏筆回收/高潮兌現】：強烈釋放前文累積的懸念能量，全面兌現承諾，禁止在此處繼續拖泥帶水。",
    "TRANSITION": "【過場/沉澱】：在高潮或大戰後提供情緒釋放與空間位移，整備下一波衝突。",
    "CLOSE": "【收束/收尾】：完滿收束當前弧線或副線，確認得失，平息餘波。",
}


@dataclass
class ContextPackage:
    """編譯完成的 6 層上下文包裹"""
    novel_id: str
    chapter_index: int
    target_node_id: Optional[str]
    has_geometry: bool
    structural_role: str = ""
    role_obligation: str = ""
    incoming_edges_summary: List[str] = field(default_factory=list)
    outgoing_obligations: List[str] = field(default_factory=list)
    cross_context_threads: List[str] = field(default_factory=list)
    echo_contrast_context: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def format_geometry_overlay(self) -> str:
        """格式化 Layer 3: Geometry Overlay 為純淨提示詞區塊"""
        if not self.has_geometry:
            return ""

        lines = [
            f"### 🏗️【幾何結構角色與敘事義務 (Geometry Overlay - 節點 {self.target_node_id or '當前章'})】",
            f"- **結構角色定位 (Structural Role)**：`{self.structural_role}`",
            f"- **敘事核心職責**：{self.role_obligation}",
        ]

        if self.incoming_edges_summary:
            lines.append("- **前置因果承接 (Incoming Links)**：")
            for item in self.incoming_edges_summary[:4]:
                lines.append(f"  * {item}")

        if self.outgoing_obligations:
            lines.append("- **後續結構義務 (Future Obligations - 必須為後文鋪墊，不得草率解決)**：")
            for item in self.outgoing_obligations[:4]:
                lines.append(f"  * {item}")

        return "\n".join(lines)

    def format_cross_context(self) -> str:
        """格式化 Layer 4: Cross-Relation Context 為純淨提示詞區塊"""
        if not self.has_geometry:
            return ""

        lines = []
        if self.cross_context_threads or self.echo_contrast_context:
            lines.append(f"### 🔗【跨距線程交織與對照關聯 (Cross Context)】")

            if self.cross_context_threads:
                lines.append("▶ **貫穿本章之活躍線程 (Active Threads)**：")
                for item in self.cross_context_threads[:5]:
                    lines.append(f"  - {item}")

            if self.echo_contrast_context:
                lines.append("▶ **遠程伏筆呼應與主題對比 (Echo & Contrast Links)**：")
                for item in self.echo_contrast_context[:4]:
                    lines.append(f"  - {item}")

        return "\n".join(lines)


class GeometryContextCompiler:
    """
    幾何上下文編譯器。
    按圖索驥，沿著幾何邊編譯出專屬於當前寫作任務的最小必要跨距上下文。
    """

    @classmethod
    def compile(
        cls,
        novel_id: str,
        chapter_index: int,
        target_node_id: Optional[str] = None,
    ) -> ContextPackage:
        """
        編譯入口。若無幾何圖，回傳空的 package。
        """
        graph = db.load_geometry_graph(novel_id)
        if not graph or not graph.nodes:
            return ContextPackage(
                novel_id=novel_id,
                chapter_index=chapter_index,
                target_node_id=target_node_id,
                has_geometry=False,
            )

        # 1. 鎖定目標節點
        node: Optional[GeometryNode] = None
        if target_node_id and target_node_id in graph.nodes:
            node = graph.nodes[target_node_id]
        else:
            # 從當前章節找第一個節點
            ch_nodes = graph.get_chapter_nodes(chapter_index)
            if ch_nodes:
                node = ch_nodes[0]
            else:
                # 找最靠近的節點
                all_nodes = sorted(graph.nodes.values(), key=lambda n: n.chapter_window[0])
                for n in all_nodes:
                    if n.chapter_window[0] >= chapter_index:
                        node = n
                        break
                if not node and all_nodes:
                    node = all_nodes[-1]

        if not node:
            return ContextPackage(
                novel_id=novel_id,
                chapter_index=chapter_index,
                target_node_id=None,
                has_geometry=False,
            )

        role_str = node.structural_role.value if hasattr(node.structural_role, "value") else str(node.structural_role)
        obligation = ROLE_OBLIGATION_MAP.get(role_str, "維持情節因果推進。")

        # 2. Layer 3: 編譯 Incoming 因果 與 Outgoing 未來義務
        incoming_summary: List[str] = []
        outgoing_obligations: List[str] = []

        in_edges = graph.get_incoming_edges(node.node_id)
        for e in in_edges:
            src_node = graph.get_node(e.source)
            if not src_node:
                continue
            e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
            src_ch = src_node.chapter_window[0]

            # 過去節點：允許包含其語義摘要
            src_sem = src_node.semantic or {}
            desc = src_sem.get("scene_title") or src_sem.get("core_action") or f"第 {src_ch} 章節點"
            if e.semantic and isinstance(e.semantic, dict):
                causal = e.semantic.get("causal_link", "")
                if causal:
                    desc += f"（因果：{causal}）"

            incoming_summary.append(f"[{e_type}] 承接第 {src_ch} 章：{desc}")

        out_edges = graph.get_outgoing_edges(node.node_id)
        for e in out_edges:
            tgt_node = graph.get_node(e.target)
            if not tgt_node:
                continue
            e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
            tgt_ch = tgt_node.chapter_window[0]

            # 未來節點：嚴禁洩露劇情，僅傳遞結構義務
            if e_type == "SETS_UP":
                outgoing_obligations.append(f"【伏筆種植】：本章埋下的線索/信物/情報，將在第 {tgt_ch} 章產生深遠回收。")
            elif e_type == "CONVERGES":
                outgoing_obligations.append(f"【匯聚預備】：本章線索將在第 {tgt_ch} 章與其他重要勢力/角色大線迎頭交會。")
            elif e_type == "ENABLES":
                outgoing_obligations.append(f"【前提解鎖】：本章行動為第 {tgt_ch} 章的後續重大轉折奠定必要前提。")
            elif e_type == "CONTRASTS":
                outgoing_obligations.append(f"【主題對照】：本章主角所做的抉擇，將在第 {tgt_ch} 章迎來境遇的諷刺性對比。")
            elif e_type == "CAUSES":
                outgoing_obligations.append(f"【直接因果】：本章引發的波瀾直接驅動第 {tgt_ch} 章的危機。")

        # 3. Layer 4: 編譯 Cross-Relation Context
        cross_threads: List[str] = []
        echo_contrasts: List[str] = []

        # 活躍線程收集
        active_thread_ids: Set[str] = set()
        if node.primary_thread:
            active_thread_ids.add(node.primary_thread)

        for edge in in_edges + out_edges:
            if edge.metadata and "thread_id" in edge.metadata:
                active_thread_ids.add(edge.metadata["thread_id"])

        for t_id in active_thread_ids:
            t_obj = graph.threads.get(t_id)
            if t_obj:
                t_type = t_obj.thread_type.value if hasattr(t_obj.thread_type, "value") else str(t_obj.thread_type)
                t_sem = t_obj.semantic or {}
                t_name = t_sem.get("thread_name") or t_id
                t_desc = t_sem.get("description") or "長線推進行動"
                cross_threads.append(f"[{t_type}] 【{t_name}】：{t_desc}")

        # 跨距 Echo / Contrast 關聯
        for e in in_edges:
            e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
            if e_type in ("ECHOES", "CONTRASTS", "PAYS_OFF"):
                src_node = graph.get_node(e.source)
                if src_node:
                    src_ch = src_node.chapter_window[0]
                    e_sem = e.semantic or {}
                    clash = e_sem.get("dramatic_clash") or e_sem.get("causal_link") or "呼應前文"
                    echo_contrasts.append(f"與第 {src_ch} 章形成 [{e_type}]：{clash}")

        return ContextPackage(
            novel_id=novel_id,
            chapter_index=chapter_index,
            target_node_id=node.node_id,
            has_geometry=True,
            structural_role=role_str,
            role_obligation=obligation,
            incoming_edges_summary=incoming_summary,
            outgoing_obligations=outgoing_obligations,
            cross_context_threads=cross_threads,
            echo_contrast_context=echo_contrasts,
        )
