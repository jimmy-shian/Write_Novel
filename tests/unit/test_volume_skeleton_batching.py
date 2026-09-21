# -*- coding: utf-8 -*-
"""
篇卷骨架批次生成單元測試：
- 批次提示詞建構（全卷大綱、批次標示、前文脈絡）
- 批次章節就緒判定
- handler 批次章節索引抽取
- planner 端到端（mock LLM 串流）
"""
import json
import uuid

from backend import persistence as db
from backend.agents.volume_skeleton.prompts import build_volume_skeleton_planner_messages
from backend.services.autonomous_pipeline import _are_batch_chapters_ready


def test_volume_skeleton_batch_prompt_construction():
    novel_id = f"test_batch_{uuid.uuid4()}"
    current_vol = {
        "volume_index": 1,
        "title": "深井伏雷，核彈在袖",
        "summary": "主角在底層黑市隱忍苟活，暗中施展天災禁咒，瓦解財閥清剿。",
        "conflict_archetype": "暗流隱忍與底層求生",
        "anti_template": "本卷嚴禁治安廳過場審訊超過1次",
        "chapter_count": 48,
        "factions": ["治安總署", "九大氏族", "深井黑市"],
    }
    
    prior_context = "【本卷前文已規劃章節骨架（已連續生成至第 8 章）】\n- 第 8 章《倉庫湮滅》：主角彈指蒸發倉庫 | 活躍人物: ['林夜'] | 結尾懸念: 警報徹夜鳴響"

    msgs = build_volume_skeleton_planner_messages(
        worldview_text="現代魔法都市世界觀",
        volume_index=1,
        current_vol=current_vol,
        start_ch=9,
        end_ch=16,
        vol_chapter_count=8,
        surrounding_context="既有角色名冊",
        precalc_clues="伏筆轉折任務表",
        user_prompt="請生成第 1 卷第 9-16 章骨架",
        novel_id=novel_id,
        total_volume_chapters=48,
        vol_start_ch=1,
        vol_end_ch=48,
        prior_chapters_context=prior_context,
        batch_num=2,
        total_batches=6,
    )

    user_content = msgs[1]["content"]
    # 驗證包含全卷大綱與設定
    assert "深井伏雷，核彈在袖" in user_content
    assert "暗流隱忍與底層求生" in user_content
    assert "本卷嚴禁治安廳過場審訊超過1次" in user_content
    assert "全卷共 48 章" in user_content

    # 驗證包含當前批次明確標示
    assert "第 9 章 至 第 16 章" in user_content
    assert "2/6" in user_content

    # 驗證包含前文已生成章節脈絡
    assert "第 8 章《倉庫湮滅》" in user_content
    assert "倉庫湮滅" in user_content


def test_are_batch_chapters_ready():
    novel_id = f"test_are_batch_{uuid.uuid4()}"
    db.create_novel(novel_id, "批次測試小說", "玄幻", "熱血")

    try:
        vol_data = [
            {
                "volume_index": 1,
                "title": "第一卷",
                "chapter_count": 16,
                "chapters_outline": [
                    {"chapter_index": i, "chapter_title": f"第{i}章", "chapter_summary": f"第{i}章摘要"}
                    for i in range(1, 9)
                ]
            }
        ]
        db.save_volumes(novel_id, vol_data)

        # 批次 1 (1-8章) 應已就緒
        assert _are_batch_chapters_ready(novel_id, 1, list(range(1, 9))) is True

        # 批次 2 (9-16章) 尚未就緒
        assert _are_batch_chapters_ready(novel_id, 1, list(range(9, 17))) is False

        # 跨批次檢查應為 False
        assert _are_batch_chapters_ready(novel_id, 1, [7, 8, 9]) is False

    finally:
        db.delete_novel(novel_id)


def test_handler_extracts_batch_target_chapter_indexes():
    from backend.generation.routing.schema import GenerationTaskRequest, GenerationTaskTarget
    from backend.generation.handlers.volume_skeleton_handler import run_volume_skeleton_task
    from unittest.mock import patch

    task = GenerationTaskRequest(
        novel_id="test_nov_123",
        stage="volume_skeleton",
        task_type="generate",
        target=GenerationTaskTarget(
            volume_index=1,
            batch_indexes=[1, 2, 3, 4, 5, 6, 7, 8],
            start_chapter=1,
            end_chapter=8,
        )
    )

    with patch("backend.generation.handlers.volume_skeleton_handler.run_volume_skeleton_planner") as mock_planner:
        run_volume_skeleton_task(task)
        assert mock_planner.called
        call_kwargs = mock_planner.call_args.kwargs
        assert call_kwargs.get("volume_index") == 1
        assert call_kwargs.get("target_chapter_indexes") == [1, 2, 3, 4, 5, 6, 7, 8]


def test_run_volume_skeleton_planner_no_unbound_variable():
    from backend.agents.volume_skeleton.runner import run_volume_skeleton_planner
    from unittest.mock import patch

    novel_id = f"test_skel_{uuid.uuid4()}"
    db.create_novel(novel_id, "測試骨架", "玄幻", "熱血")

    try:
        db.save_characters(novel_id, {
            "characters": [
                {"name": "林夜", "role": "protagonist", "summary": "主角"},
                {"name": "蘇輕雪", "role": "deuteragonist", "summary": "配角"},
            ]
        })
        db.save_worldbuilding(novel_id, json.dumps({
            "theme": "底層反叛",
            "main_conflict": "壟斷與反壟斷",
            "worldview": "魔導都市",
            "macro_outline": "主角反擊",
            "foreshadowing_seeds": [],
            "key_turning_points": []
        }), validate=False)
        db.save_volumes(novel_id, [
            {
                "volume_index": 1,
                "title": "廢柴的微風與天災的序曲",
                "chapter_count": 16,
                "summary": "第一卷概要",
                "chapters_outline": [],
            }
        ])

        mock_chapters_resp = json.dumps({
            "chapters": [
                {
                    "chapter_index": i,
                    "chapter_title": f"第{i}章 測試",
                    "chapter_summary": f"第{i}章情節概要",
                    "characters_active": ["林夜"],
                    "cliffhanger": "局勢懸念",
                    "allocated_tasks": {
                        "foreshadowing_plants": [],
                        "foreshadowing_payoffs": [],
                        "turning_points": []
                    }
                }
                for i in range(1, 9)
            ]
        }, ensure_ascii=False)

        mock_chunk = f"data: {json.dumps({'type': 'content', 'delta': mock_chapters_resp})}\n\n"
        done_chunk = f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch("backend.agents.volume_skeleton.runner.call_llm_stream", return_value=[mock_chunk, done_chunk]):
            gen = run_volume_skeleton_planner(
                novel_id=novel_id,
                volume_index=1,
                target_chapter_indexes=[1, 2, 3, 4, 5, 6, 7, 8],
            )
            events = list(gen)
            assert len(events) > 0

        # 驗證章節已成功寫入 DB
        vols = db.get_volumes(novel_id)
        outline = vols[0].get("chapters_outline") or []
        assert len(outline) == 8
        assert outline[0]["chapter_index"] == 1
        assert outline[7]["chapter_index"] == 8

    finally:
        db.delete_novel(novel_id)

