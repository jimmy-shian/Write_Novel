# -*- coding: utf-8 -*-
"""
Facade 代理接口 (Agents Facade Wrapper)
包裝並將所有呼叫導向全新設計的模組化邏輯檔案：
- `agent_main.py` (主要創作邏輯)
- `agent_detail_modifier.py` (細節修改與 Patch 邏輯)
- `agent_instructions.py` (對話框與總監決策邏輯)
此檔保持原有函數名稱及簽章完全無損，防範任何破壞性變更 (Non-breaking compatibility)。
"""

from agent_main import (
    clean_json_text,
    parse_json_safely,
    _sse_content,
    _sse_error,
    _sse_error_done,
    _looks_like_placeholder_chapter,
    _normalize_chapter_outlines,
    validate_worldview,
    validate_characters,
    validate_plot,
    validate_plot_has_chapter,
    compile_context,
    run_agent_stream,
    run_story_architect,
    run_volumes_planner,
    run_character_designer,
    run_volume_skeleton_planner,
    run_foreshadowing_orchestrator,
    run_plot_planner,
    generate_chapter_synopsis,
    run_chapter_writer
)

from agent_extension import (
    run_incremental_architect,
    run_incremental_character_designer,
    run_incremental_character_append,
    run_incremental_plot_planner,
    run_volume_alignment,
    run_volume_jit_alignment,
    run_editor_agent,
    run_copilot_chat,
    run_director_decision,
    run_director_decision_help,
    parse_incremental_command,
    verify_novel_integrity,
    pre_check_next_agent,
    get_simplified_director_prompt,
    infer_review_scope
)

# --- DIRECTOR PIPELINE EXECUTION MODE STATE CONTROL ---
# 保持總監自動執行狀態的內存共享
DIRECTOR_EXECUTION_MODE = {"auto_execute": False, "user_prompt": ""}

def set_director_auto_execute(mode: bool):
    DIRECTOR_EXECUTION_MODE["auto_execute"] = mode

def get_director_auto_execute() -> bool:
    return DIRECTOR_EXECUTION_MODE.get("auto_execute", False)

def set_director_user_prompt(prompt: str):
    DIRECTOR_EXECUTION_MODE["user_prompt"] = prompt

def get_director_user_prompt() -> str:
    return DIRECTOR_EXECUTION_MODE.get("user_prompt", "")
