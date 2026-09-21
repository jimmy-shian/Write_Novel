# -*- coding: utf-8 -*-
"""
backend.models.parsers 單元測試：
- extract_json_block：markdown 區塊、thinking 標籤、截斷救援
- _salvage_truncated_candidate：回溯補全
- validate_plot_quality：微大綱品質檢核
"""
from backend.models.parsers import (
    extract_json_block,
    _salvage_truncated_candidate,
    validate_plot_quality,
)

# 以拼接方式組出 thinking 標籤，避免測試原始碼本身含該標籤
THINK_OPEN = "<" + "think" + ">"
THINK_CLOSE = "<" + "/think" + ">"


# --- extract_json_block ---

def test_extract_clean_json():
    text = '```json\n{"foo": "bar", "count": 42}\n```'
    assert extract_json_block(text) == {"foo": "bar", "count": 42}


def test_extract_latest_codeblock_when_multiple():
    text = (
        'Here is an attempt:\n'
        '```json\n{"status": "old"}\n```\n'
        'Wait, let me restart and output complete:\n'
        '```json\n{"status": "new", "items": [1, 2, 3]}\n```'
    )
    result = extract_json_block(text)
    assert result.get("status") == "new"
    assert result.get("items") == [1, 2, 3]


def test_extract_strips_thinking_tags():
    text = (
        f'{THINK_OPEN}內部推理過程 {"x" * 100} {THINK_CLOSE}\n'
        '```json\n{"answer": 1}\n```'
    )
    assert extract_json_block(text) == {"answer": 1}


def test_extract_empty_returns_empty_dict():
    assert extract_json_block("") == {}
    assert extract_json_block(None) == {}


def test_salvage_unclosed_codeblock():
    text = (
        'Here is the JSON:\n'
        '```json\n'
        '{\n'
        '  "foreshadowing_seeds": [\n'
        '    {"seed_id": "FS_01", "title": "伏筆A"},\n'
        '    {"seed_id": "FS_02", "title": "伏筆B"}\n'
        '  ]\n'
    )
    extracted = extract_json_block(text)
    assert isinstance(extracted, dict)
    assert len(extracted["foreshadowing_seeds"]) == 2
    assert extracted["foreshadowing_seeds"][1]["seed_id"] == "FS_02"


# --- _salvage_truncated_candidate ---

def test_salvage_truncated_array_in_object():
    truncated = (
        '{\n'
        '  "key_turning_points": [\n'
        '    {"id": "TP_01", "name": "轉折點一"},\n'
        '    {"id": "TP_02", "name": "轉折點二"},\n'
        '    {"id": "TP_03", "name": "未完成的轉折'
    )
    salvaged = _salvage_truncated_candidate(truncated)
    assert isinstance(salvaged, dict)
    assert "key_turning_points" in salvaged
    # 第三筆截斷項應被回溯捨棄或成功補全
    assert len(salvaged["key_turning_points"]) in (2, 3)
    assert salvaged["key_turning_points"][0]["id"] == "TP_01"
    assert salvaged["key_turning_points"][1]["id"] == "TP_02"


def test_salvage_backtrack_discarding_incomplete_item():
    truncated = (
        '{\n'
        '  "seeds": [\n'
        '    {"id": "S1", "val": 100},\n'
        '    {"id": "S2", "val": 200},\n'
        '    {"id": "S3", "val":\n'
    )
    salvaged = _salvage_truncated_candidate(truncated)
    assert isinstance(salvaged, dict)
    assert len(salvaged["seeds"]) == 2
    assert salvaged["seeds"][0]["id"] == "S1"
    assert salvaged["seeds"][1]["id"] == "S2"


def test_salvage_root_array_backtrack():
    truncated = '[{"id": 1}, {"id": 2}, {"id": 3, "val":'
    salvaged = _salvage_truncated_candidate(truncated)
    assert isinstance(salvaged, list)
    assert len(salvaged) == 2
    assert salvaged[0]["id"] == 1
    assert salvaged[1]["id"] == 2


def test_salvage_none_on_garbage():
    assert _salvage_truncated_candidate("") is None
    assert _salvage_truncated_candidate("完全不是 JSON 的文字") is None


# --- validate_plot_quality ---

def test_validate_plot_quality_pass():
    plot = {"events": [{"scene": "主角潛入檔案室搜查線索", "consequence": "驚動了巡邏警衛"}]}
    assert validate_plot_quality(plot) is True


def test_validate_plot_quality_failures():
    assert validate_plot_quality(None) is False
    assert validate_plot_quality({}) is False
    assert validate_plot_quality({"events": []}) is False
    # scene 過短
    assert validate_plot_quality({"events": [{"scene": "太短", "consequence": "足夠長的後果描述"}]}) is False
    # consequence 過短
    assert validate_plot_quality({"events": [{"scene": "足夠長的場景描述", "consequence": "短"}]}) is False
    # 非字串欄位
    assert validate_plot_quality({"events": [{"scene": 123, "consequence": "足夠長的後果描述"}]}) is False