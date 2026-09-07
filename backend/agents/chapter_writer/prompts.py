# -*- coding: utf-8 -*-
"""
Prompt Builder for Chapter Writer
負責組裝 Chapter Writer 的系統提示詞與情境化 User Prompt。
使用 WriterContextBuilder 進行 Scene Contract 與 Knowledge Scope 解構，杜絕 Raw JSON 傾倒。
"""

import json
from typing import Any, Dict, List, Optional

from backend import persistence as db
from backend.prompts.common.context import (
    CONTEXT_REQUEST_RULE,
    build_agent_context_contract,
)
from backend.prompts.prompt_main import (
    CHAPTER_WRITER_GUIDELINES,
    CHAPTER_WRITER_PROMPT,
)
from backend.services.context.writer_context_builder import build_writer_scene_context


def build_chapter_writer_messages(
    worldview_text: str,
    characters_bible: Any,
    current_outline: Dict[str, Any],
    surrounding_plot: str,
    vol_outline_context: str,
    clue_payoff_details: str,
    custom_style: str,
    chapter_index: int,
    user_prompt: Optional[str] = None,
    narrative_memory_context: Optional[str] = None,
    required_character_set: Optional[List[str]] = None,
    novel_id: str = "",
) -> List[Dict[str, str]]:
    """正文作家寫作提示詞拼接（情境化解構版）"""
    system_prompt = CHAPTER_WRITER_PROMPT + "\n" + CONTEXT_REQUEST_RULE + "\n\n" + CHAPTER_WRITER_GUIDELINES
    system_prompt += build_agent_context_contract(
        "Chapter Writer / 正文作家",
        "- 指定章節之 Scene Contract（含 POV 視角人物、敘事距離、戲劇目標與知情邊界）。\n- 結構化 Scene Beats 推進拍點。\n- 只限本章出場角色的穩定人格/語言卡與 current state；不得把初始知情當成現時知情。\n- 前章承接、必要的時序/canon facts、當前卷方向與本章 allocated tasks。\n- 本章若是 payoff，僅使用已驗證的 plant provenance；未提供不得臆造。",
        "只撰寫指定 chapter_index 的繁體中文正式正文，嚴格落實 POV 邊界、角色知情邊界與戲劇拍點。",
        "正式正文前必須輸出 [START_OF_PROSE]；不要輸出 JSON、不要輸出設定解說。"
    )

    system_prompt += """

## Writer Context Hard Boundary
- 你沒有資料庫、工具或全書檢索權；只能使用本輪明確提供的 context。
- 只執行本章 `chapter_plan` / `allocated_tasks`；不可提前執行後續章節的 payoff，也不可自行處理未分配 open threads。
- 前章/後章與卷方向僅用於銜接與伏筆鋪墊，不得把後續事件寫成已發生的事實。
- `initial_knowledge_scope` 是角色背景資料，不代表第 N-1 章的 current knowledge；若沒有 current state/knowledge，不得自行推定。
- 若本章為 payoff 而沒有可靠的 plant anchor，停止正文生成並依 context request contract 回報資料不足。
"""

    # 透過 WriterContextBuilder 生成解構後的乾淨情境文字
    user_content = build_writer_scene_context(
        novel_id=novel_id,
        worldview_text=worldview_text,
        characters_bible=characters_bible,
        current_outline=current_outline,
        surrounding_plot=surrounding_plot,
        vol_outline_context=vol_outline_context,
        clue_payoff_details=clue_payoff_details,
        custom_style=custom_style,
        chapter_index=chapter_index,
        user_prompt=user_prompt,
        narrative_memory_context=narrative_memory_context,
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
