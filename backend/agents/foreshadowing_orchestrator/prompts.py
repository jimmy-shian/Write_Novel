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

def build_foreshadowing_messages(worldview_text, characters_json, user_prompt=None, target_field=None, novel_id=None, batch_size=15, existing_items=None, start_id=1, established_seeds=None, volumes_structure=None):
    """伏筆與轉折編織師提示詞拼接 (支援 15 條/批 自動分批累加，整合篇卷結構對齊)"""
    from backend.schemas.agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json

    volumes_align_rule = ""
    if volumes_structure:
        volumes_align_rule = (
            "7. 篇卷結構對齊要求：請參照下方提供的【全書篇卷架構與章節區間】，將伏筆的 `payoff_deadline_chapter` 與轉折點章節精準錨定在相應卷的發展或卷末高潮區間，使伏筆回收與篇卷節奏完美契合。\n"
        )

    if target_field == "foreshadowing_seeds":
        schema = {"foreshadowing_seeds": FORESHADOWING_OUTPUT_SCHEMA["foreshadowing_seeds"]}
        existing_names = [
            f"- {item.get('name')}" for item in (existing_items or [])
            if isinstance(item, dict) and item.get('name')
        ]
        existing_section = ""
        if existing_names:
            existing_section = (
                f"\n【前續批次已建立之伏筆種子（共 {len(existing_names)} 個，本批切勿重複，請承前啟後設計全新維度）】：\n"
                + "\n".join(existing_names[:30])
                + ("\n..." if len(existing_names) > 30 else "")
                + "\n"
            )
        target_instruction = (
            f"【本次批次生成 foreshadowing_seeds】\n"
            f"1. 最外層 JSON 只能有一個頂層鍵：`foreshadowing_seeds`（陣列）。\n"
            f"2. 本次請生成高品質、深刻且具體可落地的 {batch_size} 個全新伏筆種子。\n"
            f"3. 每個項目欄位：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`, `expected_payoff_window`, `payoff_deadline_chapter`, `integration_group`。\n"
            f"4. `id` 必須是整數，從 {start_id} 開始連續編號。\n"
            f"5. 禁止輸出 key_turning_points 或任何其他頂層鍵。\n"
            f"6. 每個 seed 必須具備可埋設的具體載體、表層偽裝與未來回收方向；設定清晰的 `payoff_deadline_chapter`（每20-30章具備回收點），並支援以 `integration_group` 將關聯懸念合流歸納；不得用同義改寫湊數。\n"
            + volumes_align_rule
            + existing_section
        )
    elif target_field == "key_turning_points":
        schema = {"key_turning_points": FORESHADOWING_OUTPUT_SCHEMA["key_turning_points"]}
        existing_names = [
            f"- {item.get('turning_point_name') or item.get('name')}" for item in (existing_items or [])
            if isinstance(item, dict) and (item.get('turning_point_name') or item.get('name'))
        ]
        existing_section = ""
        if existing_names:
            existing_section = (
                f"\n【前續批次已建立之關鍵轉折點（共 {len(existing_names)} 個，本批切勿重複，請承前啟後規劃全新波折）】：\n"
                + "\n".join(existing_names[:30])
                + ("\n..." if len(existing_names) > 30 else "")
                + "\n"
            )

        seeds_summary_section = ""
        if established_seeds and isinstance(established_seeds, list):
            seed_lines = []
            for s in established_seeds[:30]:
                if isinstance(s, dict):
                    s_id = s.get("id") or ""
                    s_name = s.get("name") or ""
                    s_payoff = s.get("payoff_hint") or s.get("description") or ""
                    s_chars = ", ".join(s.get("related_characters") or [])
                    seed_lines.append(f"- [伏筆 #{s_id}] {s_name}（關聯角色: {s_chars}）：{s_payoff[:75]}")
            if seed_lines:
                seeds_summary_section = (
                    f"\n【已確立之全書核心伏筆種子網絡（供本次轉折點呼應、觸發或引爆）】：\n"
                    + "\n".join(seed_lines)
                    + ("\n..." if len(established_seeds) > 30 else "")
                    + "\n"
                )

        target_instruction = (
            f"【本次批次生成 key_turning_points】\n"
            f"1. 請組織為包含 `key_turning_points` 陣列的 JSON 資料。\n"
            f"2. 本次請規劃具備高戲劇張力、重大局勢變更的 {batch_size} 個全新關鍵轉折點。\n"
            f"3. 每個項目欄位：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。\n"
            f"4. `id` 從 {start_id} 開始依序遞增編號。\n"
            f"5. 每個轉折點著重為局勢、人際關係或角色弧線帶來實質位移。\n"
            f"6. 伏筆與轉折組合聯動要求：關鍵轉折點主動與上述【已確立之全書核心伏筆種子】產生呼應，在情節推演中指明觸發、引爆或收束了哪一條伏筆懸念，形成環環相扣的因果鏈條。\n"
            + volumes_align_rule
            + existing_section
            + seeds_summary_section
        )
    else:
        schema = FORESHADOWING_OUTPUT_SCHEMA
        target_instruction = (
            f"【本次批次生成全書伏筆與關鍵轉折藍圖】\n"
            f"1. 請組織為包含 `foreshadowing_seeds` 與 `key_turning_points` 的 JSON 資料。\n"
            f"2. 本批生成：`foreshadowing_seeds` 陣列（{batch_size} 個）與 `key_turning_points` 陣列（{batch_size} 個）。\n"
            f"3. 每個 `foreshadowing_seeds` 項目欄位：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`, `expected_payoff_window`, `payoff_deadline_chapter`, `integration_group`。\n"
            f"4. 每個 `key_turning_points` 項目欄位：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。\n"
            f"5. `id` 從 1 開始依序連續編號。\n"
            f"6. 種子與轉折注重深刻具體，合理分配回收章節與懸念合流組。\n"
            + volumes_align_rule
        )

    schema_snippet = (
        format_json_schema_prompt(schema, label="foreshadowing")
        + "\n"
        + agent_json.format_criteria_for_prompt("foreshadowing")
    )
    system_prompt = f"{FORESHADOWING_ORCHESTRATOR_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{target_instruction}\n\n{FORESHADOWING_ORCHESTRATOR_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Foreshadowing Orchestrator / 伏筆與轉折編織師",
        "- 經挑選的世界觀背景與作品核心基石。\n- 角色群像背景與登場策略。\n- 全書篇卷架構與各卷章節區間（若有，供精準對齊伏筆回收 deadline 與轉折爆發點）。\n- 本批生成目標與前續批次摘要。",
        "設計全書伏筆種子與關鍵轉折藍圖，為後續篇卷和章節骨架提供情節推動力；若有篇卷架構，確保伏筆回收截止點（payoff_deadline_chapter）與關鍵轉折點精確錨定在各卷之章節區間與卷末高潮。",
        "輸出對應批次的伏筆或轉折 JSON 資料。"
    )

    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    default_task = "請根據作品核心基石、世界設定與角色背景，設計豐富的伏筆種子與關鍵轉折點。"
    volumes_block = f"【全書篇卷架構與章節區間（供精準對齊伏筆回收視窗與轉折章節）】\n{volumes_structure}\n\n" if volumes_structure else ""
    user_content = (
        core_context
        + "【世界觀背景】\n" + worldview_text + "\n\n"
        + "【角色 Bible 與人設】\n" + characters_json + "\n\n"
        + volumes_block
        + "【額外設計指令】\n" + (user_prompt or default_task) + "\n\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
