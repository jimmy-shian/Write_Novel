# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
import re
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
    JSON_OBJECT_OUTPUT_CONTRACT,
)
from backend.prompts.json_output import get_json_schema_prompt_snippet

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

def parse_quantity_constraints(prompt_text):
    """
    從使用者提示詞中辨識是否有特定項目清單數量限制要求。
    """
    constraints = {
        "min_volumes": 10,
        "max_volumes": 20,
        "min_chapters": 40,
        "max_chapters": 50,
        "min_acts": 15,
        "max_acts": 24,
        "rec_acts": "15-20",
        "min_waves": 18,
        "max_waves": 24
    }
    if not prompt_text:
        return constraints
        
    text = str(prompt_text)
    match_50_plus = re.search(r'(?:5[0-9]|6[0-9]|7[0-9]|8[0-9]|9[0-9]|[1-9][0-9]{2,})(?:\+|以上|個|波|幕|卷|章|項|條)', text)
    if match_50_plus or "50+" in text:
        num = 50
        num_match = re.search(r'(\d+)', text)
        if num_match:
            try:
                num = int(num_match.group(1))
            except ValueError:
                num = 50
        
        if "幕" in text or "act" in text.lower():
            constraints["min_acts"] = num
            constraints["max_acts"] = int(num * 1.5)
            constraints["rec_acts"] = f"{num}-{int(num * 1.2)}"
        elif "波" in text or "wave" in text.lower():
            constraints["min_waves"] = num
            constraints["max_waves"] = int(num * 1.5)
        elif "卷" in text or "volume" in text.lower():
            constraints["min_volumes"] = num
            constraints["max_volumes"] = int(num * 1.5)
        elif "章" in text or "chapter" in text.lower():
            constraints["min_chapters"] = num
            constraints["max_chapters"] = int(num * 1.5)
        else:
            constraints["min_acts"] = num
            constraints["max_acts"] = int(num * 1.5)
            constraints["rec_acts"] = f"{num}-{int(num * 1.2)}"
            constraints["min_waves"] = num
            constraints["max_waves"] = int(num * 1.5)
            constraints["min_volumes"] = num
            constraints["max_volumes"] = int(num * 1.5)
            constraints["min_chapters"] = num
            constraints["max_chapters"] = int(num * 1.5)
            
    return constraints

def format_prompt_constraints(prompt_template, c):
    """將 placeholders 替換為 parsed 的數量限制"""
    return (prompt_template
            .replace("__MIN_VOLUMES__", str(c["min_volumes"]))
            .replace("__MAX_VOLUMES__", str(c["max_volumes"]))
            .replace("__MIN_CHAPTERS__", str(c["min_chapters"]))
            .replace("__MAX_CHAPTERS__", str(c["max_chapters"]))
            .replace("__MIN_ACTS__", str(c["min_acts"]))
            .replace("__MAX_ACTS__", str(c["max_acts"]))
            .replace("__REC_ACTS__", str(c["rec_acts"]))
            .replace("__MIN_WAVES__", str(c["min_waves"]))
            .replace("__MAX_WAVES__", str(c["max_waves"])))

def build_story_architect_messages(genre, style, user_prompt):
    """世界觀架構師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    c = parse_quantity_constraints(user_prompt)
    guidelines_fmt = format_prompt_constraints(STORY_ARCHITECT_GUIDELINES, c)
    system_prompt = f"{STORY_ARCHITECT_PROMPT}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Story Architect / 世界觀架構師",
        "- 類型、風格基調、作者原始創作需求。\n- 若是重跑或局部調整，會在使用者內容中明確提供指定要求。",
        "只建立世界觀、核心衝突、全書宏觀大綱、多幕結構與角色登場策略；不要生成角色 Bible、卷列表、章節骨架或正文。",
        "輸出必須是完整 worldview JSON；不得在 JSON 外加入解釋；不得把伏筆種子與關鍵轉折點當成本階段主要產物。"
    )
    system_prompt += "\n*[提示：`multi_act_structure` 與 `progressive_character_plan` 可以依據需要規劃任意數量的多幕/波段（例如：4幕、5波等），無須限制為範例中的數量。]*\n"
    
    user_content = f"""【使用者創作需求與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：{user_prompt}

請根據以上設定，為本作品生成符合結構的完整世界觀 JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_worldview_core_messages(genre, style, user_prompt):
    """僅生成世界觀核心設定（theme, main_conflict, worldview, macro_outline）的提示詞"""
    from backend.prompts.prompt_main import STORY_ARCHITECT_PROMPT, WORLDVIEW_CORE_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("worldview_core")
    c = parse_quantity_constraints(user_prompt)
    guidelines_fmt = format_prompt_constraints(WORLDVIEW_CORE_GUIDELINES, c)
    system_prompt = f"{STORY_ARCHITECT_PROMPT}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Story Architect Core / 核心世界觀架構師",
        "- 類型、風格基調、作者原始創作需求。\n- 本階段尚未有多幕結構、角色策略、角色 Bible、篇卷與正文。",
        "只生成 theme、main_conflict、worldview、macro_outline 四個核心欄位，為後續子階段提供基底。",
        "輸出只能是核心世界觀 JSON；不要生成 multi_act_structure、progressive_character_plan、characters、volumes 或 chapters。"
    )
    
    user_content = f"""【使用者創作需求與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：{user_prompt}

請根據以上設定，僅生成核心世界觀（theme、main_conflict、worldview、macro_outline）的 JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_multi_act_structure_messages(worldview_core_json, user_prompt):
    """基於核心世界觀，獨立生成多幕式起伏結構的提示詞"""
    from backend.prompts.prompt_main import MULTI_ACT_STRUCTURE_PROMPT, MULTI_ACT_STRUCTURE_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("multi_act_structure")
    c = parse_quantity_constraints(user_prompt)
    prompt_fmt = format_prompt_constraints(MULTI_ACT_STRUCTURE_PROMPT, c)
    guidelines_fmt = format_prompt_constraints(MULTI_ACT_STRUCTURE_GUIDELINES, c)
    system_prompt = f"{prompt_fmt}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Drama Structure Specialist / 多幕式結構師",
        "- 已生成的核心世界觀 JSON。\n- 作者原始要求只作為風格與方向參考。",
        "只規劃 multi_act_structure，描述全書起伏、危機遞進與幕次功能。",
        "輸出只能包含 multi_act_structure；不要改寫核心世界觀，不要生成角色 Bible、伏筆清單、篇卷或章節。"
    )
    
    user_content = f"""【已確定的核心世界觀設定】
{worldview_core_json}

【使用者原始要求（參考）】
{user_prompt}

請根據上述已確定的核心設定，獨立規劃並生成大長篇故事的「多幕式起伏結構（multi_act_structure）」。
幕次 title 必須嚴格統一為『第一幕 (自擬階段名稱)』、『第二幕 (自擬階段名稱)』等格式，使用中文數字編號，不允許使用『1.』、『1-01』、『Setup』、『Act 1』等標號。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_progressive_character_plan_messages(worldview_core_json, multi_act_json, user_prompt):
    """基於核心世界觀與多幕式結構，獨立生成角色漸進登場規劃策略的提示詞"""
    from backend.prompts.prompt_main import PROGRESSIVE_CHARACTER_PLAN_PROMPT, PROGRESSIVE_CHARACTER_PLAN_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("progressive_character_plan")
    try:
        parsed_acts = json.loads(multi_act_json) if isinstance(multi_act_json, str) else multi_act_json
    except Exception:
        parsed_acts = None
    acts_payload = parsed_acts.get("multi_act_structure") if isinstance(parsed_acts, dict) else parsed_acts
    act_count = len(acts_payload) if isinstance(acts_payload, list) else None
    
    c = parse_quantity_constraints(user_prompt)
    if act_count:
        c["min_waves"] = max(c["min_waves"], act_count)
        c["max_waves"] = max(c["max_waves"], int(act_count * 1.5))
        
    if act_count == 18:
        wave_count_rule = "本次 multi_act_structure 已明確為 18 幕，因此 progressive_character_plan 必須正好輸出 18 波，不能只輸出前 5 波或 15 波，也不能超過 18 波。"
    elif act_count:
        wave_count_rule = f"本次 multi_act_structure 共 {act_count} 幕，progressive_character_plan 不得少於 {act_count} 波，並需覆蓋所有主要幕次需求。"
    else:
        wave_count_rule = f"若無法可靠計算幕數，progressive_character_plan 至少輸出 {c['min_waves']} 波，最多 {c['max_waves']} 波。"
        
    prompt_fmt = format_prompt_constraints(PROGRESSIVE_CHARACTER_PLAN_PROMPT, c)
    guidelines_fmt = format_prompt_constraints(PROGRESSIVE_CHARACTER_PLAN_GUIDELINES, c)
    system_prompt = f"{prompt_fmt}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Character Progression Planner / 角色登場策略規劃師",
        "- 已生成的核心世界觀 JSON。\n- 已生成的 multi_act_structure。\n- 作者原始要求只作為風格與方向參考。",
        "只規劃 progressive_character_plan，說明各波次需要哪些角色功能與登場節奏。",
        "輸出只能包含 progressive_character_plan；不要生成完整角色卡，不要憑空定稿所有角色細節。"
    )
    
    user_content = f"""【已確定的核心世界觀設定】
{worldview_core_json}

【已確定的多幕式劇情結構】
{multi_act_json}

【使用者原始要求（參考）】
{user_prompt}

請根據上述設定，獨立規劃並生成群像劇的「角色漸進登場規劃策略（progressive_character_plan）」。
{wave_count_rule}
波次 title 必須嚴格統一為『第一波 (自擬登場群體或階段主題)』、『第二波 (自擬登場群體或階段主題)』等格式，使用中文數字編號，不允許出現『1.』、『1-0XX』、『Wave 1』等標號。
每一波 content 必須包含：主要登場角色、其關鍵功能（如導師、盟友、反派、中立者、情報源、情感錨點、理念代表、戰力支點）、與該波對應幕次/劇情階段的關係，以及對主角成長或群像關係的影響。
角色設定需與 worldview factions、多幕結構起伏、伏筆與轉折需求緊密對應；允許引入新角色，但必須為後續角色 Bible 留出發展空間，不要一次定稿完整角色卡。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

