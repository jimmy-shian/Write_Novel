# -*- coding: utf-8 -*-
"""
Cross Relation Semantic Agent 提示詞構建模組 (Pass 4)
負責為幾何圖中的跨距 Motif 邊（CONVERGES, ECHOES, CONTRASTS 等）注入具體因果、碰撞動機與主題對比語義。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


CROSS_RELATION_SYSTEM_PROMPT = """你是一位精通多線交織、伏筆呼應與思想對比的長篇敘事工程師。
當前系統採用【幾何優先，語義填充 (Geometry-First Semantic Filling)】架構。
幾何圖中已經精準連好了數百條跨距結構邊（CONVERGES 多線匯聚, ECHOES 遙相呼應, CONTRASTS 思想對照, SETS_UP/PAYS_OFF 伏筆鏈）。
前置階段已經完成了篇卷 (Pass 1)、線程 (Pass 2) 與角色綁定 (Pass 3)。

【你的核心任務】
為這些跨距關係邊注入具體的【文學因果與碰撞理由】：
1. CONVERGES (合流/匯聚)：兩條或多條線程為什麼在此處劇烈碰撞？各方在此處的利益衝突點是什麼？
2. ECHOES (呼應)：後面的情節如何以變奏形式呼應前文的種子？
3. CONTRASTS (對比)：這兩個相隔甚遠的情節節點，在主角抉擇、命運境遇或哲學觀點上形成了怎樣的諷刺或鏡像對比？

【嚴格輸出合約】
必須輸出合法 JSON 物件，以 edge_id 為鍵，填充詳細的關聯語義。
"""


def build_cross_relation_messages(
    novel_title: str,
    threads_summary: str,
    cross_edges_info: List[Dict[str, Any]],
    user_prompt: str = "",
) -> List[Dict[str, str]]:
    """構建 Pass 4: 跨距 Motif 關聯語義填充提示詞。"""
    user_content = f"""【作品資訊】
書名：{novel_title}

【已填充的主要線程劇情摘要】
{threads_summary}

【待注入因果語義的幾何 Motif 結構邊清單】
{json.dumps(cross_edges_info[:35], ensure_ascii=False, indent=2)}

【作者額外指示】
{user_prompt or '請確保多線交會合情合理且充滿戲劇爆發力，長距離對比具有深刻的文學宿命感。'}

【請輸出以下 JSON 結構】
{{
  "edges": {{
    "<edge_id>": {{
      "causal_link": "兩節點之間的實質因果或驅動關係",
      "dramatic_clash": "若為 CONVERGES，說明雙方碰撞之核心矛盾；若為 ECHOES，說明呼應細節；若為 CONTRASTS，說明對照之價值觀",
      "audience_impact": "給讀者帶來的驚喜、伏筆解鎖或情感衝擊"
    }}
  }}
}}
"""
    return [
        {"role": "system", "content": CROSS_RELATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
