# -*- coding: utf-8 -*-
"""
Director Arbitration & Decision Engine.
Evaluates physical DB facts via the Four-Tier Rigid Gate Framework and arbitrates
authoritative pipeline actions: CONTINUE, AUTO_REGENERATE, REDIRECT, INCREMENTAL_PATCH, FINISH.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from backend import persistence as db
from backend.generation.core.flow_spec import TOPO_STAGE_ORDER, normalize_stage_name, get_stage_prerequisites
from backend.generation.core.contracts import DirectorArbitration
from backend.generation.core.gates import evaluate_stage_rigid_gate
from backend.generation.director.self_healing import heal_geometry_stalemate, heal_missing_volumes
from backend.generation.modules.blueprint_planner import generate_planning_blueprint


def arbitrate_director_decision(
    novel_id: str,
    current_stage: Optional[str] = None,
    loop_count: int = 0,
    context: Optional[Dict[str, Any]] = None,
) -> DirectorArbitration:
    """
    Evaluates stage health against physical database facts,
    emitting a single typed DirectorArbitration envelope.
    """
    context = context or {}
    stage = normalize_stage_name(current_stage or "worldview")

    # Anti-loop defense: if failed >= 3 times, invoke deterministic self-healing
    if loop_count >= 3:
        if stage == "planning_blueprint":
            blueprint = db.get_planning_blueprint(novel_id) if hasattr(db, "get_planning_blueprint") else None
            if not blueprint:
                generate_planning_blueprint(novel_id)
            return DirectorArbitration(
                action="CONTINUE",
                target="characters",
                rationale={
                    "factual_db_state": "規劃拓樸藍圖已由確定性模組重建",
                    "action_justification": f"重複嘗試 {loop_count} 次，修復規劃資料後再進入角色規劃",
                },
                directive={"agent_prompt": "請依規劃拓樸藍圖執行角色與陣營掛接"},
            )
        if stage == "geometry":
            heal_res = heal_geometry_stalemate(novel_id)
            return DirectorArbitration(
                action="CONTINUE",
                target="macro_semantic",
                rationale={
                    "factual_db_state": "觸發幾何圖自動降級自愈修復",
                    "action_justification": f"重複嘗試 {loop_count} 次，演算法已安全持久化幾何圖譜",
                },
                directive={"agent_prompt": "請繼續進行宏觀語義填充"},
            )
        elif stage == "volumes":
            heal_missing_volumes(novel_id, target_count=8)
            return DirectorArbitration(
                action="CONTINUE",
                target="geometry",
                rationale={
                    "factual_db_state": "觸發分卷自動補齊自愈修復",
                    "action_justification": f"重複嘗試 {loop_count} 次，演算法已保底補齊分卷結構",
                },
                directive={"agent_prompt": "請繼續進行幾何拓樸實體化"},
            )

    # Check prerequisites first
    prereqs = get_stage_prerequisites(stage)
    for p in prereqs:
        p_gate = evaluate_stage_rigid_gate(p, novel_id, context)
        if not p_gate.passed:
            return DirectorArbitration(
                action="REDIRECT",
                target=p,
                rationale={
                    "factual_db_state": f"上游依賴階段 [{p}] 驗收未通過",
                    "gate_failure_reasons": p_gate.defects,
                    "action_justification": f"當前階段 [{stage}] 依賴的前置地基未完成，強制重定向回上游階段",
                },
                directive={
                    "agent_prompt": f"請先補齊前置階段 [{p}]：{p_gate.remediation_hint}",
                },
            )

    # Evaluate current stage
    gate = evaluate_stage_rigid_gate(stage, novel_id, context)

    if gate.passed:
        # Resolve next stage
        idx = TOPO_STAGE_ORDER.index(stage) if stage in TOPO_STAGE_ORDER else 0
        if idx + 1 < len(TOPO_STAGE_ORDER):
            next_stage = TOPO_STAGE_ORDER[idx + 1]
            return DirectorArbitration(
                action="CONTINUE",
                target=next_stage,
                rationale={
                    "factual_db_state": f"階段 [{stage}] 四層剛性驗收全部通過",
                    "action_justification": f"進入下一正常標準創作階段 [{next_stage}]",
                },
                directive={"agent_prompt": f"請執行階段 [{next_stage}] 生成任務"},
            )
        else:
            return DirectorArbitration(
                action="FINISH",
                target="reconciliation",
                rationale={"factual_db_state": "全流程所有階段皆已達標完成"},
            )
    else:
        # Current stage failed gate
        return DirectorArbitration(
            action="AUTO_REGENERATE",
            target=stage,
            rationale={
                "factual_db_state": f"階段 [{stage}] 實質驗收不合格",
                "gate_failure_reasons": gate.defects,
                "action_justification": f"原地重試當前任務，附帶剛性負反饋提示詞",
            },
            directive={
                "agent_prompt": f"生成未達標，請重新調整修復：{gate.remediation_hint}。具體缺陷：{'; '.join(gate.defects)}",
            },
        )
