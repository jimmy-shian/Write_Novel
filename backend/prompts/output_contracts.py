# -*- coding: utf-8 -*-
"""
Shared JSON output contracts for prompts.

This module keeps parser-facing key rules in one place so director and agent
prompts do not drift into mixed Chinese/English JSON property names.
"""

import json


STRICT_JSON_KEY_CONTRACT = """【資料欄位整理指引】
為了方便後續章節創作與系統存檔，請在 JSON 中保持英文 key（如 schema 所示），內容 value 則請使用生動流暢的繁體中文展開描述。"""


JSON_OBJECT_OUTPUT_CONTRACT = """【輸出指引】
請只輸出純 JSON，讓我們直接聚焦在小說設定與情節乾貨上。"""


COPILOT_FLOW_OUTPUT_CONTRACT = """## Co-Pilot Flow JSON 契約
如果要呼叫 Agent，請在回應末尾輸出單一 JSON 物件：
{
  "action": "TRIGGER_AGENT",
  "target": "worldview",
  "hint": "簡短任務指示",
  "agent_prompt": "直接交給下游 Agent 的完整任務說明，必須保留作者核心需求。",
  "agent_context": "可附上作者素材、既有片段或總監整理的上下文。",
  "user_intent_summary": "一到三句總結作者真正想達成的效果。",
  "reason": "你選擇此 target 的理由。",
  "volume_index": null,
  "chapter_index": null
}

如果只是聊天或給建議，不呼叫 Agent，請在回應末尾輸出單一 JSON 物件：
{
  "action": "chat",
  "target": null,
  "hint": "",
  "agent_prompt": "",
  "agent_context": "",
  "user_intent_summary": "",
  "reason": "單純與作者討論，不執行生成。",
  "volume_index": null,
  "chapter_index": null
}
"""


CONTEXT_REQUEST_JSON_CONTRACT = """## Context Request JSON 契約
只有在資料真的不足以完成任務時才使用。此時請只輸出純 JSON，讓系統與總監補齊資料後再生成：
__STRICT_JSON_KEY_CONTRACT__
{
  "_needs_director_context": true,
  "context_request": "請總監補充哪些資料，以及為什麼缺這些資料會阻斷本次生成。",
  "missing_data": ["缺少的資料項目 1", "缺少的資料項目 2"],
  "why_it_blocks_generation": "若直接生成會造成的人設、世界觀或流程風險。"
}
""".replace("__STRICT_JSON_KEY_CONTRACT__", STRICT_JSON_KEY_CONTRACT)


DIRECTOR_DECISION_KEY_CONTRACT = """## 總監 JSON 欄位命名指引
系統會讀取回應中的 JSON 區塊，請統一使用下列標準英文 snake_case key 組織結構，中文內容請填寫於對應的 value 中：
- action
- target
- hint
- agent_prompt
- agent_context
- user_intent_summary
- reason
- volume_index
- chapter_index
- insert_after_index
- chapter_range
- selection
- task_type
- tool_call
- tool_name
- parameters
"""


DIRECTOR_TOOL_CALL_CONTRACT = """## 總監工具調用指引
若需要調用工具查閱資料，請設定 `action: "TOOL_CALL"`，並將工具名稱與參數完整封裝在 `tool_call` 物件內，只輸出純 JSON。
每次 `TOOL_CALL` 最外層請填寫 `reason`，說明本次查閱的目的與後續決策方向。
若先前的查閱已取得相應資料，請根據結果直接下達流程決策，避免重複查閱相同範圍。

{
  "action": "TOOL_CALL",
  "tool_call": {
    "tool_name": "evaluate_output",
    "parameters": {
      "stage_name": "volume_skeleton"
    }
  },
  "reason": "確認 volume_skeleton 的結構完整度，評估內容品質。"
}

查閱內容區塊（inspect_content_block）參數指引：
{
  "action": "TOOL_CALL",
  "tool_call": {
    "tool_name": "inspect_content_block",
    "parameters": {
      "stage_name": "volume_skeleton",
      "block_name": "chapters_outline",
      "volume_index": 7,
      "start_index": 1,
      "end_index": 15
    }
  },
  "reason": "展開第 7 卷第 1-15 章細綱，閱讀情節推進與人物互動品質。"
}

展開長列表（expand_collapsed_json）參數指引：
{
  "action": "TOOL_CALL",
  "tool_call": {
    "tool_name": "expand_collapsed_json",
    "parameters": {
      "stage_name": "worldview",
      "field_name": "progressive_character_plan",
      "start_index": 1,
      "end_index": 15
    }
  },
  "reason": "展開角色漸進規劃第 1-15 筆進行細部審查。"
}
查詢章節時，請統一使用 start_index 與 end_index 標註範圍。"""


DIRECTOR_HARD_VALIDATION_POLICY = """## Python 硬性校驗的用途與邊界
`validation_report` 與 `evaluate_output` 是由系統後端預先計算的客觀校驗結果，包含：
- JSON 資料是否完整可解析。
- 各階段必填欄位是否存在。
- 伏筆、轉折點與篇卷數量是否達標。
- 卷號、章號是否連續。
- 正文長度與文字飽滿度。

若校驗報告顯示結構與數量均已合格，且當前展示的內容品質良好，總監即可放心放行進入下一階段（下達 CONTINUE）；若發現情節邏輯或文字風格有具體問題，再調用工具細查。"""


DIRECTOR_MANDATORY_INSPECTION_POLICY = """## 長列表檢閱與決策指引
1. 當輸入出現摘要標記或收合提示時，代表資料庫中已妥善持久化儲存，提示詞中僅為精簡長度進行了視圖收合。
2. 若系統校驗確認數量與結構合格，展示的代表性章節或設定品質優良，總監可直接給予流程決策（如 CONTINUE），順暢推進流程。
3. 若需要深度研讀特定範圍的細節，可調用相應工具進行調閱。
4. 資料查閱完畢後，請及時給出具體明確的流程決策，帶領整個小說創作團隊穩步向前。"""


def format_json_schema_prompt(schema, *, label="this schema"):
    """Return a clean schema prompt with conversational guide."""
    return (
        f"\n【資料格式參考】\n"
        f"{STRICT_JSON_KEY_CONTRACT}\n\n"
        f"以下為資料結構範例，只輸出純 JSON：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    )
