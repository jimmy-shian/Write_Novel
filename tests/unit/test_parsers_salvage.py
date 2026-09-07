import pytest
from backend.models.parsers import extract_json_block, _salvage_truncated_candidate


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


def test_salvage_truncated_array_in_object():
    # Emulates Gemini cutting off mid-stream in an item of key_turning_points
    # The third item is cut off mid-key/value so backtracking discards it
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
    # Either successfully closed or cleanly backtracked to 2 items
    assert len(salvaged["key_turning_points"]) in (2, 3)
    assert salvaged["key_turning_points"][0]["id"] == "TP_01"
    assert salvaged["key_turning_points"][1]["id"] == "TP_02"


def test_salvage_backtrack_discarding_incomplete_item():
    # Incomplete item with broken syntax that cannot be closed by simple quotes
    truncated = (
        '{\n'
        '  "seeds": [\n'
        '    {"id": "S1", "val": 100},\n'
        '    {"id": "S2", "val": 200},\n'
        '    {"id": "S3", "val":\n'
    )
    salvaged = _salvage_truncated_candidate(truncated)
    assert isinstance(salvaged, dict)
    assert "seeds" in salvaged
    assert len(salvaged["seeds"]) == 2
    assert salvaged["seeds"][0]["id"] == "S1"
    assert salvaged["seeds"][1]["id"] == "S2"


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


def test_salvage_root_array_backtrack():
    # Array with an item cut off mid-colon
    truncated = '[{"id": 1}, {"id": 2}, {"id": 3, "val":'
    salvaged = _salvage_truncated_candidate(truncated)
    assert isinstance(salvaged, list)
    assert len(salvaged) == 2
    assert salvaged[0]["id"] == 1
    assert salvaged[1]["id"] == 2
