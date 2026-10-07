# -*- coding: utf-8 -*-
"""Deterministic handlers for the topological planning stages."""

from __future__ import annotations

import json
from typing import Any, Dict, Generator

from backend.generation.modules.blueprint_planner import generate_planning_blueprint
from backend.generation.modules.scale_architect import build_narrative_scale_spec
from backend.generation.core.gates import evaluate_stage_rigid_gate


def _sse(payload: Dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def run_narrative_scale_task(task, context=None) -> Generator[str, None, None]:
    spec = build_narrative_scale_spec(task.novel_id)
    yield _sse({"type": "thinking", "delta": f"已計算長篇規模：{spec.total_volumes} 卷、{spec.total_chapters} 章、{spec.act_count} 幕。\n"})
    yield _sse({"type": "content", "delta": json.dumps(spec.to_dict(), ensure_ascii=False)})
    yield "data: [DONE]\n\n"


def run_planning_blueprint_task(task, context=None) -> Generator[str, None, None]:
    yield _sse({"type": "thinking", "delta": "正在建立世界觀之後、分卷之前的規劃拓樸藍圖...\n"})
    blueprint = generate_planning_blueprint(task.novel_id)
    gate = evaluate_stage_rigid_gate("planning_blueprint", task.novel_id)
    if not gate.passed:
        raise RuntimeError("規劃拓樸藍圖驗收未通過：" + "；".join(gate.defects))
    payload = blueprint.to_dict()
    payload["stats"] = gate.metrics
    yield _sse({"type": "content", "delta": json.dumps(payload, ensure_ascii=False)})
    yield "data: [DONE]\n\n"
