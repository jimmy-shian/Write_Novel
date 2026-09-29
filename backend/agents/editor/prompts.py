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
        "- 待評審章節的原始正文。\n- 當前章節 Scene Contract、大綱與角色知情邊界。\n- 伏筆任務、時序動態事實與連續性記憶。",
        "診斷正文中的視角、知情、時序事實一致性、設定邊界與語言表現，輸出結構化診斷 JSON 報告。",
        "直接輸出診斷 JSON 報告。"
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
    fix_mode: bool = False,
    fix_spans: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """組裝 Targeted Rewriter 定向精修提示詞"""
    system_prompt = TARGETED_REWRITER_PROMPT
    if fix_mode:
        system_prompt += "\n\n【修正輪特別禁令】：禁用模板庫零容忍，被標記段落必須重寫消除套路，未標記段落保留；出現禁用句即視為失敗。"
    system_prompt += build_agent_context_contract(
        "Targeted Rewriter / 定向正文精修",
        "- 原始正文。\n- Reviewer 結構化品質診斷報告。\n- 時序動態事實、設定邊界約束與編輯指令。",
        "職責邊界限制：專注於語句潤色、語法流暢、口癖剔除與文風調理，嚴禁推翻因果結構、篡改大綱核心事件或變更人物抉擇；針對被標記之段落進行局部修補，未標記段落原樣保留，輸出精修後的完整繁體中文正文。",
        "直接輸出精修後正文，不要輸出評語、引言、註解或 JSON。",
        allow_context_request=False,
    )

    if fix_mode:
        spans_text = ""
        if fix_spans:
            lines = []
            for s in fix_spans:
                p_idx = s.get("paragraph_index", 1)
                sent = s.get("matched_sentence", "")
                lbl = s.get("pattern_label", "")
                lines.append(f"- [第 {p_idx} 段] 原文：『{sent}』(問題：{lbl}) -> 必須整句刪除重寫，嚴禁近義詞修飾！")
            spans_text = "\n".join(lines)
        else:
            spans_text = "（無特定標記句，依修正指令進行局部修訂）"

        user_content = f"""【本次修正最高指令：覆寫其他風格要求】
{edit_instructions or "依據診斷報告修正視角越界、設定傾倒或生硬對白，保留未標記之優秀段落。"}

【待刪除/替換原文 span（必須定點消滅重寫，出現即判失敗）】
{spans_text}

【不可破壞的連續性約束】
{editor_context or "（無額外約束）"}

【第 {chapter_index} 章原始正文】
{original_prose}

請直接輸出修訂後的完整小說正文：
"""
    else:
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


def build_length_expand_messages(
    chapter_index: int,
    short_prose: str,
    deficit: int,
    original_prose: Optional[str] = None,
    editor_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """組裝長度不足自動擴寫重試提示詞。

    用於 Editor 初次精修輸出被壓縮至 1200 字以下的情況：
    以偏短的精修稿為基底，用感官／心理／動作細節補足 deficit 字數，
    禁止刪減既有情節、禁止輸出評語，只輸出完整正文。
    """
    system_prompt = (
        TARGETED_REWRITER_PROMPT
        + "\n\n【擴寫補足特別指令（最高優先）】：本次任務是將偏短的精修稿擴寫補足至完整章節長度。"
        "必須保留既有事件因果、人物狀態與關鍵情節，只能增加細節、不可刪除任何已有段落；"
        "嚴禁輸出評語、引言、註解或 JSON。"
    )
    system_prompt += build_agent_context_contract(
        "Targeted Rewriter / 篇幅擴寫補足",
        "- 偏短的精修稿全文（擴寫基底）。\n- 原始正文（情節對照，不得遺漏關鍵事件）。\n- 不可破壞的連續性約束。",
        "將偏短稿擴寫至完整章節長度，輸出精修後的完整繁體中文正文。",
        "直接輸出擴寫後的完整正文，不要輸出評語、引言、註解或 JSON。",
        allow_context_request=False,
    )

    reference_block = ""
    if original_prose:
        reference_block = f"\n【原始正文對照（不得遺漏其中關鍵情節）】\n{original_prose}\n"

    user_content = f"""【篇幅缺口】：目前精修稿不足完整章節下限，尚缺約 {deficit} 字（全文必須達到 1200 字以上，以 Python len() 計）。

【擴寫方法（只增不減）】
- 以感官描寫、心理活動、動作細節、環境氛圍補足篇幅，呼應本章大綱與人物動機。
- 不可刪除或合併已有段落，不可將對白壓縮為一句帶過，不可新增與大綱矛盾的新事件。
- 禁止複製貼上式灌水：每段新增細節都必須推動情緒、塑造人物或鋪陳後續因果。
{reference_block}
【不可破壞的連續性約束】
{editor_context or "（無額外約束）"}

【待擴寫的偏短精修稿全文】
{short_prose}

請直接輸出擴寫補足後的完整小說正文（必須達到 1200 字以上）：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def build_editor_agent_messages(chapter_index, edit_instructions, original_prose, editor_context=None):
    """正文潤色編輯提示詞拼接"""
    system_prompt = EDITOR_PROMPT
    system_prompt += build_agent_context_contract(
        "Editor / 正文編輯",
        "- 指定章節的原始正文。\n- 精修指示或總監修改重點。\n- 本章場景目標、術語表、時序動態事實、衝突防重複與設定運作邊界。",
        "只潤色、修補與提升指定章節正文文學美感；嚴格維持動態世界線事實、設定代價邊界與情節推進因果。",
        "直接輸出精修後完整繁體中文正文；不要輸出評語、引言、註解、JSON、世界觀修改或角色設定修改。",
        allow_context_request=False,
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
