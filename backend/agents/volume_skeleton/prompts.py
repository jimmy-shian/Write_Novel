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

def build_volume_skeleton_planner_messages(worldview_text, volume_index, current_vol, start_ch, end_ch, vol_chapter_count, surrounding_context, precalc_clues, user_prompt):
    """卷骨架大綱規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUME_SKELETON_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volume Skeleton Planner / 卷章節骨架規劃師",
        "- 經後端挑選的世界觀背景。\n- 指定卷的標題、概要、時間線、序列上下文、適用規則與完整章節範圍。\n- 相鄰卷/章節脈絡與 Python 預計算的逐章 allocated_tasks 表。",
        "一次生成本卷完整輕量章節骨架，並把預計算任務填入對應章節；不得自行切段或只輸出局部缺章。",
        "輸出 chapters_skeleton JSON；chapter_index 必須完整連續覆蓋指定整卷範圍。每章只寫短骨架，不得生成詳細大綱或正文。"
    )
    volume_context = {
        "volume_index": volume_index,
        "title": current_vol.get("title"),
        "summary": current_vol.get("summary"),
        "chapter_range": [start_ch, end_ch],
        "chapter_count": vol_chapter_count,
        "factions": current_vol.get("factions"),
        "time_timeline": current_vol.get("time_timeline"),
        "sequence_context": current_vol.get("sequence_context"),
        "applicable_rules": current_vol.get("applicable_rules"),
    }
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務：整卷一次生成】
{json.dumps(volume_context, ensure_ascii=False, indent=2)}

請務必一次輸出第 {start_ch} 章至第 {end_ch} 章的完整「輕量章節骨架」（共 {vol_chapter_count} 章）。
不得切成多段，不得只輸出局部章節，不得要求總監補「本卷章節範圍」或「allocated_tasks」：這些資料已在本訊息中完整提供。
輸出完整性優先於細節量：每章請短，不要詳細。

{surrounding_context}
{precalc_clues}

【allocated_tasks 硬性填寫規則】
- 你不得自行挑選、推測、複製或新增任何伏筆 Seed / turning point 到未指定章節。
- 每一章都必須依「本卷逐章伏筆/轉折硬性操作表」填寫 allocated_tasks。
- 表中空陣列的章節必須輸出：foreshadowing_plants: [], foreshadowing_payoffs: [], turning_points: []。
- 若同一 Seed 看似同時需要埋設與回收，視為錯誤；請以章節清單中的單一操作為準。
- 若某章有 plant/payoff/turning point，該任務不能只放在 allocated_tasks；chapter_summary 或 events[0].content 必須用短句點出其劇情落點。

【每章輕量輸出格式限制】
- 不要寫正文、對白、心理描寫、詳細動作、感官描述、完整場景調度。
- 每章只需要點出：本章承接/推進、任務落點、時間、地點、活躍角色、相關勢力。
- events 僅 1 個核心事件物件；content 用「行動 -> 結果」短句，35 字內。
- chapter_summary 35-70 字；cliffhanger 30 字內；scene_setting/time_setting 都用短語。
- characters_active 只列本章真正活躍角色，通常 1-4 名。
- 若某章牽涉勢力，請放在 scene_setting、events.content 或 chapter_summary 的短句中；不要另寫長篇勢力說明。

【單章輸出長度範例（只示意格式，不可照抄內容）】
{{
  "chapter_index": {start_ch},
  "chapter_title": "月台異訊",
  "chapter_summary": "主角追查末班車異常，首次接觸乘客手冊線索，將危機推向車廂深處。",
  "time_setting": "深夜末班前",
  "scene_setting": "舊站月台",
  "events": [{{"scene_index": 1, "location": "舊站月台", "characters": ["主角"], "content": "追查異訊 -> 取得手冊線索"}}],
  "characters_active": ["主角"],
  "emotional_tone": "懸疑",
  "cliffhanger": "車門在無人處自行開啟。",
  "allocated_tasks": {{"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}}
}}

【勢力與角色一致性規則】
- 勢力/組織的定義、立場、利益、制度背景以【世界觀背景】中的 factions / 世界觀設定為準；本卷 factions 只是本卷活躍勢力子集，不得重新發明或改寫勢力設定。
- 若章節需要使用既有命名角色，characters_active 必須使用既有角色名冊中的名稱。
- 若劇情確實需要新增命名角色，可以在骨架中提出，但總監審核時必須先補角色卡再進入正文；不得把缺角色卡的命名角色當作已完備角色使用。

【使用者額外提示詞 (Prompt)】
{user_prompt or "請為本卷生成完整、連貫、短句化的輕量章節骨架。"}

請生成符合 JSON 結構的 chapters_skeleton 清單。輸出章數必須等於 {vol_chapter_count}，chapter_index 必須從 {start_ch} 到 {end_ch} 連續且不可缺漏。不要因追求細節導致輸出中斷。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volume_skeleton_completion_messages(
    worldview_text, volume_index, current_vol, start_ch, end_ch, batch_count,
    surrounding_context, precalc_clues, user_prompt, prior_segment_json
):
    """
    卷骨架「分段補全」提示詞拼接（completion 模式）。
    把已生成的前段章節成果（prior_segment_json 字串）放在 messages 中作為
    「已完成段落」，要求 LLM 只接續輸出剩餘章節 (start_ch ~ end_ch) 的骨架，
    銜接前段已有標題、情節、allocated_tasks，避免前後斷層。

    messages 結構刻意在最後放置一條 role=assistant 的「前段成果節錄」前綴，
    讓模型以續寫方式產出後半，達成真正的 completion 補全。
    """
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUME_SKELETON_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volume Skeleton Completion / 卷骨架補全師",
        "- 經後端挑選的世界觀背景。\n- 指定卷的標題、概要、已完成前段章節與本次補全範圍。\n- Python 預計算的 allocated_tasks。",
        "只接續前段，補全本次指定章節範圍；不得重寫已完成章節。",
        "輸出只包含補全範圍的 chapters_skeleton 元素；必須延續前段脈絡並保持 JSON 可解析。"
    )

    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務 — 分段補全 (Completion)】
- 當前篇卷序號：第 {volume_index} 卷
- 篇卷標題：{current_vol['title']}
- 篇卷概要：{current_vol['summary']}
- 已完成前段：第 {start_ch - 1} 章及之前（請勿重寫此前段章節）
- 本次需補全章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {batch_count} 章）
請務必只輸出此補全範圍內的章節骨架；不得輸出範圍外章節，不得重寫前段已存在章節。

{surrounding_context}
{precalc_clues}

【前段已生成之章節骨架（務必延續其標題命名風格、情節脈絡、伏筆分配）】
{prior_segment_json}

以下為本次需補全章節的 allocated_tasks 硬性填寫規則：
- 你不得自行挑選、推測、複製或新增任何伏筆 Seed / turning point 到未指定章節。
- 只有上方清單明確列出的章節，才可在 allocated_tasks 對應陣列填入該任務。
- 未列出任務的章節必須輸出：foreshadowing_plants: [], foreshadowing_payoffs: [], turning_points: []。
- 補全章節須與前段情節自然銜接：延續前段 cliffhanger 的解決、角色行為因果、時間線連貫。

【使用者額外提示詞 (Prompt)】
{user_prompt or "請接續前段內容，為本卷剩餘章節補全骨架大綱。"}

請以 completion（續寫）方式，只輸出第 {start_ch} 章至第 {end_ch} 章的 chapters_skeleton JSON 陣列。輸出章數必須等於 {batch_count}，chapter_index 必須連續且不可缺漏。
"""
    # 為促成真正的 completion，把前段成果作為 assistant 前綴（role=assistant），
    # 讓模型以「自己先前已開始產出此 JSON」的續寫方式補完剩餘章節。
    # 注意：以下字串刻意不以 f-string 撰寫，避免 JSON 花括號被當成 f-string 表達式。
    assistant_intro = (
        "以下是第 " + str(volume_index) + " 卷前段已生成的章節骨架（請勿重複輸出，僅作為脈絡）：\n"
        "```json\n" + prior_segment_json + "\n```\n\n"
        "我現在接續輸出第 " + str(start_ch) + " 章至第 " + str(end_ch) + " 章的 chapters_skeleton：\n"
        "```json\n"
        '{"volume_index": ' + str(volume_index) + ', "chapters_skeleton": ['
    )
    assistant_follow = (
        "請接著上面已開始的 JSON 直接輸出 chapters_skeleton 陣列中的章節元素"
        "（第 " + str(start_ch) + " ~ " + str(end_ch) + " 章），"
        "然後以 ]}} 結束。只輸出尚未補完的章節，不要重複前段章節。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_intro},
        {"role": "user", "content": assistant_follow},
    ]
    return messages

def build_incremental_skeleton_messages(worldview_text, volume_index, existing_skeleton, user_hint):
    """卷骨架增量修正提示詞拼接"""
    patch_schema = {
        "volume_index": volume_index,
        "chapters_skeleton": [
            {
                "chapter_index": "必填：要修改的絕對章節序號",
                "chapter_title": "可省略未修改欄位",
                "chapter_summary": "可省略未修改欄位",
                "time_setting": "可省略未修改欄位",
                "scene_setting": "可省略未修改欄位",
                "events": "若修改事件，回傳完整的新 events 陣列",
                "characters_active": "可省略未修改欄位",
                "emotional_tone": "可省略未修改欄位",
                "cliffhanger": "可省略未修改欄位",
                "allocated_tasks": "除非明確要求修改伏筆/轉折，否則省略"
            }
        ]
    }
    schema_snippet = format_json_schema_prompt(patch_schema, label="this incremental skeleton patch schema")
    system_prompt = VOLUME_SKELETON_PROMPT_PLUS.format(hints=user_hint) + f"\n\n{schema_snippet}"
    system_prompt += build_agent_context_contract(
        "Incremental Skeleton / 卷骨架增量修正師",
        "- 世界觀摘要。\n- 指定卷索引。\n- 現有該卷章節骨架。\n- 總監或使用者的局部修改要求。",
        "只修補指定卷中被要求修改或補全的章節。",
        "輸出 chapters_skeleton patch JSON；每個回傳章節必須含 chapter_index。未修改章節不要回傳。"
    )
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前篇卷】
- 卷索引: {volume_index}

【現有骨架大綱】
{existing_skeleton}

【修改要求】
{user_hint}

請僅針對第 {volume_index} 卷的章節大綱骨架進行修改，並回傳格式完全合法的 chapters_skeleton JSON。
只回傳被修改或新增補全的章節物件；每個物件必須包含 chapter_index。未修改章節不要回傳，未修改欄位請省略，後端會按 chapter_index 深度合併。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

