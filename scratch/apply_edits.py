# -*- coding: utf-8 -*-
import os
import re

builder_path = r"c:\Users\user\Desktop\test_html\Write_Novel\prompts\prompt_builder.py"
agents_path = r"c:\Users\user\Desktop\test_html\Write_Novel\agents.py"

# Read prompt_builder.py
with open(builder_path, 'r', encoding='utf-8') as f:
    builder_content = f.read()

# Replace build_copilot_chat_messages
old_copilot = """def build_copilot_chat_messages(worldview_text, characters_text, plot_text, history_context, user_message, validation_report=None):
    \"\"\"Copilot 創意決策總監聊天提示詞\"\"\"
    if not validation_report:
        validation_report = "底層校驗一切正常。全階段架構完備。"
    written_chapters_text = "未進入正文寫作"
    
    # 對角色聖經進行基本設定篩選
    characters_filtered = extract_character_basic(characters_text)
    
    # 填充 CO_PILOT_ORCHESTRATOR_PROMPT
    system_prompt = CO_PILOT_ORCHESTRATOR_PROMPT.format(
        worldview=worldview_text[:300] + "...",
        characters=json.dumps(characters_filtered, ensure_ascii=False)[:300] + "...",
        plot=plot_text[:300] + "...",
        written_chapters=written_chapters_text,
        validation_report=validation_report
    )
    
    user_content = f\"\"\"【當前專案狀態】
- 世界觀：{worldview_text[:300]}...
- 角色 Bible：{json.dumps(characters_filtered, ensure_ascii=False)[:300]}...
- 大綱概要：{plot_text[:300]}..."""

new_copilot = """def build_copilot_chat_messages(novel_id, worldview_text, characters_text, plot_text, history_context, user_message, validation_report=None):
    \"\"\"Copilot 創意決策總監聊天提示詞\"\"\"
    if not validation_report:
        validation_report = "底層校驗一切正常。全階段架構完備。"
    
    from diagnostics import diagnose_all_phases
    diags = diagnose_all_phases(novel_id)
    
    # 填充 CO_PILOT_ORCHESTRATOR_PROMPT
    system_prompt = CO_PILOT_ORCHESTRATOR_PROMPT.format(
        worldview=diags["worldview"],
        characters=diags["characters"],
        plot=diags["plot"],
        written_chapters=diags["written_chapters"],
        validation_report=validation_report
    )
    
    user_content = f\"\"\"【當前專案狀態】
- 世界觀：{diags["worldview"]}
- 角色 Bible：{diags["characters"]}
- 大綱概要：{diags["plot"]}"""

# Normalize CRLF/LF for replacement
builder_content = builder_content.replace(old_copilot.replace('\n', '\r\n'), new_copilot.replace('\n', '\r\n'))
builder_content = builder_content.replace(old_copilot, new_copilot)

# Read build_director_decision_messages in builder_content and modify it
# Let's inspect where build_director_decision_messages is and how it slices things
# Slices in build_director_decision_messages:
# worldview_text[:1500] if worldview_text else "（空）"
# characters_text[:1500] if characters_text else "（空）"
# plot_text[:1500] if plot_text else "（空）"
# written_chapters_text if written_chapters_text else "（空）" -> wait, does it have a slice? No, but let's change them to diags.

old_decision_default = """        user_content = f\"\"\"【創作主軸需求】
{user_prompt}
 
【當前各板塊數據】
- 世界觀設定：{worldview_text[:1500] if worldview_text else "（空）"}
- 角色設定：{characters_text[:1500] if characters_text else "（空）"}
- 大綱設定：{plot_text[:1500] if plot_text else "（空）"}
- 正文：{written_chapters_text if written_chapters_text else "（空）"}\"""".replace('\n', '\r\n')

new_decision_default = """        user_content = f\"\"\"【創作主軸需求】
{user_prompt}
 
【當前各板塊數據】
- 世界觀設定：{diags["worldview"]}
- 角色設定：{diags["characters"]}
- 大綱設定：{diags["plot"]}
- 正文：{diags["written_chapters"]}\"""".replace('\n', '\r\n')

builder_content = builder_content.replace(old_decision_default, new_decision_default)
# Also try without CRLF normalization
builder_content = builder_content.replace(old_decision_default.replace('\r\n', '\n'), new_decision_default.replace('\r\n', '\n'))

# Change signature of build_director_decision_messages
old_sig = "def build_director_decision_messages(current_stage, worldview_text, characters_text, plot_text, written_chapters_text, user_prompt, validation_report, character_review_mode=None, character_review_hint=None, character_review_target_content=None, suggested_next_chapter=None, chapter_index=None):"
new_sig = "def build_director_decision_messages(novel_id, current_stage, worldview_text, characters_text, plot_text, written_chapters_text, user_prompt, validation_report, character_review_mode=None, character_review_hint=None, character_review_target_content=None, suggested_next_chapter=None, chapter_index=None):\\n    from diagnostics import diagnose_all_phases\\n    diags = diagnose_all_phases(novel_id)"

builder_content = builder_content.replace(old_sig, "def build_director_decision_messages(novel_id, current_stage, worldview_text, characters_text, plot_text, written_chapters_text, user_prompt, validation_report, character_review_mode=None, character_review_hint=None, character_review_target_content=None, suggested_next_chapter=None, chapter_index=None):\n    from diagnostics import diagnose_all_phases\n    diags = diagnose_all_phases(novel_id)")

with open(builder_path, 'w', encoding='utf-8') as f:
    f.write(builder_content)

print("prompt_builder.py modified successfully.")

# Read agents.py
with open(agents_path, 'r', encoding='utf-8') as f:
    agents_content = f.read()

# Replace calls in agents.py
# 1. build_copilot_chat_messages(worldview_text, characters_text...
# 2. build_director_decision_messages(current_stage, worldview_text...

agents_content = agents_content.replace(
    "build_copilot_chat_messages(\n        worldview_text",
    "build_copilot_chat_messages(\n        novel_id, worldview_text"
)
agents_content = agents_content.replace(
    "build_copilot_chat_messages(worldview_text",
    "build_copilot_chat_messages(novel_id, worldview_text"
)

agents_content = agents_content.replace(
    "build_director_decision_messages(\n        current_stage",
    "build_director_decision_messages(\n        novel_id, current_stage"
)
agents_content = agents_content.replace(
    "build_director_decision_messages(current_stage",
    "build_director_decision_messages(novel_id, current_stage"
)

with open(agents_path, 'w', encoding='utf-8') as f:
    f.write(agents_content)

print("agents.py modified successfully.")
