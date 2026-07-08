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

def build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index):
    """角色設計師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("character")
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{CHARACTER_DESIGNER_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Character Designer / 角色設計師",
        "- 經後端挑選的世界觀背景，必須包含或摘要呈現 factions / 勢力設定與 progressive_character_plan / 角色登場策略。\n- generate 模式：通常只有世界觀，沒有現有角色；這是建立角色聖經與關係網的第一次定稿。\n- expand/modify 模式：會提供現有角色聖經與總監提示；modify 可能提供被修改角色完整內容。",
        "根據可見世界觀設計或修補角色 Bible。角色要服務於世界觀衝突、勢力格局、登場策略與作者需求；不得用空世界觀硬編角色。",
        "輸出完整合法的 characters JSON。generate 必須建立核心角色表、勢力歸屬、角色之間的關聯與可供卷/骨架/writer 使用的生成設定；expand/modify 應保留既有角色並補充或修正，避免刪除無關角色。"
    )
    
    if mode == "generate":
        user_content = f"""【世界觀背景】
{worldview_text}

【使用者要求】
{user_prompt or "請根據世界觀，為我們設計核心角色與配角群像。"}

請為本作品生成符合結構的角色 Bible JSON 設定。
硬性要求：
1. 必須讀取並落實世界觀中的 `factions` / 勢力設定，為主要角色標明所屬勢力、利益立場、與其他勢力的衝突或合作關係。
2. 必須讀取並落實 `progressive_character_plan` / 角色登場策略，讓角色功能、首次登場階段與群像節奏對齊。
3. 必須建立可供後續 volumes、volume_skeleton、writer 使用的角色關係資料，例如 relationships / relationship_matrix / role / faction / entry_phase 等 schema 允許欄位。
4. 不要只列人物簡介；每位核心角色都要有可寫作的動機、弱點、成長弧線、聲音/行為特徵與關係張力。
"""
    elif mode == "expand":
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}

【總監批判與擴增提示 (Hint)】
{hint or "請擴增有深度的新角色。"}

【一般提示詞 (Prompt)】
{user_prompt or "請在現有角色基礎上進行增量擴展，追加新角色。"}

請根據總監提示，追加新角色。
[極重要要求]：
請只生成本次需要「新增/追加」的角色清單，並回傳格式完全合法的 characters JSON（例如 `{{ "characters": [...] }}`），列表中應「僅」包含本次新增的角色，千萬不要重寫、輸出或複製任何未修改的既有角色。
擴增角色時仍必須遵守世界觀勢力設定；新角色的 faction、登場功能與關係網必須能回接既有角色聖經，不能只新增孤立人物。
"""
    else:  # modify
        target_char_content = ""
        if target_char_index is not None:
            try:
                parsed_chars = json.loads(existing_chars_json)
                chars_list = parsed_chars.get("characters", [])
                norm_idx = db.normalize_char_index(int(target_char_index), len(chars_list), source='character_designer')
                target_char_content = f"\n【被修改角色的完整內容 (Index {norm_idx})】\n{json.dumps(chars_list[norm_idx], ensure_ascii=False, indent=2)}"
            except IndexError:
                pass
                
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}
{target_char_content}

【修改指示 (Hint)】
{hint or "請修改角色設定。"}

【一般提示詞 (Prompt)】
{user_prompt or "請對指定角色進行內容調整。"}

請將以上修改與該角色的完整內容融會貫通。
[極重要要求]：
請只生成「受修改後」的角色清單，並回傳格式完全合法的 characters JSON（例如 `{{ "characters": [...] }}`），列表中應「僅」包含本次被修改的角色的全新設定，千萬不要複製或重寫其他無關、未修改的角色。
修改時保留角色既有關係網與勢力一致性；若總監要求補關係或勢力，請同步修正 relationships / relationship_matrix 等相關欄位。
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_missing_character_designer_messages(worldview_summary, existing_chars_json, new_char_name, chapter_outline):
    """
    為首次登場的缺失角色生成獨立設計提示詞訊息列表。
    此函數負責將角色設計 system prompt 與 user prompt 組裝為 LLM messages，
    按照嚴格 JSON Schema 要求生成新角色卡。
    """
    schema = {
        "name": "",
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

    # 僅提取現有角色的名稱與角色定位，節省 Token 並防範衝突
    existing_names_str = "暫無角色"
    if existing_chars_json:
        try:
            names = extract_character_names_list(existing_chars_json)
            if names:
                existing_names_str = ", ".join(names)
        except Exception:
            pass

    schema_snippet = format_json_schema_prompt(schema, label="this missing character schema")
    system_prompt = f"""你是一位頂尖的角色設計大師（Character Designer）。
請根據世界觀背景與新角色首次登場的章節骨架，為新登場的角色【{new_char_name}】設計一個具備深度與心理層次的角色卡設定。

⚠️【剛性約束項目】：
1. 輸出必須符合以下角色 schema：
{schema_snippet}
2. name 欄位必須是角色的具體姓名【{new_char_name}】，絕對禁止填寫無關名稱。
3. 角色的人設、動機 (motivation)、致命缺陷 (fatal_flaw)、發聲風格 (speech_style) 必須與章節大綱的情境完全契合，且不可與現有的其他角色衝突。
"""
    system_prompt += build_agent_context_contract(
        "Missing Character Designer / 缺失角色補卡師",
        "- 世界觀背景大綱。\n- 既有角色名稱與定位清單。\n- 新角色首次登場的章節大綱。",
        "只為指定新角色生成一張可併入角色庫的角色卡，服務於其首次登場章節。",
        "輸出單一角色 JSON；name 必須等於指定新角色名稱，不得順手新增其他角色。"
    )
    user_content = f"""【世界觀背景大綱】
{worldview_summary}

【現有已登場角色清單 (避免人設重複或名稱衝突)】
{existing_names_str}

【新角色【{new_char_name}】登場的第 {chapter_outline.get('chapter_index')} 章大綱】
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

請為新角色【{new_char_name}】生成高品質的完整角色 JSON 卡片。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

