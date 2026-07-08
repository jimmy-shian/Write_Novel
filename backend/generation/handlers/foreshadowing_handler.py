"""Foreshadowing generation handler — supports split target_field generation.

Director 需要在 agent_prompt 中帶入 [BATCH: foreshadowing_seeds] 或 [BATCH: key_turning_points]
標記，後端會自動解析並僅生成對應類別的資料，保留另一類已有的資料不被覆蓋。
這避免了單次生成 50+ 條伏筆 + 50+ 條轉折點導致 JSON 過長而解析錯誤。
"""

from __future__ import annotations

import re
import json


from backend import persistence as db
from backend.common.config import MIN_FORESHADOWING_SEEDS, MIN_KEY_TURNING_POINTS
from backend.generation.routing.schema import GenerationTaskRequest
from backend.agents.foreshadowing_orchestrator.runner import run_foreshadowing_orchestrator


def _extract_batch_target(task: GenerationTaskRequest) -> str | None:
    """從 agent_prompt 或 instruction 中提取 [BATCH: xxx] 標記。"""
    texts_to_check = [
        getattr(task, "agent_prompt", None) or "",
        task.instruction or "",
        task.hint or "",
        task.user_prompt or "",
    ]
    for text in texts_to_check:
        if not text:
            continue
        m = re.search(r'\[BATCH:\s*(foreshadowing_seeds|key_turning_points)\]', text, re.IGNORECASE)
        if m:
            return m.group(1).lower().strip()
    return None


def _normalize_target_field(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if raw in {"foreshadowing_seeds", "key_turning_points"}:
        return raw
    return None


def _foreshadowing_counts(novel_id: str) -> tuple[int, int]:
    wb = db.get_latest_worldbuilding(novel_id)
    if not wb:
        return 0, 0
    try:
        parsed = db.parse_worldview_to_json(wb["content"])
    except Exception:
        return 0, 0
    seeds = parsed.get("foreshadowing_seeds", [])
    turns = parsed.get("key_turning_points", [])
    return (
        len(seeds) if isinstance(seeds, list) else 0,
        len(turns) if isinstance(turns, list) else 0,
    )


def _infer_batch_target_from_db(novel_id: str) -> str | None:
    seed_count, turn_count = _foreshadowing_counts(novel_id)
    if seed_count < MIN_FORESHADOWING_SEEDS:
        return "foreshadowing_seeds"
    if turn_count < MIN_KEY_TURNING_POINTS:
        return "key_turning_points"
    return None


def _characters_ready(novel_id: str) -> bool:
    char_data = db.get_latest_characters(novel_id)
    if not char_data:
        return False

    candidates = []
    if char_data.get("json_data"):
        try:
            candidates.append(json.loads(char_data.get("json_data") or "{}"))
        except Exception:
            pass
    if char_data.get("parsed_data") is not None:
        candidates.append(char_data.get("parsed_data"))

    for parsed in candidates:
        if isinstance(parsed, dict):
            chars = parsed.get("characters", [])
        elif isinstance(parsed, list):
            chars = parsed
        else:
            chars = []
        if isinstance(chars, list) and len(chars) > 0:
            return True
    return False


def _redirect_to_characters(task: GenerationTaskRequest, prompt: str):
    decision = {
        "action": "CONTINUE",
        "target": "characters",
        "hint": "伏筆與轉折需要角色 Bible，請先生成角色設定。",
        "agent_prompt": prompt or "請根據世界觀與作者原始需求生成角色 Bible。",
        "agent_context": "後端前置檢查：foreshadowing 階段需要 related_characters，但目前角色資料為空。",
        "reason": "foreshadowing prompt 需要角色 Bible 提供具體角色名稱；不能在角色空資料上硬生成轉折。",
        "volume_index": None,
        "chapter_index": None,
    }

    def _generator():
        yield "data: " + json.dumps({
            "type": "content",
            "delta": "\n【後端前置檢查】伏筆與轉折需要先完成角色設定。已導向角色階段。\n```json\n"
            + json.dumps(decision, ensure_ascii=False, indent=2)
            + "\n```\n"
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"

    return _generator()


def run_foreshadowing_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()

    # 優先從 task 直接屬性讀取（若前端或 copilot 已明確傳入）
    target_field = _normalize_target_field(getattr(task, "target_field", None) or None)

    # 若未直接傳入，從 agent_prompt / instruction 中解析 [BATCH: xxx] 標記
    if not target_field:
        target_field = _normalize_target_field(_extract_batch_target(task))

    # 舊前端或手動呼叫可能漏帶 batch 標記；用 DB 目前缺項推斷，避免落回全量驗證。
    if not target_field:
        target_field = _infer_batch_target_from_db(task.novel_id)

    if not _characters_ready(task.novel_id):
        return _redirect_to_characters(task, prompt)

    return run_foreshadowing_orchestrator(
        task.novel_id,
        user_prompt=prompt or None,
        target_field=target_field,
        stream=task.options.stream,
        force_json=True,
    )
