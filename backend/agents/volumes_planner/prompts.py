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

def build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx, novel_id=None, batch_info=None, characters_summary=None, foreshadowing_summary=None):
    """篇卷規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("volumes")
    from backend.agents.story_architect.prompts import parse_quantity_constraints, format_prompt_constraints
    combined_prompt = f"{user_prompt or ''}\n{hint or ''}"
    c = parse_quantity_constraints(combined_prompt)
    guidelines_fmt = format_prompt_constraints(VOLUMES_PLANNER_GUIDELINES, c)
    system_prompt = f"{VOLUMES_PLANNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{guidelines_fmt}\n"
    system_prompt += build_agent_context_contract(
        "Volumes Planner / 篇卷規劃師",
        "- 經後端挑選的世界觀、macro_outline、多幕結構與作品核心基石。\n- 核心角色名冊（定位、核心慾望與秘密）、全書長程伏筆網絡與關鍵重大轉折點。\n- patch 模式會提供目標卷前後卷概要與總監提示。\n- 批次生成模式會提供已確立篇卷的大綱進展。",
        "規劃全書分卷結構或分批精細推演指定篇卷，讓每卷承接世界觀主軸、作品核心能力/衝突、既有角色弧線與預定收束的伏筆轉折。",
        "輸出 volumes JSON；不要生成章節骨架、正文或角色卡。patch 模式只回傳指定卷，批次模式只回傳當批指定的篇卷。"
    )
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    chars_block = f"【已確立角色人物誌（供各卷矛盾焦點與角色弧線對齊）】\n{characters_summary}\n\n" if characters_summary else ""
    foreshadow_block = f"【全書伏筆網絡與關鍵轉折點（供各卷高潮起伏與懸念收束對齊）】\n{foreshadowing_summary}\n\n" if foreshadowing_summary else ""

    if mode == "generate":
        if batch_info:
            start_idx = batch_info.get("start_vol_idx", 1)
            end_idx = batch_info.get("end_vol_idx", start_idx + 2)
            batch_count = batch_info.get("batch_count", end_idx - start_idx + 1)
            total_target = batch_info.get("total_target", 12)
            prev_vols = batch_info.get("previous_volumes", [])

            prev_context = ""
            if prev_vols:
                prev_summary_lines = []
                for pv in prev_vols:
                    v_no = pv.get("volume_index")
                    v_title = pv.get("title", "")
                    v_sum = pv.get("summary", "")
                    v_archetype = pv.get("conflict_archetype", "")
                    prev_summary_lines.append(f"- 第 {v_no} 卷《{v_title}》（衝突原型：{v_archetype}）：{v_sum}")
                prev_context = "【前續已規劃篇卷脈絡】\n" + "\n".join(prev_summary_lines) + "\n\n"

            user_content = f"""{core_context}【世界觀背景】
{worldview_text}

{chars_block}{foreshadow_block}{prev_context}【使用者要求】
{user_prompt or f"請專注且細緻規劃第 {start_idx} 卷至第 {end_idx} 卷的大綱骨架與衝突起伏。"}

【本次生成任務：精細篇卷批次規劃】
全書總規劃目標為 {total_target} 卷。本次請專注規劃 **第 {start_idx} 卷 至 第 {end_idx} 卷**（共 {batch_count} 卷）。
請聚焦本批次篇卷的衝突激化、情節質變、因果推進與人物代價，產出高品質的篇卷架構。

【篇卷規劃指引】
1. 篇卷結構與篇幅：
   - 本次回傳的 volumes 陣列中，請規劃第 {start_idx} 卷到第 {end_idx} 卷（共 {batch_count} 卷），volume_index 依序為 {start_idx} 至 {end_idx}。
   - 為維持長篇小說的宏大體量，每卷章節數（chapter_count）請規劃在 40 至 50 章之間。
2. 承前啟後與情節質變：
   - 緊密承接前續篇卷的局勢與未解懸念，情節層層遞進，展現更具新意的情節焦點與推進方式。
3. 角色弧線與矛盾焦點：
   - 各卷的主導衝突原型與核心事件，應與上述已確立角色的人設定位、核心追求（want）及致命秘密緊密綁定，推動角色心理狀態的階梯式轉變。
4. 伏筆收束與轉折爆發：
   - 若該卷涵蓋的章節範圍內對應了上述伏筆種子（預期回收章）或重大關鍵轉折點，請在該卷的 summary 與高潮事件中落實該伏筆的收束或重大轉折的爆發。
5. 篇卷衝突原型：
   - 每卷明確指定其主導衝突原型，相鄰篇卷展現不同層次的矛盾衝突。
6. 反套路思考：
   - 避免落入模板化的劇情套路，引導故事走向未知的深層博弈。
7. 卷末懸念多樣性：
   - 真相揭露、盟友考驗、大局劇變、主動宣戰等懸念手法靈活搭配。
"""
        else:
            user_content = f"""{core_context}【世界觀背景】
{worldview_text}

{chars_block}{foreshadow_block}【使用者大綱/要求】
{user_prompt or "請根據作品核心基石與完整世界觀，規劃全書的卷數、每卷標題、概要與章節數量設定。"}

請為本作品生成符合結構的篇卷 JSON 清單。
各卷之核心矛盾、主線推進與高潮事件緊扣作品核心基石。

【篇卷規劃指引】
1. 篇卷數量與長篇規模：
   - 規劃 10 至 20 卷（推薦 10 至 12 卷），覆蓋完整長篇宏觀史詩格局。每卷依序由 volume_index: 1 遞增排列至總卷數。
   - 每卷章節數（chapter_count）請規劃在 40 至 50 章之間，支撐百萬字篇幅。
2. 角色弧線與矛盾焦點：
   - 各卷的主導衝突原型應與核心角色的人設定位與核心追求（want）緊密對齊。
3. 伏筆收束與轉折爆發：
   - 各卷的轉折高潮應承接伏筆網絡中的關鍵埋設與收束。
4. 篇卷衝突原型：
   - 每卷明確指定其主導衝突原型，相鄰篇卷展現不同層次的矛盾衝突。
5. 反套路思考：
   - 避免落入常規套路，引導故事走向深度探索。
6. 卷末懸念輪替：
   - 真相揭露、局勢反轉、新強敵登場等手法靈活呈現。
"""
    else:  # patch/add specific idx
        v_idx = target_vol_idx or 1
        surrounding_context = ""
        pre_vol = next((v for v in existing_vols if v["volume_index"] == v_idx - 1), None)
        next_vol = next((v for v in existing_vols if v["volume_index"] == v_idx + 1), None)
        
        if pre_vol:
            surrounding_context += f"\n【前 1 卷 (卷 {v_idx - 1}) 大綱與概要】\n標題：{pre_vol['title']}\n概要：{pre_vol['summary']}\n"
        if next_vol:
            surrounding_context += f"\n【後 1 卷 (卷 {v_idx + 1}) 大綱與概要】\n標題：{next_vol['title']}\n概要：{next_vol['summary']}\n"
            
        user_content = f"""{core_context}【世界觀背景】
{worldview_text}
{chars_block}{foreshadow_block}{surrounding_context}
【修補指定卷目標】
- 指定修補生成第 {v_idx} 卷

【總監批判與修改指示 (Hint)】
{hint or "請修正該卷的起承轉合與情節重心。"}

【一般提示詞 (Prompt)】
{user_prompt or f"請專注且只生成/修補第 {v_idx} 卷的大綱骨架，不要修改其他無關卷。"}

請僅針對第 {v_idx} 卷進行精細化生成/修補，並回傳格式完全合法的 volumes JSON，列表中應僅包含第 {v_idx} 卷的新/修改內容。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
