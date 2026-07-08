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
)
from backend.prompts.json_output import format_json_schema_prompt, get_json_schema_prompt_snippet

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

def build_incremental_architect_messages(target_section, worldview_text, user_hint):
    """增量世界觀提示詞拼接"""
    from backend.schemas.agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json
    
    if target_section == "foreshadowing_seeds":
        schema = {"foreshadowing_seeds": FORESHADOWING_OUTPUT_SCHEMA["foreshadowing_seeds"]}
        schema_snippet = format_json_schema_prompt(schema, label="this foreshadowing_seeds schema")
    elif target_section == "key_turning_points":
        schema = {"key_turning_points": FORESHADOWING_OUTPUT_SCHEMA["key_turning_points"]}
        schema_snippet = format_json_schema_prompt(schema, label="this key_turning_points schema")
    else:
        schema_snippet = get_json_schema_prompt_snippet("worldview")
        
    system_prompt = f"""你是一位精準的世界觀增量修正師。請根據用戶的修改要求，對現有的世界觀進行精準的局部修改或增量追加。
你只需要回傳【本次有新增或被修改的 {target_section}】的內容 JSON 區塊即可，後端會自動完成替換與合併。

{schema_snippet}
"""
    system_prompt += build_agent_context_contract(
        "Incremental Architect / 世界觀增量修正師",
        "- 現有世界觀全文或摘要。\n- 指定 target_section。\n- 使用者或總監的局部修改要求。",
        "只修改 target_section 對應內容；不要重建整個世界觀，除非 target_section 本身就是完整核心世界觀。",
        "只輸出本次新增或被修改的 JSON 區塊，讓後端合併；不要輸出解釋文字。"
    )
    user_content = f"""【現有世界觀】
{worldview_text}

【目標修改板塊】
- target_section: {target_section}

【使用者修改要求 (user_hint)】
{user_hint}

請輸出更新後的 JSON 區塊：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_incremental_character_messages(worldview_text, existing_chars_json, target_char_content, target_char_index, field_name, user_hint):
    """增量角色修改提示詞拼接"""
    if field_name:
        patch_schema = {
            field_name: "只填此欄位的新值；可以是字串、陣列或物件，依原欄位型別決定"
        }
    elif target_char_index is not None:
        patch_schema = {
            "character": {
                "name": "只有需要修改名稱時才填",
                "role": "可省略未修改欄位",
                "personality": ["可只回傳被修改欄位"],
                "want": "可省略",
                "need": "可省略",
                "fatal_flaw": "可省略",
                "motivation": "可省略",
                "arc": "可省略",
                "speech_style": "可省略",
                "appearance": "可省略",
                "background": "可省略",
                "relationships": []
            }
        }
    else:
        patch_schema = {
            "characters": [
                {
                    "name": "新角色具體姓名/代號",
                    "role": "",
                    "entry_phase": "",
                    "personality": [],
                    "want": "",
                    "need": "",
                    "fatal_flaw": "",
                    "motivation": "",
                    "arc": "",
                    "speech_style": "",
                    "appearance": "",
                    "background": "",
                    "relationships": []
                }
            ]
        }
    schema_snippet = format_json_schema_prompt(patch_schema, label="this incremental character patch schema")
    
    if target_char_index is not None:
        if field_name:
            # Modify specific field of character
            system_prompt = INCREMENTAL_CHARACTER_PROMPT.format(
                existing_worldbuilding=worldview_text,
                existing_characters=existing_chars_json + "\n" + target_char_content,
                user_hint=f"請只修改角色索引 {target_char_index} 的 `{field_name}` 欄位。具體修改要求：{user_hint}\n\n輸出只能包含 `{field_name}` 或 `value/new_value`，不得輸出其他未修改角色。"
            )
        else:
            # Modify full character design
            system_prompt = INCREMENTAL_CHARACTER_PROMPT.format(
                existing_worldbuilding=worldview_text,
                existing_characters=existing_chars_json + "\n" + target_char_content,
                user_hint=f"請局部修正角色索引 {target_char_index}。要求：{user_hint}\n\n只輸出本角色被修改欄位的 patch；未修改欄位請省略，後端會與原角色深度合併。不得回傳完整角色列表。"
            )
    else:
        # Append mode
        system_prompt = INCREMENTAL_CHARACTER_APPEND_PROMPT.format(
            existing_worldbuilding=worldview_text,
            existing_characters=existing_chars_json,
            new_characters="請根據修改要求追加新角色",
            user_hint=user_hint
        )
        
    system_prompt += f"\n\n{schema_snippet}"
    system_prompt += build_agent_context_contract(
        "Incremental Character / 角色增量修正師",
        "- 現有世界觀摘要。\n- 現有角色聖經。\n- 若為修改，會提供目標角色或欄位；若為追加，會提供追加要求。",
        "只修補指定角色欄位、指定角色卡，或追加新角色；不要重寫整個角色庫。",
        "輸出增量 patch JSON。未修改欄位省略，避免覆蓋既有角色資料。"
    )
    
    user_content = f"""請根據以上增量指令與規則，輸出更新後的 JSON 區塊："""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
