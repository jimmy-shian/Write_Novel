# -*- coding: utf-8 -*-
"""
Macro Semantic Agent 提示詞構建模組 (Pass 1 & Pass 2)
負責引導 LLM 在不改動幾何拓撲的前提下，為 Volume, Arc 以及 Thread 注入文學語義。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


MACRO_SEMANTIC_SYSTEM_PROMPT = """你是一位精通長篇小說宏觀架構的文學總監與語義填充架構師。
當前系統採用【幾何優先，語義填充 (Geometry-First Semantic Filling)】架構。
程式已經一次性精確鋪設好了全書的幾何拓撲（章節分卷區間、弧線劃分、線程骨架、節點角色）。

【你的唯一職責】
在【絕對不修改章節位置、數量與結構角色】的前提下，為給定的幾何骨架注入具體的文學故事語義：
1. 篇卷語義 (Volume Semantics)：每卷的主題、劇名、衝突核心、核心目標與高潮轉折。
2. 弧線語義 (Arc Semantics)：卷內各階段的起承轉合情節主旨。
3. 線程語義 (Thread Semantics)：為每條主線、副線、主題線賦予具體的劇本命名、核心懸念與推進邏輯。

【嚴格輸出合約】
必須輸出合法 JSON 物件，嚴禁包含 markdown 代碼塊外的任何閒聊廢話。
JSON 的 key 必須嚴格對應輸入的容器 ID (如 V01, A01, TM01 等)。
"""


def build_volume_semantic_messages(
    novel_title: str,
    genre: str,
    worldview_text: str,
    volumes_info: List[Dict[str, Any]],
    user_prompt: str = "",
) -> List[Dict[str, str]]:
    """構建 Pass 1: 篇卷與弧線語義填充提示詞。"""
    vol_descriptions = []
    for v in volumes_info:
        vol_descriptions.append({
            "volume_id": v["volume_id"],
            "volume_index": v["volume_index"],
            "chapter_range": f"第 {v['chapter_range'][0]} - {v['chapter_range'][1]} 章",
            "arcs": v.get("arcs", []),
        })

    user_content = f"""【小說資訊】
書名：{novel_title}
題材：{genre}
【作者創作原案/世界觀摘要】
{worldview_text[:6000]}

【需要填充語義的幾何篇卷容器清單】
{json.dumps(vol_descriptions, ensure_ascii=False, indent=2)}

【作者額外指示】
{user_prompt or '請依據世界觀設定與長篇小說節奏，為每一卷與弧線設計富有吸引力的主線故事與衝突。'}

【請輸出以下 JSON 結構】
{{
  "volumes": {{
    "<volume_id>": {{
      "title": "卷標題（簡練有張力）",
      "summary": "本卷全景摘要（200-300字）",
      "theme": "本卷核心思想/主題",
      "conflict_core": "核心對抗與主要阻礙",
      "climax_turn": "卷末最高潮轉折"
    }}
  }},
  "arcs": {{
    "<arc_id>": {{
      "title": "階段主題",
      "narrative_goal": "本階段必須達成的戲劇目標",
      "tension_focus": "張力聚焦點"
    }}
  }}
}}
"""
    return [
        {"role": "system", "content": MACRO_SEMANTIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_thread_semantic_messages(
    novel_title: str,
    genre: str,
    worldview_text: str,
    volume_semantics_summary: str,
    threads_info: List[Dict[str, Any]],
    user_prompt: str = "",
) -> List[Dict[str, str]]:
    """構建 Pass 2: 線程語義填充提示詞。"""
    thread_descriptions = []
    for t in threads_info:
        thread_descriptions.append({
            "thread_id": t["thread_id"],
            "thread_type": t["thread_type"],
            "node_count": len(t.get("node_sequence", [])),
            "chapter_span": t.get("metadata", {}).get("chapter_span", (1, 1)),
            "structural_skeleton": t.get("structural_skeleton", []),
        })

    user_content = f"""【小說資訊】
書名：{novel_title}
題材：{genre}
【已填充的各卷故事大綱】
{volume_semantics_summary}

【世界觀背景】
{worldview_text[:4000]}

【幾何線程骨架清單】
{json.dumps(thread_descriptions, ensure_ascii=False, indent=2)}

【請輸出以下 JSON 結構】
為每條線程填入具體劇情設定（例如神祕古鏡之謎、宗門內鬼之爭、道侶情感羈絆等）：
{{
  "threads": {{
    "<thread_id>": {{
      "thread_name": "線程名稱（如：青雲古印之謎）",
      "description": "具體劇情推進說明與牽涉利益",
      "core_question": "本線程引發的核心懸念",
      "thematic_resonance": "呼應之主題理念"
    }}
  }}
}}
"""
    return [
        {"role": "system", "content": MACRO_SEMANTIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
