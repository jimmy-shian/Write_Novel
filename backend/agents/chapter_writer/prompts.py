# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
from backend.schemas import agent_json
from backend import persistence as db
from backend.schemas.agent_json import CHARACTER_BASIC_FIELDS
from backend.prompts.prompt_main import (
    STORY_ARCHITECT_PROMPT,
    STORY_ARCHITECT_GUIDELINES,
    VOLUMES_PLANNER_PROMPT,
    VOLUMES_PLANNER_GUIDELINES,
    VOLUME_SKELETON_PROMPT,
    VOLUME_SKELETON_GUIDELINES,
    CHARACTER_DESIGNER_PROMPT,
    CHARACTER_DESIGNER_GUIDELINES,
    FORESHADOWING_ORCHESTRATOR_PROMPT,
    FORESHADOWING_ORCHESTRATOR_GUIDELINES,
    CHAPTER_WRITER_PROMPT,
    CHAPTER_WRITER_GUIDELINES,
    VOLUME_SKELETON_PROMPT_PLUS,
    CHARACTER_DESIGNER_PROMPT_PLUS
)
from backend.prompts.prompt_detail_modifier import (
    EDITOR_PROMPT,
    INCREMENTAL_CHARACTER_PROMPT,
    INCREMENTAL_CHARACTER_APPEND_PROMPT
)
from backend.prompts.prompt_instructions import (
    CO_PILOT_ORCHESTRATOR_PROMPT,
    DIRECTOR_COMMON_FOOTER
)
from backend.prompts.output_contracts import (
    DIRECTOR_DECISION_KEY_CONTRACT,
    DIRECTOR_HARD_VALIDATION_POLICY,
    DIRECTOR_MANDATORY_INSPECTION_POLICY,
    DIRECTOR_TOOL_CALL_CONTRACT,
    STRICT_JSON_KEY_CONTRACT,
    format_json_schema_prompt,
)

# --- 世界觀摘要輔助函數 ---
# 用於提取世界觀的關鍵摘要，避免過長的上下文導致 API 失敗
MAX_WORLDVIEW_SUMMARY_LENGTH = 36000
MAX_MACRO_OUTLINE_LENGTH = 12000
MAX_DIRECTOR_WORLDVIEW_LENGTH = 42000
MAX_DIRECTOR_CHARACTERS_LENGTH = 36000
MAX_DIRECTOR_PLOT_LENGTH = 52000
MAX_DIRECTOR_PROSE_LENGTH = 32000
MAX_DIRECTOR_REPORT_LENGTH = 30000
MAX_GOLD_RULES_CONTEXT_LENGTH = 16000

# --- 角色基本設定輔助函數 ---
# 定義角色只需要傳入的基本欄位，過濾掉冗長的背景故事等欄位
# 核心欄位：name 和 personality 是必留的，其他可以過濾
# CHARACTER_BASIC_FIELDS 定義在 agent_json.py 中，供各模組統一引用

MAX_CHARACTERS_SUMMARY_LENGTH = 26000

from backend.prompts.common.context import *
from backend.prompts.common.context import _context_query_text

def build_chapter_writer_messages(
    worldview_text,
    characters_bible,
    current_outline,
    surrounding_plot,
    vol_outline_context,
    clue_payoff_details,
    custom_style,
    chapter_index,
    user_prompt=None,
    narrative_memory_context=None,
):
    """正文作家寫作提示詞拼接"""
    system_prompt = CHAPTER_WRITER_PROMPT + "\n" + CONTEXT_REQUEST_RULE + "\n\n" + CHAPTER_WRITER_GUIDELINES
    system_prompt += build_agent_context_contract(
        "Chapter Writer / 正文作家",
        "- 經後端挑選的世界觀背景，包含 factions / 勢力設定。\n- 本章大綱、前後章節脈絡、本卷概要、本卷活躍勢力與規則。\n- 本章命中的角色完整卡與其他角色基本關係。\n- 章節記憶、arc summary、前章正文尾段與未回收伏筆。\n- 本章與附近章節的伏筆/轉折分配。",
        "只撰寫指定 chapter_index 的正式正文，嚴格落實本章大綱、敘事記憶、已分配任務、角色卡與世界觀勢力設定。",
        "正式正文前必須輸出 [START_OF_PROSE]；不要改寫世界觀、角色 Bible、卷章大綱，不要輸出 JSON。"
    )
    
    context_query = _context_query_text(current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, user_prompt)
    characters_bible_filtered = build_relevant_character_context(
        characters_bible,
        query_text=context_query,
        force_full_names=(current_outline or {}).get("characters_active") if isinstance(current_outline, dict) else None,
    )
    
    extra_prompt_block = ""
    if user_prompt and str(user_prompt).strip():
        extra_prompt_block = f"""
【本章額外創作指令】
{str(user_prompt).strip()}
"""

    user_content = f"""【世界觀背景】
{worldview_text}

【角色 Bible 聖經】(命中角色完整設定；其他角色名稱與基本關係)
{json.dumps(characters_bible_filtered, ensure_ascii=False, indent=2)}

【當前章節 (第 {chapter_index} 章) 大綱】
{json.dumps(current_outline, ensure_ascii=False, indent=2)}

【敘事記憶 / 連續性上下文】
{narrative_memory_context or "（尚無可用章節記憶；若為第一章可忽略）"}

{surrounding_plot}
{vol_outline_context}
{clue_payoff_details}
{extra_prompt_block}

【勢力與角色一致性硬性規則】
- 勢力/組織描寫以世界觀 factions、世界觀背景與當前卷設定為準；不得臨時改寫勢力立場、制度、資源、敵友關係或名稱。
- 本卷 factions 代表本章可活躍的勢力範圍；若正文需要引入其他勢力，必須與世界觀既有設定相容，不能憑空新增制度背景。
- 本章命名角色必須依角色 Bible 行動、說話與做決策；若缺少角色卡，應回報上下文不足，不要硬寫。

請根據以上豐富的上下文細節，展開本章正文寫作；正文目標字數為 1500 至 2000 字左右，不要寫成摘要或短章。
【寫作風格基調】
{custom_style}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
