# -*- coding: utf-8 -*-
"""
Prompt Builder for Editor & Reviewer
負責組裝 Editor 兩階段管線提示詞：
1. Reviewer（品質評審）：輸出結構化品質診斷報告 JSON（POV 違規、知識洩漏、設定傾倒、對話瑕疵、AI 模板詞）。
2. Targeted Rewriter（定向精修）：依據診斷報告進行外科手術式局部修補。
"""

import json
from typing import Any, Dict, List, Optional

from backend.prompts.common.context import (
    CONTEXT_REQUEST_RULE,
    build_agent_context_contract,
)
from backend.prompts.prompt_detail_modifier import (
    EDITOR_PROMPT,
    REVIEWER_PROMPT,
    TARGETED_REWRITER_PROMPT,
)


def build_reviewer_agent_messages(
    chapter_index: int,
    original_prose: str,
    scene_contract_or_outline: Optional[Dict[str, Any]] = None,
    editor_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """組裝 Reviewer 品質評審提示詞"""
    system_prompt = REVIEWER_PROMPT + "\n" + CONTEXT_REQUEST_RULE
    system_prompt += build_agent_context_contract(
        "Reviewer / 小說品質評審",
        "- 待評審章節的原始正文。\n- 當前章節 Scene Contract、大綱與角色知情邊界。\n- 伏筆任務與連續性記憶。",
        "嚴格診斷正文中的 POV 越界、知情洩漏、設定傾倒、對白生硬與 AI 套路詞，輸出標準診斷 JSON 報告。",
        "必須且只能輸出合法 JSON 物件，嚴禁包含額外對話或散文。"
    )

    contract_text = ""
    if scene_contract_or_outline:
        contract_text = f"【本章場景契約與大綱約束】\n{json.dumps(scene_contract_or_outline, ensure_ascii=False, indent=2)}\n\n"

    user_content = f"""{contract_text}【背景與連續性上下文】
{editor_context or "（無額外上下文）"}

【待評審的第 {chapter_index} 章正文】
{original_prose}

請按照審查面向進行深度評審，並直接回傳合法的診斷 JSON 報告：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


def build_targeted_rewriter_messages(
    chapter_index: int,
    original_prose: str,
    diagnostic_report: Dict[str, Any],
    edit_instructions: Optional[str] = None,
    editor_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """組裝 Targeted Rewriter 定向精修提示詞"""
    system_prompt = TARGETED_REWRITER_PROMPT + "\n" + CONTEXT_REQUEST_RULE
    system_prompt += build_agent_context_contract(
        "Targeted Rewriter / 定向正文精修",
        "- 原始正文。\n- Reviewer 結構化品質診斷報告。\n- 連續性約束與編輯指令。",
        "只針對被標記之段落進行局部重寫修正，未標記段落原樣保留，輸出精修後的完整繁體中文正文。",
        "直接輸出精修後正文，不要輸出評語、不要輸出 JSON。"
    )

    report_text = json.dumps(diagnostic_report, ensure_ascii=False, indent=2)

    user_content = f"""【Reviewer 品質診斷報告與待修復標記】
{report_text}

【額外精修指示】
{edit_instructions or "依據診斷報告修正視角越界、設定傾倒或生硬對白，保留未標記之優秀段落。"}

【不可破壞的連續性約束】
{editor_context or "（無額外約束）"}

【第 {chapter_index} 章原始正文】
{original_prose}

請直接輸出修訂後的完整小說正文：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


def build_editor_agent_messages(chapter_index, edit_instructions, original_prose, editor_context=None):
    """舊版單步編輯提示詞拼接（相容過渡介面）"""
    system_prompt = EDITOR_PROMPT + "\n" + CONTEXT_REQUEST_RULE
    system_prompt += build_agent_context_contract(
        "Editor / 正文編輯",
        "- 指定章節的原始正文。\n- 精修指示或總監修改重點。\n- 本章大綱、敘事記憶、角色卡與伏筆/轉折任務。",
        "只潤色、修補與提升指定章節正文；保留原章節核心事件、人物意圖、伏筆狀態與既有連續性。",
        "直接輸出精修後完整正文；不要輸出評語、JSON、世界觀修改或角色設定修改。"
    )
    user_content = f"""【修改指示 / 精修重點】
{edit_instructions or "精雕細琢遣詞造句，優化意象與文學美感，剔除冗詞贅字，增強情節張力與情緒渲染。"}

【編輯上下文 / 不可破壞的連續性約束】
{editor_context or "（尚無額外上下文）"}

【待精修的第 {chapter_index} 章原始正文】
{original_prose}

請直接輸出拋光後的完整正文：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
