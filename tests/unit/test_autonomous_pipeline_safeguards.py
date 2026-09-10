# -*- coding: utf-8 -*-
import json
import uuid
import pytest

from backend import persistence as db
from backend.services.autonomous_pipeline import (
    _is_worldview_ready,
    _are_characters_ready,
    _are_seeds_ready,
    _are_turning_points_ready,
    _are_volumes_ready,
)


def test_validation_helpers_with_empty_and_substantive_data():
    novel_id = f"test_valid_{uuid.uuid4()}"
    db.create_novel(novel_id, "測試驗證小說", "仙俠", "古典")

    # 1. 初始空狀態校驗
    assert _is_worldview_ready(novel_id) is False
    assert _are_characters_ready(novel_id) is False
    assert _are_seeds_ready(novel_id) is False
    assert _are_turning_points_ready(novel_id) is False
    assert _are_volumes_ready(novel_id) is False

    # 2. 存入空白模板 JSON，確認仍判定為 False
    empty_wb = {
        "theme": "",
        "main_conflict": "",
        "worldview": "",
        "macro_outline": "",
        "multi_act_structure": [],
        "progressive_character_plan": [],
        "foreshadowing_seeds": [],
        "key_turning_points": [],
    }
    db.save_worldbuilding(novel_id, json.dumps(empty_wb, ensure_ascii=False), validate=False)
    assert _is_worldview_ready(novel_id) is False

    # 3. 存入實質世界觀內容，確認判定為 True
    valid_wb = dict(empty_wb)
    valid_wb["worldview"] = "這是一個充滿靈氣復甦與上古仙魔殘存法則的宏大修仙大世界，凡人亦可藉由功法登天。"
    db.save_worldbuilding(novel_id, json.dumps(valid_wb, ensure_ascii=False), validate=False)
    assert _is_worldview_ready(novel_id) is True

    # 4. 角色庫校驗：佔位符角色應判定為 False
    placeholder_chars = {
        "characters": [
            {"name": "新登場的次要角色", "role": "配角"},
            {"name": "待補充", "role": "路人"},
        ]
    }
    db.save_characters(novel_id, json.dumps(placeholder_chars, ensure_ascii=False))
    assert _are_characters_ready(novel_id) is False

    # 5. 角色庫存入實質角色，判定為 True
    real_chars = {
        "characters": [
            {"name": "沈青雲", "role": "主角", "personality": "沉著冷靜，謀定而後動"},
            {"name": "林婉兒", "role": "女主角", "personality": "靈動活潑，天生劍心"},
        ]
    }
    db.save_characters(novel_id, json.dumps(real_chars, ensure_ascii=False))
    assert _are_characters_ready(novel_id) is True

    # 清理
    db.delete_novel(novel_id)


def test_reset_novel_content():
    novel_id = f"test_reset_{uuid.uuid4()}"
    prompt_text = "這是一段測試用的大綱靈感故事簡述。"
    db.create_novel(novel_id, "測試重置小說", "玄幻", "史詩")
    db.update_novel_pipeline_prompt(novel_id, prompt_text)

    # 寫入生成資料
    wb_data = {
        "theme": "主題測試內容足夠長以便驗證實質內容存在",
        "worldview": "世界觀測試內容足夠長以便驗證實質內容存在",
        "macro_outline": "宏觀大綱內容足夠長以便驗證實質內容存在",
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_data, ensure_ascii=False), validate=False)
    db.save_characters(novel_id, json.dumps({"characters": [{"name": "主角A"}]}, ensure_ascii=False))
    db.save_chapter(novel_id, 1, "這是第一章正文內容，字數超過五十個字以符合測試標準與資料庫檢驗門檻要求。")
    db.save_volumes(novel_id, [{"volume_index": 1, "title": "第一卷", "chapter_count": 10}])

    # 驗證資料存在
    assert db.get_latest_worldbuilding(novel_id) is not None
    assert db.get_latest_characters(novel_id) is not None
    assert len(db.get_chapters(novel_id)) == 1
    assert len(db.get_volumes(novel_id)) == 1

    # 執行清空重置
    db.reset_novel_content(novel_id)

    # 驗證生成資料全數被清空
    assert db.get_latest_worldbuilding(novel_id) is None
    assert db.get_latest_characters(novel_id) is None
    assert len(db.get_chapters(novel_id)) == 0
    assert len(db.get_volumes(novel_id)) == 0

    # 驗證小說基本資料與 pipeline_prompt 依然完整保留
    novel = db.get_novel(novel_id)
    assert novel is not None
    assert novel["title"] == "測試重置小說"
    assert novel["pipeline_prompt"] == prompt_text

    # 清理
    db.delete_novel(novel_id)


def test_autonomous_pipeline_get_status_isolation():
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, NovelPipelineTask

    mgr = AutonomousPipelineManager()
    
    # 模擬小說 A 正在背景自主寫作中
    task_a = NovelPipelineTask("novel_A", "小說A")
    task_a.is_running = True
    task_a.current_chapter = 5
    task_a.status_message = "正在撰寫第 5 章"
    mgr.tasks["novel_A"] = task_a

    try:
        # 1. 前端查詢小說 A：應取得小說 A 的 running 狀態
        res_a = mgr.get_status("novel_A")
        assert res_a["novel_id"] == "novel_A"
        assert res_a["is_running"] is True
        assert res_a["current_chapter"] == 5
        assert res_a["active_tasks_count"] == 1

        # 2. 前端切換至小說 B (未運行)：絕對不能回傳小說 A 的狀態！
        res_b = mgr.get_status("novel_B")
        assert res_b["novel_id"] == "novel_B"
        assert res_b["is_running"] is False
        assert res_b["status_message"] == "未運行"
        # 但 active_tasks 應包含小說 A，供前端多工顯示背景狀態
        assert res_b["active_tasks_count"] == 1
        assert res_b["active_tasks"][0]["novel_id"] == "novel_A"

        # 3. 前端全域查詢 (None)：應回傳當前正在運行的任務 (小說 A)
        res_global = mgr.get_status(None)
        assert res_global["novel_id"] == "novel_A"
        assert res_global["is_running"] is True

    finally:
        # 清理測試狀態
        task_a.is_running = False
        mgr.tasks.pop("novel_A", None)

