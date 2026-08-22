# -*- coding: utf-8 -*-
"""
Shared JSON output contracts for prompts.

This module keeps parser-facing key rules in one place so director and agent
prompts do not drift into mixed Chinese/English JSON property names.
"""

import json


STRICT_JSON_KEY_CONTRACT = """## JSON 欄位命名合約
- JSON property name 必須完全使用 schema / 範例中列出的英文 snake_case key。
- 嚴禁把 key 翻譯成中文、繁簡混用或改成同義詞；例如不得把 `chapter_index` 寫成「章節序號」，不得把 `agent_prompt` 寫成「代理人提示詞」。
- 可以在 value 裡使用繁體中文內容；只有 key 必須維持英文 snake_case。
- 不得新增 schema 未列出的頂層 key 或 alias key。"""


JSON_OBJECT_OUTPUT_CONTRACT = """## JSON 物件輸出契約
1. 只輸出一個格式完全合法、可被 Python `json.loads()` 直接解析的標準 JSON 物件。
2. 必須使用 ```json ... ``` code block 包裹。
3. 不得在 JSON block 之前或之後輸出寒暄、摘要、評語、修改說明或任何自然語言。
4. 不得輸出多個 JSON 物件、半截 JSON、註解、尾逗號或 schema 未允許的頂層 key。
__STRICT_JSON_KEY_CONTRACT__""".replace("__STRICT_JSON_KEY_CONTRACT__", STRICT_JSON_KEY_CONTRACT)


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
只有在資料真的不足以完成任務時才使用。此時請只輸出以下 JSON，讓系統與總監補齊資料後再生成：
__STRICT_JSON_KEY_CONTRACT__
```json
{
  "_needs_director_context": true,
  "context_request": "請總監補充哪些資料，以及為什麼缺這些資料會阻斷本次生成。",
  "missing_data": ["缺少的資料項目 1", "缺少的資料項目 2"],
  "why_it_blocks_generation": "若直接生成會造成的人設、世界觀或流程風險。"
}
```
""".replace("__STRICT_JSON_KEY_CONTRACT__", STRICT_JSON_KEY_CONTRACT)


DIRECTOR_DECISION_KEY_CONTRACT = """## 總監 JSON 欄位命名合約
系統只解析最後一個 JSON block，且只接受下列英文 snake_case key：
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

嚴禁使用中文 key 或別名 key，例如「行動」、「目標」、「原因」、「篇卷序號」、「章節序號」、「代理人提示詞」、「工具名稱」、「參數」。中文只能出現在 value 裡。"""


DIRECTOR_TOOL_CALL_CONTRACT = """## 總監工具 JSON 契約
工具呼叫必須使用 `action: "TOOL_CALL"`，並把工具名稱與參數放在 `tool_call` 內；不要把工具參數攤平成頂層欄位。
每次 `TOOL_CALL` 最外層都必須填寫 `reason`，說明「為什麼要查這段、正在驗證哪個風險、工具結果將用來決定什麼」。後端會把此 reason 鎖進下一輪工具 follow-up context，避免總監跨輪忘記原本的工作。
同一輪工具 follow-up context 內若已出現相同 `tool_signature`，代表同一工具同一參數已執行過；禁止再次輸出相同 TOOL_CALL，必須根據既有工具結果做流程決策，或改查尚未查過的不同範圍。
絕對禁止只輸出工具參數物件，例如 `{ "stage_name": "...", "field_name": "..." }`。工具參數必須被包在下列完整 envelope 的 `tool_call.parameters` 之內。

```json
{
  "action": "TOOL_CALL",
  "tool_call": {
    "tool_name": "evaluate_output",
    "parameters": {
      "stage_name": "volume_skeleton",
      "output_content": "通常省略。除非後端明確提供了一段短小且完整的未持久化輸出，否則不要放入大段 JSON 或正文；後端會依 stage_name 從資料庫讀取完整輸出。",
      "novel_id": "由後端自動注入時可省略"
    }
  },
  "reason": "先做硬性校驗：確認 volume_skeleton 的 JSON 結構、必填欄位與章節索引是否可通過；若通過，再展開指定章節做內容品質審查。"
}
```

`inspect_content_block` 的參數只能使用這些英文 key：
```json
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
  "reason": "展開第 7 卷骨架第 1-15 筆，實際閱讀內容品質。"
}
```

`expand_collapsed_json` 用於展開世界觀 JSON 內被收合的長列表，包括 `multi_act_structure`、`progressive_character_plan`、`foreshadowing_seeds`、`key_turning_points` 等；參數只能使用：
```json
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
  "reason": "展開角色漸進規劃第 1-15 筆做內容審查。"
}
```

禁止使用 `start_chapter`、`end_chapter`、`章節範圍`、`欄位名稱`、`工具名稱` 等別名。章節號若要查卷骨架，請先轉成該卷內的 `start_index` / `end_index`；例如第 7 卷章節 273-317 對應第 7 卷 `chapters_outline` 的 `start_index: 1, end_index: 45`。"""


DIRECTOR_HARD_VALIDATION_POLICY = """## Python 硬性校驗的用途與邊界
`validation_report` 與 `evaluate_output` 是 Python 計算出的硬性結果，用來回答 LLM 不應自行猜算的問題。呼叫 `evaluate_output` 時優先只傳 `stage_name`；不要把收合封包、長列表、完整角色表、完整卷骨架或正文塞進 `output_content`：
- JSON 是否可解析。
- 必填欄位是否存在且非空。
- 數量是否達標，例如伏筆/轉折至少 50 個、篇卷數量範圍。
- 卷號、章號、id 是否連續或重複。
- allocated_tasks 是否有明顯格式錯誤。
- 正文是否過短、空白或含占位標記。

硬性校驗回答「結構與數量」。若 Python 校驗報告確認數量與結構皆合格，且展示的預設視圖品質優良，總監即可直接放行進入下一流程（例如下達 CONTINUE）；僅在發現具體品質疑慮時才需調用展開工具細查。"""


DIRECTOR_MANDATORY_INSPECTION_POLICY = """## 長列表收合與展開檢閱指引
1. 當輸入出現摘要標記或 `...收合標記...` 時，代表資料庫中已完整存檔，僅在提示詞中為節省 Token 進行了展示收合。
2. 若 Python 校驗報告確認該區塊數量與必填欄位完整，且展示的項目質量符合標準，總監可直接下達流程決策（如 `CONTINUE`），不需要強制調用工具展開每一筆已收合的項目。
3. 若總監確實需要深度審閱某個具體範圍的內容細節，可以使用 `TOOL_CALL`（如 `expand_collapsed_json` 或 `inspect_content_block`）調閱該範圍。
4. **禁止重複展開**：工具返回展開結果後，該資料即視為已檢閱完畢。總監必須在下一輪給出流程決策（`CONTINUE` / `AUTO_REGENERATE` / `GO_BACK_*` 等），絕對禁止連續調用相同參數的展開工具，不得陷入展開循環。"""


def format_json_schema_prompt(schema, *, label="this schema"):
    """Return a unified schema prompt with strict parser-facing key rules."""
    return (
        f"\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching {label}. "
        "Wrap in ```json ... ``` codeblock]\n"
        f"{STRICT_JSON_KEY_CONTRACT}\n\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    )
