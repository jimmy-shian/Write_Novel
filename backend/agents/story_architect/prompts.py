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

def build_story_architect_messages(genre, style, user_prompt, novel_id=None, existing_assets_context=None):
    """世界觀架構師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    c = parse_quantity_constraints(user_prompt)
    guidelines_fmt = format_prompt_constraints(STORY_ARCHITECT_GUIDELINES, c)
    system_prompt = f"{STORY_ARCHITECT_PROMPT}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Story Architect / 世界觀架構師",
        "- 類型、風格基調、作者原始創作需求與作品核心基石。\n- 既有設定資產（角色聖經、伏筆網絡、篇卷大綱等，修訂時須嚴格維持連續性，避免設定斷層）。\n- 若是重跑或局部調整，會在使用者內容中明確提供指定要求。",
        "只建立世界觀、核心衝突、全書宏觀大綱、多幕結構與角色登場策略；不要生成角色 Bible、卷列表、章節骨架或正文。",
        "輸出必須是完整 worldview JSON；不得在 JSON 外加入解釋；不得把伏筆種子與關鍵轉折點當成本階段主要產物。"
    )
    system_prompt += "\n*[提示：`multi_act_structure` 與 `progressive_character_plan` 可以依據需要規劃任意數量的多幕/波段（例如：4幕、5波等），無須限制為範例中的數量。]*\n"
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    assets_block = f"【已確立之既有設定資產（修訂時嚴格保持連續性避免衝突）】\n{existing_assets_context}\n\n" if existing_assets_context else ""
    if core_context:
        instructions = (user_prompt or "").strip()
        if novel_id:
            try:
                novel = db.get_novel(novel_id)
                p_prompt = (novel.get("pipeline_prompt") or "").strip()
                if p_prompt and p_prompt in instructions:
                    instructions = instructions.replace(f"【故事原案大綱靈感】\n{p_prompt}", "")
                    instructions = instructions.replace(f"【作者創作原案與要求】\n{p_prompt}", "")
                    instructions = instructions.replace(p_prompt, "").strip()
            except Exception:
                pass
        instructions = instructions.strip() or "請為本小說構建完整的世界觀設定、力量體系與時代背景"
        user_content = f"""{core_context}{assets_block}【本階段執行目標】
{instructions}

請根據上述作品核心基石與靈感羅盤，為本作品生成符合結構的完整世界觀 JSON 設定。
請緊扣作品原案的核心精神與設定基石，充分發揮故事的原創特色。
"""
    else:
        user_content = f"""{assets_block}【使用者創作需求與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：
{user_prompt}

請根據以上作品核心基石與創作要求，為本作品生成符合結構的完整世界觀 JSON 設定。
請緊扣作品原案的核心精神與設定基石，充分發揮故事的原創特色。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_worldview_core_messages(genre, style, user_prompt, novel_id=None, existing_assets_context=None):
    """僅生成世界觀核心設定（theme, main_conflict, worldview, macro_outline）的提示詞"""
    from backend.prompts.prompt_main import STORY_ARCHITECT_PROMPT, WORLDVIEW_CORE_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("worldview_core")
    c = parse_quantity_constraints(user_prompt)
    guidelines_fmt = format_prompt_constraints(WORLDVIEW_CORE_GUIDELINES, c)
    system_prompt = f"{STORY_ARCHITECT_PROMPT}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Story Architect Core / 核心世界觀架構師",
        "- 類型、風格基調、作者原始創作需求與作品核心基石。\n- 既有設定資產（若處於增量修訂模式，須嚴格維持與既有角色/篇卷連續性）。\n- 本階段尚未有多幕結構、角色策略、角色 Bible、篇卷與正文。",
        "聚焦構思 theme、main_conflict、worldview、macro_outline 四個核心欄位，為後續子階段提供基底。",
        "輸出核心世界觀 JSON 資料。"
    )
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    assets_block = f"【已確立之既有設定資產（修訂時嚴格保持連續性避免衝突）】\n{existing_assets_context}\n\n" if existing_assets_context else ""
    if core_context:
        # 去除 user_prompt 中可能重複出現的原案內容
        instructions = (user_prompt or "").strip()
        if novel_id:
            try:
                novel = db.get_novel(novel_id)
                p_prompt = (novel.get("pipeline_prompt") or "").strip()
                if p_prompt and p_prompt in instructions:
                    instructions = instructions.replace(f"【故事原案大綱靈感】\n{p_prompt}", "")
                    instructions = instructions.replace(f"【作者創作原案與要求】\n{p_prompt}", "")
                    instructions = instructions.replace(p_prompt, "").strip()
            except Exception:
                pass
        instructions = instructions.strip() or "請為本作品構建完整的世界觀設定、力量體系與時代背景"
        user_content = f"""{core_context}{assets_block}【本階段執行目標】
{instructions}

請根據上述作品核心基石與靈感羅盤，生成核心世界觀（theme、main_conflict、worldview、macro_outline）的 JSON 設定。
請緊扣本作品核心構想展開，充分發揮原案的核心能力設定與故事魅力。
"""
    else:
        user_content = f"""{assets_block}【核心世界觀生成任務與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：
{user_prompt}

請根據以上作品核心基石與創作要求，生成核心世界觀（theme、main_conflict、worldview、macro_outline）的 JSON 設定。
請緊扣本作品核心構想展開，充分發揮原案的核心能力設定與故事魅力。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_multi_act_structure_messages(worldview_core_json, user_prompt, novel_id=None, existing_assets_context=None):
    """基於核心世界觀，獨立生成多幕式起伏結構的提示詞"""
    from backend.prompts.prompt_main import MULTI_ACT_STRUCTURE_PROMPT, MULTI_ACT_STRUCTURE_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("multi_act_structure")
    c = parse_quantity_constraints(user_prompt)
    prompt_fmt = format_prompt_constraints(MULTI_ACT_STRUCTURE_PROMPT, c)
    guidelines_fmt = format_prompt_constraints(MULTI_ACT_STRUCTURE_GUIDELINES, c)
    system_prompt = f"{prompt_fmt}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Drama Structure Specialist / 多幕式結構師",
        "- 作品核心基石與已確立的核心世界觀 JSON。\n- 既有設定資產（若處於增量修訂模式，須嚴格保持連續性）。",
        "規劃 multi_act_structure，勾勒全書起伏、各幕危機遞進與核心轉折。",
        "輸出包含 multi_act_structure 的 JSON 資料。"
    )
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    assets_block = f"【已確立之既有設定資產（修訂時嚴格保持連續性避免衝突）】\n{existing_assets_context}\n\n" if existing_assets_context else ""
    user_content = f"""{core_context}【已確立之核心世界觀設定】
{worldview_core_json}

{assets_block}【本階段創作目標】
請參考上述世界觀設定與作品風格，為我們這部小說規劃完整生動的多幕式劇情起伏結構（multi_act_structure）。
- 幕次標題以中文數字依序編排，並結合該幕核心情節或主旨命名，展現典雅流暢的中文風格。
- 請直接輸出 multi_act_structure 的 JSON 資料。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_progressive_character_plan_messages(worldview_core_json, multi_act_json, user_prompt, novel_id=None, existing_assets_context=None):
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
        wave_count_rule = "建議規劃 18 波角色登場梯隊，與當前 18 幕結構緊密呼應。"
    elif act_count:
        wave_count_rule = f"建議規劃約 {act_count} 波角色登場梯隊，對齊主要幕次需求。"
    else:
        wave_count_rule = f"建議規劃 {c['min_waves']} 至 {c['max_waves']} 波角色登場梯隊。"
        
    prompt_fmt = format_prompt_constraints(PROGRESSIVE_CHARACTER_PLAN_PROMPT, c)
    guidelines_fmt = format_prompt_constraints(PROGRESSIVE_CHARACTER_PLAN_GUIDELINES, c)
    system_prompt = f"{prompt_fmt}\n\n{schema_snippet}\n\n{guidelines_fmt}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Character Progression Planner / 角色登場策略規劃師",
        "- 作品核心基石、已確立之核心世界觀與 multi_act_structure。\n- 既有設定資產（若處於增量修訂模式，須嚴格保持連續性）。",
        "規劃 progressive_character_plan，說明各波次角色功能定位與登場節奏。",
        "輸出包含 progressive_character_plan 的 JSON 資料。"
    )
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    assets_block = f"【已確立之既有設定資產（修訂時嚴格保持連續性避免衝突）】\n{existing_assets_context}\n\n" if existing_assets_context else ""
    user_content = f"""{core_context}【已確立之核心世界觀設定】
{worldview_core_json}

【已規劃之多幕劇情結構】
{multi_act_json}

{assets_block}【本階段創作目標】
請結合世界觀與各幕起伏，規劃人物群像的漸進登場策略（progressive_character_plan）。
- 波次標題以中文數字依序編排，並概括該批角色的功能定位或陣營特色，層次分明。
- 請直接輸出 progressive_character_plan 的 JSON 資料。
每波 content 建議點明：主要登場角色、其功能定位、與當前幕次的關係，以及對主角成長的推動作用。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


