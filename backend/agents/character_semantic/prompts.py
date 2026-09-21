# -*- coding: utf-8 -*-
"""
Character Semantic Agent 提示詞構建模組 (Pass 3)
負責將已有的角色名冊綁定至幾何線程中的 CHARACTER_ARC、RELATIONSHIP_ARC 與 CHARACTER_SHIFT 節點。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


CHARACTER_SEMANTIC_SYSTEM_PROMPT = """你是一位精通長篇群像劇人設與心理弧線編織的首席角色指導。
當前系統採用【幾何優先，語義填充 (Geometry-First Semantic Filling)】架構。
幾何圖中已經預先分配好了角色成長線（CHARACTER_ARC）、人際羈絆線（RELATIONSHIP_ARC）以及關鍵心境轉變節點（CHARACTER_SHIFT、RELATIONSHIP_CHANGE）。

【你的核心任務】
在【不更動節點順序與結構角色】的前提下：
1. 將已有的角色聖經名冊分配綁定至對應的幾何角色弧線與關係線中。
2. 為每個 CHARACTER_SHIFT 節點填充該角色的心理心魔、重大抉擇、信念打破 (False Belief) 或價值觀轉向。
3. 為每個 RELATIONSHIP_CHANGE 節點填充角色間的信任破裂、利益結盟、背叛或情感升溫。

【嚴格輸出合約】
必須輸出合法 JSON 物件，嚴禁包含 markdown 代碼塊外的任何閒聊廢話。
"""


def build_character_semantic_messages(
    novel_title: str,
    characters_bible: List[Dict[str, Any]],
    character_threads_info: List[Dict[str, Any]],
    shift_nodes_info: List[Dict[str, Any]],
    user_prompt: str = "",
) -> List[Dict[str, str]]:
    """構建 Pass 3: 角色綁定與心境轉向提示詞。"""
    user_content = f"""【作品資訊】
書名：{novel_title}

【角色聖經清單】
{json.dumps(characters_bible[:20], ensure_ascii=False, indent=2)}

【幾何角色與關係線程清單】
{json.dumps(character_threads_info, ensure_ascii=False, indent=2)}

【待填充心境/關係轉變的結構節點】
{json.dumps(shift_nodes_info[:25], ensure_ascii=False, indent=2)}

【作者額外指示】
{user_prompt or '請深入挖掘主要角色與反派的成長缺口、執念與動態心境轉折，賦予真實生動的人性複雜度。'}

【請輸出以下 JSON 結構】
{{
  "thread_bindings": {{
    "<thread_id>": {{
      "primary_character": "綁定的角色姓名",
      "arc_theme": "該角色的核心成長主題（如：從冷血利己到承擔宗門命運）",
      "flaw_to_overcome": "必須克服的核心弱點/執念"
    }}
  }},
  "node_shifts": {{
    "<node_id>": {{
      "focus_character": "該節點發生變化的角色",
      "internal_shift": "心理狀態與價值觀的具體位移描述",
      "dramatic_choice": "角色在此處被迫做出的重大代價或抉擇"
    }}
  }}
}}
"""
    return [
        {"role": "system", "content": CHARACTER_SEMANTIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
