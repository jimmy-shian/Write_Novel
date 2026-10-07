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
    fix_mode: bool = False,
    fix_targets: Optional[List[Dict[str, Any]]] = None,
    banned_hits: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """正文作家寫作提示詞拼接（情境化解構版）"""
    system_prompt = CHAPTER_WRITER_PROMPT + "\n" + CONTEXT_REQUEST_RULE + "\n\n" + CHAPTER_WRITER_GUIDELINES
    if fix_mode:
        system_prompt += "\n\n【修正輪特別禁令】：禁用句與套路動作零容忍，其優先級高於文學美感與銜接要求。被標記之套路動作與因果必須實質打破，出現禁用句即判失敗。"
    system_prompt += build_agent_context_contract(
        "Chapter Writer / 正文作家",
        "- 指定章節之場景契約（包含 POV 視角人物、戲劇目標與知情邊界）。\n- 結構化推進拍點 (Scene Beats)。\n- 本章出場角色的人格特質與當前狀態。\n- 前章銜接背景與本章任務。",
        "撰寫指定章節可供 Editor 擴寫的繁體中文劇情底稿，完整交代事件因果、角色行動與情緒轉折；描寫潤飾由 Editor 完成。",
        "請直接輸出小說正文（可在正文開頭標註 [正文開始]），不需輸出額外的 JSON 或設定解說。"
    )

    system_prompt += """

【本章正文創作指引】
- 職責分工：交付情節完整、因果清楚、角色行動與重要對白到位的可編輯底稿；不要為達篇幅刻意灌入大量環境、衣著、表情或修辭描寫，這些由 Editor 擴寫精修。
- 專注本章：請聚焦落實本章場景契約與推進拍點，使情節平穩自然地推進。
- 知情邊界：人物言語與行動基於其當前已知情報與性格動機，呈現真實生動的情境互動。
- 緊密銜接：承接前章留下的局勢與情緒餘波，將本章懸念自然留給下一章。
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
        fix_mode=fix_mode,
        fix_targets=fix_targets,
        banned_hits=banned_hits,
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
