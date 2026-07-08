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
from backend.prompts.json_output import format_json_schema_prompt

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

def build_foreshadowing_messages(worldview_text, characters_json, user_prompt=None, target_field=None):
    """伏筆與轉折編織師提示詞拼接

    target_field: None = 兩者都生成（全量，每類至少50條）
                  "foreshadowing_seeds"   = 只生成伏筆種子（至少50條）
                  "key_turning_points"    = 只生成關鍵轉折點（至少50條）
    分批模式可顯著減少單次 JSON 長度，降低解析錯誤機率。
    """
    from backend.schemas.agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json

    if target_field == "foreshadowing_seeds":
        schema = {"foreshadowing_seeds": FORESHADOWING_OUTPUT_SCHEMA["foreshadowing_seeds"]}
        target_instruction = (
            "【本次只生成 foreshadowing_seeds】\n"
            "1. 最外層 JSON 只能有一個頂層鍵：`foreshadowing_seeds`（陣列）。\n"
            "2. 必須至少 50 個；少於此數量即為失敗輸出。\n"
            "3. 每個項目只能使用：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`。\n"
            "4. `id` 必須是整數，從 1 開始連續編號。\n"
            "5. 禁止輸出 key_turning_points 或任何其他頂層鍵。\n"
            "6. 每個 seed 必須具備可埋設的具體載體、表層偽裝與未來回收方向；不得用同義改寫湊數。"
        )
    elif target_field == "key_turning_points":
        schema = {"key_turning_points": FORESHADOWING_OUTPUT_SCHEMA["key_turning_points"]}
        target_instruction = (
            "【本次只生成 key_turning_points】\n"
            "1. 最外層 JSON 只能有一個頂層鍵：`key_turning_points`（陣列）。\n"
            "2. 必須至少 50 個；少於此數量即為失敗輸出。\n"
            "3. 每個項目只能使用：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。\n"
            "4. `id` 必須是整數，從 1 開始連續編號。\n"
            "5. 禁止輸出 foreshadowing_seeds 或任何其他頂層鍵。\n"
            "6. 每個 turning point 必須能造成局勢、關係或角色弧線的實質改變；不得用普通事件湊數。"
        )
    else:
        schema = FORESHADOWING_OUTPUT_SCHEMA
        target_instruction = (
            "【不可違反的輸出契約】\n"
            "1. 最外層 JSON 必須只有一個物件，且只能包含兩個頂層鍵：`foreshadowing_seeds` 與 `key_turning_points`。\n"
            "2. `foreshadowing_seeds` 必須是陣列，至少 50 個；`key_turning_points` 必須是陣列，至少 50 個；少於此數量即為失敗輸出。\n"
            "3. 每個 `foreshadowing_seeds` 項目只能使用這些欄位：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`。\n"
            "4. 每個 `key_turning_points` 項目只能使用這些欄位：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。\n"
            "5. `id` 必須是 JSON number / integer，從 1 開始連續編號；禁止填 `FS001`、`Seed-001`、`TP001`、`Turn-001`、中文標號或任何文字。\n"
            "6. 所有文字內容只能填入名稱、描述、提示、影響、代價、主題連結等文字欄位；禁止把情節文字、標號規則或說明塞入 `id`、`index`、`number` 類欄位。\n"
            "7. 禁止輸出 `volume_1`、`volume_2`、`act_1` 等作為頂層鍵；卷/幕/章節只能寫入文字欄位的內容裡。\n"
            "8. 此階段只生成全書伏筆與關鍵轉折藍圖，不需要章節正文、卷骨架，也不可要求 writer/editor 先執行。\n"
            "9. 每個 seed 必須具備可埋設的具體載體、表層偽裝與未來回收方向；不得用同義改寫湊數。\n"
            "10. 每個 turning point 必須能造成局勢、關係或角色弧線的實質改變；不得用普通事件湊數。"
        )

    schema_snippet = (
        format_json_schema_prompt(schema, label="this foreshadowing schema from backend/schemas/agent_json.py")
        + "\n"
        + agent_json.format_criteria_for_prompt("foreshadowing")
    )
    system_prompt = f"{FORESHADOWING_ORCHESTRATOR_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{target_instruction}\n\n{FORESHADOWING_ORCHESTRATOR_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Foreshadowing Orchestrator / 伏筆與轉折編織師",
        "- 經後端挑選的世界觀背景。\n- 角色 Bible 或角色摘要。\n- 總監可能透過 [BATCH: foreshadowing_seeds] 或 [BATCH: key_turning_points] 指定本批目標。",
        "只設計全書伏筆種子與關鍵轉折藍圖，供後續篇卷和章節分配使用。",
        "嚴格遵守本批 target_field 的頂層鍵；分批時不得混入另一類資料，不得輸出卷別鍵、章節正文或解釋文字。"
    )

    default_task = "請根據世界設定與角色背景，設計豐富的伏筆種子與關鍵轉折點。"
    user_content = (
        "【世界觀背景】\n" + worldview_text + "\n\n"
        "【角色 Bible 與人設】\n" + characters_json + "\n\n"
        "【額外設計指令】\n" + (user_prompt or default_task) + "\n\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
