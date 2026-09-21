# -*- coding: utf-8 -*-
"""
backend.services.incremental_patch.engine 單元測試：
- clean_json_text / parse_incremental_response（LLM 輸出清理）
- validate_incremental_payload（各 target_section 結構校驗）
- filter_and_sanitize_content（品質防禦過濾）
- smart_merge_worldbuilding（防覆蓋合併）
- validate_and_merge_incremental_patch（DB 端到端）
"""
import json

from backend import persistence as db
from backend.services.incremental_patch.engine import (
    clean_json_text,
    parse_incremental_response,
    validate_incremental_payload,
    filter_and_sanitize_content,
    smart_merge_worldbuilding,
    validate_and_merge_incremental_patch,
)


# --- clean_json_text / parse_incremental_response ---

def test_clean_json_text_extracts_codeblock():
    text = '說明文字\n```json\n{"a": 1}\n```\n結尾'
    assert clean_json_text(text) == '{"a": 1}'


def test_clean_json_text_wraps_braceless_kv():
    assert clean_json_text('"theme": "測試"') == '{"theme": "測試"}'


def test_clean_json_text_passthrough_valid_json():
    raw = '{"note": "時間: 12:30, 地點: 北門"}'
    assert clean_json_text(raw) == raw


def test_parse_incremental_response_variants():
    assert parse_incremental_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_incremental_response({"a": 1}) == {"a": 1}
    assert parse_incremental_response("") is None
    assert parse_incremental_response("完全無法解析") is None


# --- validate_incremental_payload ---

def test_validate_worldbuilding_payload_whitelist():
    ok, err = validate_incremental_payload("worldbuilding", {"theme": "新主題"})
    assert ok is True
    ok, err = validate_incremental_payload("worldbuilding", {"hacker_key": "x"})
    assert ok is False and "Unauthorized" in err
    ok, err = validate_incremental_payload("worldbuilding", ["not", "a", "dict"])
    assert ok is False


def test_validate_characters_append_requires_name():
    ok, _ = validate_incremental_payload("characters", {"characters": [{"name": "林夜"}]}, action="APPEND")
    assert ok is True
    ok, err = validate_incremental_payload("characters", {"characters": [{"role": "配角"}]}, action="APPEND")
    assert ok is False and "name" in err


def test_validate_characters_patch_field_whitelist():
    # alias 欄位 backstory 應正規化為 background 後通過
    ok, err = validate_incremental_payload(
        "characters", {"value": "冷靜"}, action="PATCH",
        extra_params={"field_name": "backstory"},
    )
    assert ok is True
    ok, err = validate_incremental_payload(
        "characters", {"value": "x"}, action="PATCH", extra_params={"field_name": "not_allowed_field"}
    )
    assert ok is False and "whitelist" in err


def test_validate_volumes_payload():
    ok, _ = validate_incremental_payload("volumes", {"volumes": [{"volume_index": 1, "title": "第一卷"}]})
    assert ok is True
    ok, err = validate_incremental_payload("volumes", {"volumes": [{"title": "缺索引"}]})
    assert ok is False and "volume_index" in err
    ok, err = validate_incremental_payload("volumes", {"volumes": [{"volume_index": "abc"}]})
    assert ok is False


# --- filter_and_sanitize_content ---

def test_filter_blocks_placeholders_and_boilerplates():
    ok, err = filter_and_sanitize_content("worldbuilding", {"worldview": "待補充"})
    assert ok is False and "待補充" in err
    ok, err = filter_and_sanitize_content("chapters", {"chapters": [{"title": "推進核心衝突"}]})
    assert ok is False and "模板" in err
    ok, err = filter_and_sanitize_content("worldbuilding", {"worldview": "具體實質的世界觀描述內容"})
    assert ok is True


def test_filter_blocks_short_summaries_and_repeated_titles():
    ok, err = filter_and_sanitize_content("chapters", {"chapters": [{"chapter_summary": "短"}]})
    assert ok is False and "過短" in err
    repeated = {"chapters": [{"title": "同一標題"}, {"title": "同一標題"}, {"title": "同一標題"}]}
    ok, err = filter_and_sanitize_content("chapters", repeated)
    assert ok is False and "語意退化" in err


# --- smart_merge_worldbuilding ---

def test_smart_merge_never_overwrites_with_empty():
    current = {"theme": "原有主題", "worldview": "原有世界觀", "foreshadowing_seeds": [{"id": 1}]}
    patch = {"theme": "", "worldview": "無", "foreshadowing_seeds": [{"id": 2}]}
    merged = smart_merge_worldbuilding(current, patch)
    assert merged["theme"] == "原有主題"
    assert merged["worldview"] == "原有世界觀"
    # 種子為增量合併而非覆蓋
    assert merged["foreshadowing_seeds"] == [{"id": 1}, {"id": 2}]


def test_smart_merge_converts_dict_to_structure():
    current = {"multi_act_structure": []}
    patch = {"multi_act_structure": {"act1": "開幕", "act2": "對抗", "act3": "收尾"}}
    merged = smart_merge_worldbuilding(current, patch)
    acts = merged["multi_act_structure"]
    assert len(acts) == 3
    assert acts[0]["content"] == "開幕"
    assert "第一幕" in acts[0]["title"]


# --- validate_and_merge_incremental_patch (DB 端到端) ---

def test_validate_and_merge_incremental_patch_end_to_end(novel_factory):
    novel_id = novel_factory(title="增量補丁端到端")
    db.save_worldbuilding(novel_id, json.dumps({
        "theme": "原主題", "main_conflict": "原衝突", "worldview": "原世界觀",
        "macro_outline": "原大綱", "foreshadowing_seeds": [], "key_turning_points": [],
    }, ensure_ascii=False), validate=False)

    ok, version, err = validate_and_merge_incremental_patch(
        novel_id, "worldbuilding", "PATCH",
        {"theme": "升級後主題", "foreshadowing_seeds": [{"id": 1, "name": "新種子"}]},
    )
    assert ok is True, err
    wb = db.get_latest_worldbuilding(novel_id)
    parsed = db.parse_worldview_to_json(wb["content"])
    assert parsed["theme"] == "升級後主題"
    # 未提供的欄位不可消失
    assert parsed["worldview"] == "原世界觀"
    assert parsed["foreshadowing_seeds"] == [{"id": 1, "name": "新種子"}]

    # 品質攔截：含佔位符的補丁必須被擋下
    ok, _, err = validate_and_merge_incremental_patch(
        novel_id, "worldbuilding", "PATCH", {"main_conflict": "待補充"},
    )
    assert ok is False and "品質攔截" in err