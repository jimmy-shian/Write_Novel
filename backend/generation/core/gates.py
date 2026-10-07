# -*- coding: utf-8 -*-
"""
Four-Tier Rigid Gate Framework.
Provides deterministic, DB-factual validation across all generation stages:
Tier 1: Structural (Schema & syntax validity)
Tier 2: Quantitative (Threshold & count compliance)
Tier 3: Referential (Entity & topological connectivity)
Tier 4: Substantive (Database persistence & non-placeholder reality)
"""

from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.common.config import (
    MIN_CHARACTER_COUNT,
    MIN_FORESHADOWING_SEEDS,
    MIN_KEY_TURNING_POINTS,
    MIN_VOLUME_COUNT,
)
from backend.common.refusal_filter import is_refusal_or_disclaimer
from backend.generation.core.contracts import GateResult
from backend.generation.core.flow_spec import normalize_stage_name, compute_dynamic_acts


def evaluate_stage_rigid_gate(stage: str, novel_id: str, context: Optional[Dict[str, Any]] = None) -> GateResult:
    """
    Evaluates the factual completion of a stage against the physical database.
    Ignores LLM verbal claims; only physical DB data counts.
    """
    norm = normalize_stage_name(stage)
    context = context or {}

    if norm == "worldview":
        return _evaluate_worldview(novel_id)
    elif norm == "narrative_scale":
        return _evaluate_narrative_scale(novel_id)
    elif norm == "planning_blueprint":
        return _evaluate_planning_blueprint(novel_id)
    elif norm == "geometry":
        return _evaluate_geometry(novel_id)
    elif norm == "characters":
        return _evaluate_characters(novel_id)
    elif norm == "foreshadowing":
        return _evaluate_foreshadowing(novel_id)
    elif norm == "volumes":
        return _evaluate_volumes(novel_id, context)
    elif norm == "macro_semantic":
        return _evaluate_macro_semantic(novel_id)
    elif norm == "character_semantic":
        return _evaluate_character_semantic(novel_id)
    elif norm == "cross_relation":
        return _evaluate_cross_relation(novel_id)
    elif norm == "volume_skeleton":
        vol_idx = context.get("volume_index")
        return _evaluate_volume_skeleton(novel_id, vol_idx)
    elif norm == "writer":
        ch_idx = context.get("chapter_index")
        return _evaluate_writer(novel_id, ch_idx)
    elif norm == "editor":
        ch_idx = context.get("chapter_index")
        return _evaluate_editor(novel_id, ch_idx)
    else:
        # Default fallback
        return GateResult(
            stage=stage,
            passed=True,
            structural_ok=True,
            quantitative_ok=True,
            referential_ok=True,
            substantive_ok=True,
        )


def _evaluate_worldview(novel_id: str) -> GateResult:
    wb = db.get_latest_worldbuilding(novel_id)
    defects = []
    structural_ok = False
    quantitative_ok = False
    referential_ok = False
    substantive_ok = False

    if not wb or not wb.get("content"):
        defects.append("世界觀尚未持久化存入資料庫")
        return GateResult("worldview", False, False, False, False, False, defects, "請執行世界觀生成任務")

    content = wb["content"].strip()
    if len(content) > 100:
        substantive_ok = True
    else:
        defects.append(f"世界觀內容過短（{len(content)} 字）")

    # Try parse JSON
    parsed = None
    try:
        parsed = db.parse_worldview_to_json(content)
        structural_ok = isinstance(parsed, dict)
    except Exception:
        # If markdown prose, structural ok if sections exist
        structural_ok = ("#" in content or "【" in content)

    # Quantitative: check key components
    if parsed and isinstance(parsed, dict):
        has_theme = bool(parsed.get("theme") or parsed.get("core_theme") or parsed.get("theme_tone"))
        has_rules = bool(parsed.get("rules") or parsed.get("world_rules") or parsed.get("power_system"))
        has_factions = bool(parsed.get("factions") or parsed.get("forces"))
        quantitative_ok = bool(has_theme or has_rules or len(content) > 300)
        referential_ok = bool(has_factions or "陣營" in content or "勢力" in content)
    else:
        quantitative_ok = len(content) >= 300
        referential_ok = ("力量" in content or "體系" in content or "勢力" in content)

    passed = structural_ok and quantitative_ok and substantive_ok
    return GateResult(
        stage="worldview",
        passed=passed,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=defects,
        remediation_hint="需補齊核心主題、法則與勢力骨架" if not passed else "",
        metrics={"char_length": len(content)},
    )


def _evaluate_narrative_scale(novel_id: str) -> GateResult:
    # Scale can be inferred from novel settings or volumes
    novel = db.get_novel(novel_id) or {}
    volumes = db.get_volumes(novel_id) or []
    vol_count = len(volumes) if volumes else int(novel.get("target_volumes") or 8)
    expected_acts = compute_dynamic_acts(vol_count)

    # Narrative scale spec in DB
    wb = db.get_latest_worldbuilding(novel_id)
    wb_json = db.parse_worldview_to_json(wb["content"]) if wb and wb.get("content") else {}
    acts = wb_json.get("acts") or wb_json.get("multi_act_structure") or []

    structural_ok = isinstance(acts, list)
    quantitative_ok = (len(acts) >= min(4, expected_acts)) or (vol_count > 0)
    referential_ok = True
    substantive_ok = True

    return GateResult(
        stage="narrative_scale",
        passed=structural_ok and quantitative_ok and substantive_ok,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=[] if quantitative_ok else [f"幕次不足：預期 {expected_acts} 幕，實際 {len(acts)} 幕"],
        metrics={"expected_acts": expected_acts, "actual_acts": len(acts)},
    )


def _evaluate_geometry(novel_id: str) -> GateResult:
    stats = db.get_geometry_stats(novel_id) if hasattr(db, "get_geometry_stats") else {}
    node_count = int(stats.get("node_count") or 0)
    edge_count = int(stats.get("edge_count") or 0)
    thread_count = int(stats.get("thread_count") or 0)

    structural_ok = True
    quantitative_ok = (node_count > 0 and thread_count > 0)
    referential_ok = (edge_count > 0 or node_count <= 2)
    substantive_ok = (node_count > 0)

    defects = []
    if node_count == 0:
        defects.append("資料庫幾何拓樸節點數為 0，尚未持久化")
    if thread_count == 0:
        defects.append("資料庫敘事線程數為 0")

    passed = structural_ok and quantitative_ok and substantive_ok
    return GateResult(
        stage="geometry",
        passed=passed,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=defects,
        remediation_hint="必須執行 Geometry 生成並持久化至 SQLite" if not passed else "",
        metrics=stats,
    )


def _evaluate_planning_blueprint(novel_id: str) -> GateResult:
    blueprint = db.get_planning_blueprint(novel_id) if hasattr(db, "get_planning_blueprint") else None
    nodes = blueprint.get("nodes", {}) if isinstance(blueprint, dict) else {}
    edges = blueprint.get("edges", []) if isinstance(blueprint, dict) else []
    threads = blueprint.get("threads", {}) if isinstance(blueprint, dict) else {}
    structural_ok = isinstance(blueprint, dict) and isinstance(nodes, dict) and isinstance(edges, list) and isinstance(threads, dict)
    quantitative_ok = bool(nodes) and bool(edges) and bool(threads)
    substantive_ok = quantitative_ok and all(isinstance(n, dict) and str(n.get("title") or "").strip() for n in nodes.values())
    defects = []
    if not blueprint:
        defects.append("規劃拓樸藍圖尚未持久化")
    if not quantitative_ok:
        defects.append("規劃拓樸缺少節點、因果邊或敘事線")
    return GateResult("planning_blueprint", structural_ok and quantitative_ok and substantive_ok,
                      structural_ok, quantitative_ok, True, substantive_ok, defects,
                      "先建立世界觀規模與規劃拓樸藍圖" if defects else "",
                      {"node_count": len(nodes), "edge_count": len(edges), "thread_count": len(threads)})


def _evaluate_characters(novel_id: str) -> GateResult:
    char = db.get_latest_characters(novel_id)
    if not char or not char.get("json_data") or char["json_data"] == "{'characters': []}":
        return GateResult("characters", False, False, False, False, False, ["角色聖經為空，尚未寫入資料庫"], "請生成角色聖經")

    char_list = []
    structural_ok = False
    try:
        parsed = json.loads(char["json_data"]) if isinstance(char["json_data"], str) else char["json_data"]
        if isinstance(parsed, dict):
            char_list = parsed.get("characters", [])
        elif isinstance(parsed, list):
            char_list = parsed
        structural_ok = isinstance(char_list, list)
    except Exception:
        structural_ok = False

    c_count = len(char_list)
    min_count = MIN_CHARACTER_COUNT
    quantitative_ok = c_count >= min_count
    substantive_ok = c_count > 0 and any(len(c.get("name", "")) > 0 for c in char_list)

    # Referential: check whether characters have factions or role definitions
    has_factions_or_roles = any(c.get("faction") or c.get("faction_id") or c.get("role") for c in char_list)
    referential_ok = has_factions_or_roles

    defects = []
    if c_count < min_count:
        defects.append(f"角色數量不足：當前 {c_count} 位，至少需 {min_count} 位")
    if not referential_ok:
        defects.append("角色缺乏陣營或角色身份關聯")

    passed = structural_ok and quantitative_ok and referential_ok and substantive_ok
    return GateResult(
        stage="characters",
        passed=passed,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=defects,
        remediation_hint="需擴充角色至合規數量並明確陣營歸屬" if not passed else "",
        metrics={"character_count": c_count},
    )


def _evaluate_foreshadowing(novel_id: str) -> GateResult:
    wb = db.get_latest_worldbuilding(novel_id)
    if not wb or not wb.get("content"):
        return GateResult("foreshadowing", False, False, False, False, False, ["缺少世界觀數據以提取伏筆"], "請先完成世界觀")

    try:
        parsed_wb = db.parse_worldview_to_json(wb["content"])
        seeds = parsed_wb.get("foreshadowing_seeds", [])
        turns = parsed_wb.get("key_turning_points", [])
    except Exception:
        seeds, turns = [], []

    s_count = len(seeds)
    t_count = len(turns)
    structural_ok = isinstance(seeds, list) and isinstance(turns, list)
    quantitative_ok = (s_count >= MIN_FORESHADOWING_SEEDS and t_count >= MIN_KEY_TURNING_POINTS)
    substantive_ok = s_count > 0 and t_count > 0
    referential_ok = True

    defects = []
    if s_count < MIN_FORESHADOWING_SEEDS:
        defects.append(f"伏筆種子不足：當前 {s_count} 條，至少需 {MIN_FORESHADOWING_SEEDS} 條")
    if t_count < MIN_KEY_TURNING_POINTS:
        defects.append(f"關鍵轉折點不足：當前 {t_count} 條，至少需 {MIN_KEY_TURNING_POINTS} 條")

    passed = structural_ok and quantitative_ok and substantive_ok
    return GateResult(
        stage="foreshadowing",
        passed=passed,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=defects,
        remediation_hint="請執行伏筆與轉折生成任務補齊缺額" if not passed else "",
        metrics={"seeds_count": s_count, "turns_count": t_count},
    )


def _evaluate_volumes(novel_id: str, context: Dict[str, Any]) -> GateResult:
    vols = db.get_volumes(novel_id)
    if not vols:
        return GateResult("volumes", False, False, False, False, False, ["分卷大綱為空，尚未寫入資料庫"], "請生成分卷大綱")

    v_count = len(vols)
    target_vol_count = context.get("target_volume_count") or MIN_VOLUME_COUNT
    structural_ok = all("volume_index" in v and "title" in v for v in vols)
    quantitative_ok = v_count >= target_vol_count
    substantive_ok = v_count > 0 and all(len(str(v.get("title", ""))) > 0 for v in vols)

    # Referential: sequential volume indices
    indices = sorted([int(v.get("volume_index", 0)) for v in vols])
    expected_indices = list(range(1, v_count + 1))
    referential_ok = (indices == expected_indices)

    defects = []
    if v_count < target_vol_count:
        defects.append(f"分卷數量不足：當前 {v_count} 卷，目標需達 {target_vol_count} 卷")
    if not referential_ok:
        defects.append(f"卷序號不連續：實際 {indices} vs 預期 {expected_indices}")

    passed = structural_ok and quantitative_ok and referential_ok and substantive_ok
    return GateResult(
        stage="volumes",
        passed=passed,
        structural_ok=structural_ok,
        quantitative_ok=quantitative_ok,
        referential_ok=referential_ok,
        substantive_ok=substantive_ok,
        defects=defects,
        remediation_hint="需補齊分卷至目標數量並確保序號連續" if not passed else "",
        metrics={"volume_count": v_count, "target_volume_count": target_vol_count},
    )


def _evaluate_macro_semantic(novel_id: str) -> GateResult:
    stats = db.get_geometry_stats(novel_id) if hasattr(db, "get_geometry_stats") else {}
    filled_threads = int(stats.get("filled_threads") or 0)
    filled_volumes = int(stats.get("filled_volumes") or 0)

    graph_loader = getattr(db, "load_geometry_graph", None)
    graph = graph_loader(novel_id) if callable(graph_loader) else None
    has_macro = filled_threads > 0 or filled_volumes > 0 or bool(graph and any(v.semantic for v in graph.volumes.values()))

    passed = has_macro
    return GateResult(
        stage="macro_semantic",
        passed=passed,
        structural_ok=True,
        quantitative_ok=has_macro,
        referential_ok=True,
        substantive_ok=has_macro,
        defects=[] if has_macro else ["尚未填充宏觀卷級主題與線程語義"],
        metrics={"filled_threads": filled_threads, "filled_volumes": filled_volumes},
    )


def _evaluate_character_semantic(novel_id: str) -> GateResult:
    stats = db.get_geometry_stats(novel_id) if hasattr(db, "get_geometry_stats") else {}
    filled_nodes = int(stats.get("filled_nodes") or 0)
    graph_loader = getattr(db, "load_geometry_graph", None)
    graph = graph_loader(novel_id) if callable(graph_loader) else None
    has_char = filled_nodes > 0 or bool(
        graph and any(t.semantic and "character_binding" in t.semantic for t in graph.threads.values())
    )

    passed = has_char
    return GateResult(
        stage="character_semantic",
        passed=passed,
        structural_ok=True,
        quantitative_ok=has_char,
        referential_ok=True,
        substantive_ok=has_char,
        defects=[] if has_char else ["尚未將角色心理弧光與人物節點填充至幾何拓樸"],
        metrics={"filled_nodes": filled_nodes},
    )


def _evaluate_cross_relation(novel_id: str) -> GateResult:
    stats = db.get_geometry_stats(novel_id) if hasattr(db, "get_geometry_stats") else {}
    edge_count = int(stats.get("edge_count") or 0)
    filled_edges = int(stats.get("filled_edges") or 0)
    graph_loader = getattr(db, "load_geometry_graph", None)
    graph = graph_loader(novel_id) if callable(graph_loader) else None
    has_cross = (filled_edges > 0) or (edge_count == 0) or bool(graph and any(e.semantic for e in graph.edges))

    passed = has_cross
    return GateResult(
        stage="cross_relation",
        passed=passed,
        structural_ok=True,
        quantitative_ok=has_cross,
        referential_ok=True,
        substantive_ok=has_cross,
        defects=[] if has_cross else ["尚未填充跨線交織與衝突因果語義"],
        metrics={"edge_count": edge_count, "filled_edges": filled_edges},
    )


def _evaluate_volume_skeleton(novel_id: str, volume_index: Optional[int] = None) -> GateResult:
    vols = db.get_volumes(novel_id)
    if not vols:
        return GateResult("volume_skeleton", False, False, False, False, False, ["無分卷資料"], "請先生成分卷")

    target_vols = [v for v in vols if v.get("volume_index") == volume_index] if volume_index else vols
    defects = []
    all_ok = True

    for v in target_vols:
        v_idx = v.get("volume_index")
        skel = v.get("chapters_outline")
        if isinstance(skel, str):
            try:
                skel = json.loads(skel)
            except Exception:
                skel = None
        if not isinstance(skel, list) or len(skel) == 0:
            defects.append(f"第 {v_idx} 卷細綱為空")
            all_ok = False
            continue

        planned = db._get_clean_chapter_count(v) if hasattr(db, "_get_clean_chapter_count") else len(skel)
        if len(skel) < planned:
            defects.append(f"第 {v_idx} 卷章數不足（已規劃 {len(skel)}/{planned} 章）")
            all_ok = False

    return GateResult(
        stage="volume_skeleton",
        passed=all_ok,
        structural_ok=True,
        quantitative_ok=all_ok,
        referential_ok=True,
        substantive_ok=all_ok,
        defects=defects,
        metrics={"evaluated_volumes": len(target_vols)},
    )


def _evaluate_writer(novel_id: str, chapter_index: Optional[int]) -> GateResult:
    if not chapter_index:
        return GateResult("writer", True, True, True, True, True)

    ch = db.get_chapter(novel_id, int(chapter_index))
    if not ch or not ch.get("content"):
        return GateResult("writer", False, False, False, False, False, [f"第 {chapter_index} 章正文尚未持久化"], "請執行寫作任務")

    content = ch["content"].strip()
    if is_refusal_or_disclaimer(content):
        return GateResult("writer", False, True, False, False, False, [f"第 {chapter_index} 章包含 AI 拒答或免責聲明"], "請重新生成")

    length_ok = len(content) >= 800
    return GateResult(
        stage="writer",
        passed=length_ok,
        structural_ok=True,
        quantitative_ok=length_ok,
        referential_ok=True,
        substantive_ok=length_ok,
        defects=[] if length_ok else [f"第 {chapter_index} 章正文字數不足（{len(content)} 字）"],
        metrics={"word_count": len(content)},
    )


def _evaluate_editor(novel_id: str, chapter_index: Optional[int]) -> GateResult:
    if not chapter_index:
        return GateResult("editor", True, True, True, True, True)
    # If writer is ready and edited version or final gate passes
    writer_res = _evaluate_writer(novel_id, chapter_index)
    return GateResult(
        stage="editor",
        passed=writer_res.passed,
        structural_ok=writer_res.structural_ok,
        quantitative_ok=writer_res.quantitative_ok,
        referential_ok=writer_res.referential_ok,
        substantive_ok=writer_res.substantive_ok,
        defects=writer_res.defects,
    )
