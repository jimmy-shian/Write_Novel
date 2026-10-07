# -*- coding: utf-8 -*-
"""
Entity & Foreshadowing Topology Binder.
Enforces structural ID linkages across factions, characters, narrative acts, and foreshadowing debts.
Prevents natural-language hallucination by establishing deterministic relational references.
"""

from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.generation.core.contracts import ForeshadowingBinding


def bind_entities_and_foreshadowings(novel_id: str) -> List[ForeshadowingBinding]:
    """
    Reads existing worldview and characters, assigning authoritative IDs,
    factions, and act/volume coordinates to each foreshadowing seed.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    char_record = db.get_latest_characters(novel_id)

    wb_json = db.parse_worldview_to_json(wb["content"]) if wb and wb.get("content") else {}
    seeds = wb_json.get("foreshadowing_seeds", [])

    char_list = []
    if char_record and char_record.get("json_data"):
        try:
            parsed = json.loads(char_record["json_data"]) if isinstance(char_record["json_data"], str) else char_record["json_data"]
            char_list = parsed.get("characters", []) if isinstance(parsed, dict) else parsed
        except Exception:
            char_list = []

    char_ids = [c.get("id") or f"CHAR-{i:03d}" for i, c in enumerate(char_list, start=1)]

    # Fetch geometry nodes for attachment
    graph_loader = getattr(db, "load_geometry_graph", None)
    graph = graph_loader(novel_id) if callable(graph_loader) else None
    available_node_ids = list(graph.nodes.keys()) if graph and graph.nodes else []
    if not available_node_ids:
        planning = db.get_planning_blueprint(novel_id) if hasattr(db, "get_planning_blueprint") else None
        planning_nodes = planning.get("nodes", {}) if isinstance(planning, dict) else {}
        available_node_ids = list(planning_nodes.keys()) if isinstance(planning_nodes, dict) else []

    bound_foreshadowings: List[ForeshadowingBinding] = []

    for idx, s in enumerate(seeds, start=1):
        fs_id = f"FS-{idx:03d}"
        if isinstance(s, dict):
            title = s.get("title") or s.get("name") or s.get("seed") or f"伏筆種子 #{idx}"
            category = s.get("category") or s.get("type") or "mystery"
            surface = s.get("surface_clue") or s.get("clue") or str(s.get("description", ""))
            truth = s.get("core_truth") or s.get("truth") or str(s.get("resolution", ""))
        else:
            title = str(s)[:30]
            category = "mystery"
            surface = str(s)
            truth = f"關於「{title}」的底層真相"

        # Assign carrier characters
        explicit_carriers = s.get("carrier_character_ids") if isinstance(s, dict) else None
        carrier = [str(x) for x in explicit_carriers if str(x).strip()] if isinstance(explicit_carriers, list) else []
        if not carrier:
            carrier_idx = (idx - 1) % max(1, len(char_ids))
            carrier = [char_ids[carrier_idx]] if char_ids else ["CHAR-001"]

        # Assign plant and payoff acts
        plant_act = f"ACT-{(idx % 3) + 1:02d}"
        payoff_act = f"ACT-{max(4, (idx % 6) + 4):02d}"

        # Attached node
        attached_node = available_node_ids[(idx - 1) % len(available_node_ids)] if available_node_ids else None

        explicit_faction = s.get("faction_id") if isinstance(s, dict) else None
        binding = ForeshadowingBinding(
            foreshadowing_id=fs_id,
            title=title,
            category=category,
            carrier_character_ids=carrier,
            faction_id=str(explicit_faction or _faction_for_characters(carrier, char_list)) if (explicit_faction or _faction_for_characters(carrier, char_list)) else None,
            planned_plant_act_id=plant_act,
            planned_payoff_act_id=payoff_act,
            planned_plant_volume=(idx % 2) + 1,
            planned_payoff_volume=max(3, (idx % 4) + 3),
            surface_clue=surface,
            core_truth=truth,
            attached_node_id=attached_node,
            status="planted",
        )
        bound_foreshadowings.append(binding)

    db.save_entity_bindings(novel_id, bound_foreshadowings)
    return bound_foreshadowings


def _faction_for_characters(carrier_ids: List[str], characters: List[Dict[str, Any]]) -> Optional[str]:
    for character in characters:
        if not isinstance(character, dict):
            continue
        if str(character.get("id") or "") in carrier_ids:
            faction = character.get("faction_id") or character.get("faction")
            if isinstance(faction, dict):
                faction = faction.get("id") or faction.get("name")
            if faction:
                return str(faction)
    return None
