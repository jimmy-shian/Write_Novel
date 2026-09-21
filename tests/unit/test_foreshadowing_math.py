# -*- coding: utf-8 -*-
"""
伏筆配置數學與藍圖單元測試：
- chapter_math 純函式（卷章區間換算，無 DB）
- blueprint 純函式（canonical id、配對正規化、藍圖驗證）
- 藍圖預計算與 canonical task map（DB 整合）
"""
import json

from backend import persistence as db
from backend.services.foreshadowing.chapter_math import (
    get_clean_chapter_count,
    get_volume_chapter_range,
    get_chapter_volume_index,
    get_total_chapter_count,
)
from backend.services.foreshadowing.blueprint import (
    canonical_seed_id,
    coerce_int,
    normalize_allocation_pair,
    is_valid_foreshadowing_blueprint,
    build_canonical_foreshadowing_task_map,
    apply_canonical_allocated_tasks_to_chapters,
    get_global_foreshadowing_blueprint,
)


# --- chapter_math 純函式 ---

def test_get_clean_chapter_count():
    assert get_clean_chapter_count({"chapter_count": 12}) == 12
    assert get_clean_chapter_count({"chapter_count": 0}) == 50
    assert get_clean_chapter_count({"chapter_count": "abc"}) == 50
    assert get_clean_chapter_count(None) == 50
    assert get_clean_chapter_count({}, default=7) == 7


def test_get_volume_chapter_range():
    volumes = [
        {"volume_index": 1, "chapter_count": 10},
        {"volume_index": 2, "chapter_count": 20},
    ]
    assert get_volume_chapter_range(volumes, 1) == (1, 10)
    assert get_volume_chapter_range(volumes, 2) == (11, 30)
    # 超出範圍：以最後一卷 chapter_count（20）外推
    assert get_volume_chapter_range(volumes, 3) == (31, 50)
    # 空卷列表：預設每卷 50 章
    assert get_volume_chapter_range([], 2) == (51, 100)


def test_get_chapter_volume_index():
    volumes = [
        {"volume_index": 1, "chapter_count": 10},
        {"volume_index": 2, "chapter_count": 20},
    ]
    assert get_chapter_volume_index(volumes, 1) == 1
    assert get_chapter_volume_index(volumes, 10) == 1
    assert get_chapter_volume_index(volumes, 11) == 2
    assert get_chapter_volume_index(volumes, 30) == 2
    # 超出：以最後一卷 chapter_count 外推
    assert get_chapter_volume_index(volumes, 31) == 3
    # 空卷列表：每 50 章一卷
    assert get_chapter_volume_index([], 55) == 2


def test_get_total_chapter_count():
    assert get_total_chapter_count([{"chapter_count": 10}, {"chapter_count": 20}]) == 30
    assert get_total_chapter_count([]) == 1000
    assert get_total_chapter_count(None) == 1000


# --- blueprint 純函式 ---

def test_canonical_seed_id_and_coerce_int():
    assert canonical_seed_id(0) == "FS001"
    assert canonical_seed_id(9) == "FS010"
    assert canonical_seed_id(99) == "FS100"
    assert coerce_int("12", 0) == 12
    assert coerce_int("abc", 5) == 5
    assert coerce_int(None, -1) == -1


def test_normalize_allocation_pair():
    # 正常配對
    assert normalize_allocation_pair([3, 10], 20) == (3, 10)
    # 非法輸入
    assert normalize_allocation_pair(None, 20) is None
    assert normalize_allocation_pair([1], 20) is None
    # 無法轉 int 的值以 0 帶入後被夾限為 (1, 2)
    assert normalize_allocation_pair(["x", "y"], 20) == (1, 2)
    # 超界裁切
    assert normalize_allocation_pair([0, 99], 20) == (1, 20)
    # payoff <= plant 時強制拉開
    assert normalize_allocation_pair([10, 10], 20) == (10, 11)
    assert normalize_allocation_pair([15, 3], 20) == (15, 16)
    # total_chapters <= 0 時以配對自推
    assert normalize_allocation_pair([5, 8], 0) == (5, 8)


def test_is_valid_foreshadowing_blueprint():
    valid = {
        "foreshadowing_allocations": [[1, 5], [2, 8]],
        "turning_allocations": [3, 7],
    }
    assert is_valid_foreshadowing_blueprint(valid, 2, 2, 10) is True
    # 數量不符
    assert is_valid_foreshadowing_blueprint(valid, 3, 2, 10) is False
    # 非法結構
    assert is_valid_foreshadowing_blueprint(None, 2, 2, 10) is False
    # 無法正規化的配對（長度不足）
    bad = {"foreshadowing_allocations": [[5], [2, 8]], "turning_allocations": [3, 7]}
    assert is_valid_foreshadowing_blueprint(bad, 2, 2, 10) is False
    # 轉折點超出章節範圍
    bad_turn = {"foreshadowing_allocations": [[1, 5], [2, 8]], "turning_allocations": [3, 99]}
    assert is_valid_foreshadowing_blueprint(bad_turn, 2, 2, 10) is False


# --- DB 整合 ---

def test_canonical_task_map_and_apply(novel_factory):
    novel_id = novel_factory(title="伏筆藍圖測試")
    db.save_volumes(novel_id, [
        {"volume_index": 1, "title": "第一卷", "chapter_count": 10},
        {"volume_index": 2, "title": "第二卷", "chapter_count": 10},
    ])
    db.save_worldbuilding(novel_id, json.dumps({
        "theme": "測試",
        "main_conflict": "衝突",
        "worldview": "世界",
        "macro_outline": "大綱",
        "foreshadowing_seeds": [{"id": 1, "name": "種子一"}, {"id": 2, "name": "種子二"}],
        "key_turning_points": [{"id": 1, "name": "轉折一"}],
    }, ensure_ascii=False), validate=False)

    blueprint = get_global_foreshadowing_blueprint(novel_id)
    assert blueprint["T"] == 20
    assert len(blueprint["foreshadowing_allocations"]) == 2
    assert len(blueprint["turning_allocations"]) == 1
    # 決定論：同 novel_id 重取必須一致（經 JSON 往返正規化 tuple/list 差異）
    assert json.loads(json.dumps(blueprint)) == get_global_foreshadowing_blueprint(novel_id)

    task_map = build_canonical_foreshadowing_task_map(novel_id)
    # 每顆種子恰好一個 plant 與一個 payoff
    plants = [sid for tasks in task_map.values() for sid in tasks["foreshadowing_plants"]]
    payoffs = [sid for tasks in task_map.values() for sid in tasks["foreshadowing_payoffs"]]
    assert sorted(plants) == ["FS001", "FS002"]
    assert sorted(payoffs) == ["FS001", "FS002"]
    # 轉折點
    tps = [tp for tasks in task_map.values() for tp in tasks["turning_points"]]
    assert tps == ["TP001"]

    # apply：覆寫章節 allocated_tasks 並清除殘留鍵
    chapters = [
        {"chapter_index": 1, "chapter_title": "開端", "allocated_tasks": {"foreshadowing_plants": ["FS999"]}},
        {"chapter_index": 2, "chapter_title": "發展", "foreshadowing": "殘留欄位"},
    ]
    normalized = apply_canonical_allocated_tasks_to_chapters(novel_id, chapters)
    assert set(normalized.keys()) == {1, 2}
    ch1 = normalized[1]
    assert ch1["allocated_tasks"]["foreshadowing_plants"] == task_map.get(1, {}).get("foreshadowing_plants", [])
    ch2 = normalized[2]
    assert "foreshadowing" not in ch2
    assert ch2["allocated_tasks"]["foreshadowing_plants"] == task_map.get(2, {}).get("foreshadowing_plants", [])
