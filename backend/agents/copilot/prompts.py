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

def simplify_plot_data_for_copilot(plot_text):
    if not plot_text or not isinstance(plot_text, str) or plot_text.startswith("尚無"):
        return plot_text
    try:
        data = json.loads(plot_text)
        if isinstance(data, dict):
            if "volumes" in data:
                vols = data["volumes"]
                simplified_vols = []
                for v in vols:
                    v_copy = dict(v)
                    if "chapters_outline" in v_copy:
                        if isinstance(v_copy["chapters_outline"], list):
                            v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                        else:
                            v_copy["chapters_outline"] = "尚未生成骨架"
                    simplified_vols.append(v_copy)
                return json.dumps({"volumes": simplified_vols}, ensure_ascii=False, indent=2)
            elif "chapters" in data:
                chapters = data["chapters"]
                simplified_chapters = []
                for ch in chapters:
                    if isinstance(ch, dict):
                        simplified_ch = {
                            "chapter_index": ch.get("chapter_index") or ch.get("chapter") or ch.get("index"),
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or "未命名章節",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or "（尚無摘要說明）"
                        }
                        simplified_chapters.append(simplified_ch)
                return json.dumps({"chapters": simplified_chapters}, ensure_ascii=False, indent=2)
        elif isinstance(data, list):
            if data and "volume_index" in data[0]:
                simplified_vols = []
                for v in data:
                    v_copy = dict(v)
                    if "chapters_outline" in v_copy:
                        if isinstance(v_copy["chapters_outline"], list):
                            v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                        else:
                            v_copy["chapters_outline"] = "尚未生成骨架"
                    simplified_vols.append(v_copy)
                return json.dumps(simplified_vols, ensure_ascii=False, indent=2)
            else:
                simplified_chapters = []
                for ch in data:
                    if isinstance(ch, dict):
                        simplified_ch = {
                            "chapter_index": ch.get("chapter_index") or ch.get("chapter") or ch.get("index"),
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or "未命名章節",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or "（尚無摘要說明）"
                        }
                        simplified_chapters.append(simplified_ch)
                return json.dumps(simplified_chapters, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to simplify plot data for copilot: {e}")
    return plot_text


def build_copilot_chat_messages(novel_id, worldview_text, characters_text, plot_text, history_context, user_message, validation_report=None, gold_rules_context=None):
    """Copilot 創意決策總監聊天提示詞"""
    if not validation_report:
        validation_report = "底層校驗一切正常。全階段架構完備。"
    
    from backend.services.diagnostics import diagnose_all_phases
    diags = diagnose_all_phases(novel_id)
    
    system_prompt = CO_PILOT_ORCHESTRATOR_PROMPT
    
    # Select task-relevant context first; length limits are only overflow guards.
    context_query = _context_query_text(user_message, plot_text, history_context)
    worldview_summary = select_worldview_context(worldview_text, "copilot", query_text=context_query)
    gold_rules_context = compact_context_text(gold_rules_context, MAX_GOLD_RULES_CONTEXT_LENGTH, "創作金律")
    
    characters_summary = build_relevant_character_context_text(characters_text, query_text=context_query)
    
    plot_summary = compact_context_text(simplify_plot_data_for_copilot(plot_text), MAX_DIRECTOR_PLOT_LENGTH, "大綱")
    gold_rules_block = f"\n【既有會議討論聖經 / 創作金律（若存在，需作為總監判斷參考）】\n{gold_rules_context}\n" if gold_rules_context else ""
    
    user_content = f"""【當前專案實際設定與大綱內容】
- 【世界觀主題與設定】：
{worldview_summary}

- 【角色 Bible 聖經（基本人設）】：
{characters_summary}

- 【全書篇卷與大綱（簡化版）】：
{plot_summary}

{gold_rules_block}
【目前系統診斷狀態】
- 世界觀：{diags["worldview"]}
- 角色 Bible：{diags["characters"]}
- 大綱概要：{diags["plot"]}
- 已完稿正文：{diags["written_chapters"]}

【系統底層結構完整性與邏輯校驗報告】
{validation_report}

【最近對話歷史】
{history_context}

【使用者最新輸入】
{user_message}

請以總監身份給出專業回覆意見，並在末尾推薦對應的 Flow 狀態 JSON 區塊。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
