# -*- coding: utf-8 -*-
"""
總監角色守門單元測試：
- 單一角色時診斷必須嚴正阻斷、階段不得前進、總監決策須被攔截要求自癒
- 補足主要反派後放行
"""
import json

from backend import persistence as db
from backend.services.diagnostics import diagnose_characters, detect_current_stage
from backend.agents.director.runner import (
    _director_decision_needs_recovery,
    _get_director_decision_error_message,
)
from backend.services.autonomous_pipeline import _are_characters_ready


def test_character_guard_single_character_blocked(novel_factory):
    novel_id = novel_factory(title="單一角色測試小說", genre="玄幻", style="無敵流")

    # 1. 保存完整世界觀
    wb_data = {
        "theme": "宿命反抗",
        "main_conflict": "凡人與古神契約的撕裂",
        "worldview": "以神紋為力量本源的浩瀚大世界",
        "macro_outline": "從底層崛起打破神界專制",
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_data, ensure_ascii=False), validate=False)

    # 2. 存入僅有 1 位主角
    single_char = {
        "characters": [
            {
                "name": "主角林夜",
                "role": "protagonist",
                "archetype": "孤勇者",
                "goal": "向神明復仇",
                "core_trait": "冷靜隱忍",
                "arc": "從棋子蛻變為執棋者",
            }
        ]
    }
    db.save_characters(novel_id, json.dumps(single_char, ensure_ascii=False))

    # 診斷報告應嚴正阻斷
    char_diag = diagnose_characters(novel_id)
    assert "數量嚴重不足" in char_diag
    assert "嚴禁放行" in char_diag

    # 階段偵測必須停留在 characters，不得跳至 foreshadowing
    stage = detect_current_stage(novel_id)
    assert stage == "characters", f"Expected 'characters', got '{stage}'"

    # 自主流水線必須判定角色未就緒
    assert _are_characters_ready(novel_id) is False

    # 總監若決策 CONTINUE 到後續階段，必須被剛性攔截要求自癒
    decision_approve = {
        "action": "CONTINUE",
        "target": "foreshadowing",
        "hint": "準備生成伏筆 [BATCH: foreshadowing_seeds]",
        "reason": "誤以為1個角色足夠放行",
        "agent_prompt": "請生成伏筆",
    }
    needs_recovery = _director_decision_needs_recovery(
        decision_approve, current_stage="characters", novel_id=novel_id
    )
    assert needs_recovery is True

    err_msg = _get_director_decision_error_message(
        decision_approve, json.dumps(decision_approve), current_stage="characters", novel_id=novel_id
    )
    assert "角色階段放行阻斷" in err_msg
    assert "主要對立反派/宿敵" in err_msg

    # 3. 補充第 2 位角色（主要反派/宿敵）
    two_chars = {
        "characters": [
            {
                "name": "主角林夜",
                "role": "protagonist",
                "archetype": "孤勇者",
                "goal": "向神明復仇",
                "core_trait": "冷靜隱忍",
                "arc": "從棋子蛻變為執棋者",
            },
            {
                "name": "神殿主祭羅淵",
                "role": "antagonist",
                "archetype": "狂熱信徒",
                "goal": "將整座城池獻祭以迎真神",
                "core_trait": "傲慢冷酷",
                "arc": "執迷不悟走向自毀",
            },
        ]
    }
    db.save_characters(novel_id, json.dumps(two_chars, ensure_ascii=False))

    # 診斷報告不再出現阻斷標籤
    char_diag_2 = diagnose_characters(novel_id)
    assert "嚴禁放行" not in char_diag_2

    # 階段偵測可前進至 foreshadowing
    stage_2 = detect_current_stage(novel_id)
    assert stage_2 == "foreshadowing"

    # 自主流水線判定角色就緒
    assert _are_characters_ready(novel_id) is True

    # 總監決策此時不再因角色數量被攔截
    needs_recovery_2 = _director_decision_needs_recovery(
        decision_approve, current_stage="characters", novel_id=novel_id
    )
    assert needs_recovery_2 is False