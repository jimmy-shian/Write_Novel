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


def format_json_schema_prompt(schema, *, label="this schema"):
    """Return a unified schema prompt with strict parser-facing key rules."""
    return (
        f"\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching {label}. "
        "Wrap in ```json ... ``` codeblock]\n"
        f"{STRICT_JSON_KEY_CONTRACT}\n\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    )
