# -*- coding: utf-8 -*-
"""
Graphiti Temporal Knowledge Graph Service.
Provides temporal graph querying, NetworkX subgraph traversal, and temporal context assembly.
"""
from typing import Dict, Any, List, Optional, Set
import networkx as nx
from backend import persistence as db

class TemporalGraphService:
    """Manages temporal queries and graph traversal over narrative entities and facts."""

    @staticmethod
    def get_chapter_graph(novel_id: str, at_chapter: int) -> nx.MultiDiGraph:
        """Constructs a NetworkX MultiDiGraph representing the world state at a specific chapter."""
        G = nx.MultiDiGraph()
        entities = db.get_entities(novel_id)
        for ent in entities:
            G.add_node(
                ent["id"],
                name=ent["name"],
                entity_type=ent["entity_type"],
                summary=ent["summary"],
                attributes=ent.get("attributes", {})
            )
        
        facts = db.get_facts_at_chapter(novel_id, at_chapter)
        for fact in facts:
            u = fact.get("source_entity_id") or "global"
            v = fact.get("target_entity_id") or "global"
            G.add_edge(
                u, v,
                key=fact["id"],
                statement=fact["fact_statement"],
                relation=fact.get("relation_type", "relates_to"),
                valid_from=fact["valid_from_chapter"]
            )
        return G

    @staticmethod
    def get_active_facts_for_entities(
        novel_id: str,
        at_chapter: int,
        entity_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves facts active at at_chapter, optionally filtered by relevant entity names."""
        facts = db.get_facts_at_chapter(novel_id, at_chapter)
        if not entity_names:
            return facts
        
        clean_names = {n.strip().lower() for n in entity_names if n and n.strip()}
        if not clean_names:
            return facts

        filtered = []
        for fact in facts:
            src = (fact.get("source_name") or "").strip().lower()
            tgt = (fact.get("target_name") or "").strip().lower()
            stmt = (fact.get("fact_statement") or "").lower()
            # If source, target, or statement mentions the entity
            if src in clean_names or tgt in clean_names or any(name in stmt for name in clean_names):
                filtered.append(fact)
        return filtered

    @staticmethod
    def build_narrative_context(
        novel_id: str,
        at_chapter: int,
        active_characters: Optional[List[str]] = None,
        max_facts: int = 15
    ) -> str:
        """
        Formats a dynamic, high-density temporal context string for the Chapter Writer & Editor.
        Includes active world facts, character statuses at this timeline, and recent invalidations.
        """
        active_facts = TemporalGraphService.get_active_facts_for_entities(
            novel_id, at_chapter, active_characters
        )
        
        if not active_facts:
            active_facts = db.get_facts_at_chapter(novel_id, at_chapter)[:max_facts]
        else:
            active_facts = active_facts[:max_facts]

        all_facts = db.get_all_facts(novel_id)
        recently_invalidated = [
            f for f in all_facts
            if f.get("invalid_from_chapter") is not None
            and 0 < (at_chapter - f["invalid_from_chapter"]) <= 5
        ]

        return TemporalGraphService.format_temporal_facts_prompt(
            active_facts=active_facts,
            invalidated_facts=recently_invalidated[:5],
            chapter_index=at_chapter
        )

    @staticmethod
    def format_temporal_facts_prompt(
        facts: Optional[List[Dict[str, Any]]] = None,
        active_facts: Optional[List[Dict[str, Any]]] = None,
        invalidated_facts: Optional[List[Dict[str, Any]]] = None,
        chapter_index: int = 1,
    ) -> str:
        """
        Formats a dynamic, high-density temporal facts prompt with rigid worldline constraints.
        """
        effective_active = active_facts if active_facts is not None else (facts or [])
        lines = [
            f"【Graphiti 時序動態記憶 (第 {chapter_index} 章世界線狀態 - 剛性約束鐵律)】",
            "本章情節必須嚴格錨定以下世界線事實，禁止違背已發生之歷史與客觀狀態：",
        ]
        if effective_active:
            lines.append("▶ 當前生效之關鍵事實與關係 (Temporal Facts)：")
            for f in effective_active:
                src = f.get("source_name")
                tgt = f.get("target_name")
                rel = f.get("relation_type")
                stmt = f.get("fact_statement") or f.get("stmt") or ""
                from_ch = f.get("valid_from_chapter") or f.get("from_ch") or 1
                if src and tgt and rel:
                    lines.append(f"  - [第 {from_ch} 章起生效] {src} --({rel})--> {tgt}：{stmt}")
                else:
                    lines.append(f"  - [第 {from_ch} 章起生效] {stmt}")
        else:
            lines.append("  (暫無特定時序事實記錄，依照總體世界觀與大綱推進)")

        if invalidated_facts:
            lines.append("▶ 近期已作廢/改變之舊事實 (Invalidated / Superseded - 避免穿幫)：")
            for f in invalidated_facts:
                stmt = f.get("fact_statement") or f.get("stmt") or ""
                inv_ch = f.get("invalid_from_chapter") or f.get("inv_ch") or "?"
                lines.append(f"  - [於第 {inv_ch} 章已失效/被顛覆] {stmt}")

        return "\n".join(lines)
