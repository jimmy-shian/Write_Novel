import sys
import json

from backend.agents.director.prompts import build_director_decision_messages
from backend.services.diagnostics import generate_validation_report, detect_current_stage
from backend.services.director.tool_registry.inspect import expand_collapsed_json
from backend import persistence as db

def test_tool_loop_and_prompts():
    novel_id = '42330e2b-8a5a-4fe4-a017-a9a2a2ce827b'
    stage = 'foreshadowing'
    wb = db.get_latest_worldbuilding(novel_id)
    char_data = db.get_latest_characters(novel_id)
    val_rep = generate_validation_report(novel_id, current_stage=stage)

    # 1. Test expand_collapsed_json with string arguments
    res_str = expand_collapsed_json(stage_name='foreshadowing', field_name='key_turning_points', start_index='6', end_index='50', novel_id=novel_id)
    assert res_str['success'] is True, 'expand_collapsed_json failed with str args'
    assert res_str['returned_count'] == 45, f"expected 45, got {res_str['returned_count']}"

    # 2. Test prompt construction
    msgs = build_director_decision_messages(
        novel_id=novel_id,
        current_stage=stage,
        worldview_text=wb['content'],
        characters_text=char_data['json_data'],
        plot_text='伏筆與轉折編織審查階段',
        written_chapters_text='',
        user_prompt='請根據現有設定繼續創作',
        validation_report=val_rep
    )
    assert 'target: "volumes"' in msgs[0]['content'], 'foreshadowing system prompt should target volumes'
    assert msgs[1]['content'].strip().endswith('`reason`、`hint`、`agent_prompt` 或 `agent_context`。'), 'FINAL_USER_INSTRUCTION must be at the very end of user_content'

    # 3. Test detect_current_stage
    det = detect_current_stage(novel_id)
    assert det == 'volumes', f'Expected volumes, got {det}'
