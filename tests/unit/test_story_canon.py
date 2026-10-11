import pytest

from backend.services.narrative.story_canon import (
    build_canon_context,
    compare_timeline_anchors,
    ensure_timeline_anchors,
    normalize_timeline_anchor,
    validate_life_contract,
    validate_timeline,
    get_life_status_at_chapter,
)
from backend import persistence as db


def test_structured_timeline_detects_date_regression():
    volumes = [{
        "chapters_outline": [
            {"chapter_index": 1, "timeline_anchor": {"date": "0312-03-16", "time_of_day": "afternoon"}},
            {"chapter_index": 2, "timeline_anchor": {"date": "0312-03-12", "time_of_day": "morning"}},
        ]
    }]
    issues = validate_timeline(volumes)
    assert len(issues) == 1
    assert issues[0]["severity"] == "critical"


def test_legacy_month_day_text_detects_date_regression():
    issues = validate_timeline([{
        "chapters_outline": [
            {"chapter_index": 1, "time_setting": "3 月 16 日 下午"},
            {"chapter_index": 2, "time_setting": "3 月 12 日 上午"},
        ]
    }])
    assert issues and issues[0]["dimension"] == "timeline"


def test_same_date_sequence_is_comparable():
    first = normalize_timeline_anchor({"date": "0312-03-16", "time_of_day": "afternoon", "sequence": 2}, 1)
    second = normalize_timeline_anchor({"date": "0312-03-16", "time_of_day": "afternoon", "sequence": 1}, 2)
    assert compare_timeline_anchors(first, second)


def test_canon_context_allows_planned_death_and_resurrection():
    text = build_canon_context({
        "timeline_anchor": {"date": "0312-03-16", "time_of_day": "evening"},
        "planned_events": [{"event_type": "resurrection", "character": "塞拉菲娜", "reason": "靈魂容器"}],
    }, 10, [{"name": "塞拉菲娜", "life_status": "dead"}])
    assert "resurrection" in text
    assert "死亡與復活均可發生" in text


def test_legacy_free_text_does_not_create_false_structured_date():
    assert normalize_timeline_anchor("承接前章時間線", 3) is None


def test_graph_extractor_cannot_rewrite_established_life_status():
    novel_id = "test_story_canon_extractor"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "canon", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "拜蒙", "character", life_status="dead", chapter_index=3)
        observed = db.upsert_entity(
            novel_id, "拜蒙", "character", life_status="alive", chapter_index=8, source="extractor"
        )
        assert observed["life_status"] == "dead"
    finally:
        db.delete_novel(novel_id)


def test_missing_timeline_anchors_are_deterministically_filled():
    result = ensure_timeline_anchors([
        {"chapter_index": 4, "title": "甲"},
        {"chapter_index": 5, "title": "乙"},
    ])
    assert result[0]["timeline_anchor"]["story_day"] == 0
    assert result[1]["timeline_anchor"]["sequence"] == 5


def test_planned_and_occurred_story_events_are_separate():
    novel_id = "test_story_event_records"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "events", "fantasy", "classic")
    try:
        planned = db.upsert_story_event(
            novel_id, 8, {"event_type": "resurrection", "character": "塞拉菲娜"}, status="planned"
        )
        occurred = db.upsert_story_event(
            novel_id, 8, {"event_type": "reveal", "character": "塞拉菲娜"}, status="occurred", source="graphiti_observation"
        )
        assert planned["status"] == "planned"
        assert occurred["status"] == "occurred"
        assert len(db.get_story_events(novel_id, status="planned")) == 1
        assert len(db.get_story_events(novel_id, status="occurred")) == 1
    finally:
        db.delete_novel(novel_id)


def test_authorized_resurrection_transition_is_allowed():
    novel_id = "test_story_canon_resurrection"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "resurrection", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "塞拉菲娜", "character", life_status="dead", chapter_index=4)
        result = db.apply_authorized_life_transition(
            novel_id, "塞拉菲娜", "alive", 10, "resurrection", "靈魂容器完成"
        )
        assert result["life_status"] == "alive"
        assert db.get_entities(novel_id)[0]["life_status"] == "alive"
    finally:
        db.delete_novel(novel_id)


def test_multi_character_life_event_commit_is_atomic_on_malformed_event():
    novel_id = "test_story_canon_atomic_commit"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "atomic commit", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "甲", "character", life_status="alive", chapter_index=1)
        db.upsert_entity(novel_id, "乙", "character", life_status="alive", chapter_index=1)
        db.upsert_story_event(
            novel_id, 5,
            {"event_type": "death", "character": ["甲", "乙"], "description": "同一場戰鬥"},
            status="planned",
        )
        # A malformed sibling event must prevent the whole chapter commit.
        db.upsert_story_event(
            novel_id, 5,
            {"event_type": "death", "description": "缺少角色"},
            status="planned",
        )
        from backend.services.narrative.story_canon import advance_story_canon_for_chapter
        result = advance_story_canon_for_chapter(novel_id, 5)
        assert result["issues"]
        assert all(item["life_status"] == "alive" for item in db.get_entities(novel_id))
        assert db.get_story_events(novel_id, chapter_index=5, status="occurred") == []
    finally:
        db.delete_novel(novel_id)


def test_dead_character_without_authorized_revival_is_blocked():
    novel_id = "test_story_canon_life_gate"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "life gate", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "拜蒙", "character", life_status="dead", chapter_index=4)
        issues = validate_life_contract(novel_id, 8, {}, "拜蒙走進大廳，回答了守門人的問題。")
        assert issues
        assert issues[0]["dimension"] == "life_status"
        allowed = validate_life_contract(
            novel_id, 8,
            {"planned_events": [{"event_type": "resurrection", "character": "拜蒙"}]},
            "拜蒙走進大廳，回答了守門人的問題。",
        )
        assert allowed == []
    finally:
        db.delete_novel(novel_id)


def test_alive_character_without_planned_death_is_blocked():
    novel_id = "test_story_canon_unplanned_death"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "unplanned death", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "楚風", "character", life_status="alive", chapter_index=1)
        issues = validate_life_contract(novel_id, 8, {}, "楚風在黑石山戰死，化為齏粉。")
        assert issues and issues[0]["severity"] == "critical"
        allowed = validate_life_contract(
            novel_id,
            8,
            {"planned_events": [{"event_type": "death", "character": "楚風"}]},
            "楚風在黑石山戰死，化為齏粉。",
        )
        assert allowed == []
    finally:
        db.delete_novel(novel_id)


def test_future_authoritative_death_does_not_block_earlier_chapter():
    novel_id = "test_story_canon_future_death"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "future death", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "拜蒙", "character", life_status="dead", chapter_index=247)
        assert get_life_status_at_chapter(novel_id, 8) == {}
        assert validate_life_contract(novel_id, 8, {}, "拜蒙走進大廳，回答了守門人的問題。") == []
    finally:
        db.delete_novel(novel_id)


def test_planned_life_event_becomes_canon_only_at_chapter_commit():
    novel_id = "test_story_canon_schedule_commit"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "schedule", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "拜蒙", "character", life_status="alive", chapter_index=1)
        db.sync_planned_story_events(novel_id, [{
            "chapter_index": 5,
            "planned_events": [{"event_type": "death", "character": "拜蒙", "description": "星隕"}],
        }])
        assert get_life_status_at_chapter(novel_id, 4)["拜蒙"]["life_status"] == "alive"
        assert db.get_entities(novel_id)[0]["life_status"] == "alive"
        db.save_chapter(novel_id, 5, "拜蒙抬頭望向星空。")
        from backend.services.narrative.story_canon import advance_story_canon_for_chapter
        assert not advance_story_canon_for_chapter(novel_id, 5)["issues"]
        assert get_life_status_at_chapter(novel_id, 5)["拜蒙"]["life_status"] == "dead"
        assert db.get_story_events(novel_id, chapter_index=5, status="occurred")[0]["source"] == "story_canon_schedule"
    finally:
        db.delete_novel(novel_id)


def test_graphiti_life_observation_never_becomes_canon():
    novel_id = "test_story_canon_observation_only"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "observation", "fantasy", "classic")
    try:
        db.upsert_entity(novel_id, "拜蒙", "character", life_status="alive", chapter_index=1)
        db.upsert_story_event(
            novel_id, 5, {"event_type": "death", "character": "拜蒙"},
            status="occurred", source="graphiti_observation"
        )
        assert get_life_status_at_chapter(novel_id, 5)["拜蒙"]["life_status"] == "alive"
    finally:
        db.delete_novel(novel_id)


def test_bulk_outline_save_rejects_timeline_regression_before_write():
    novel_id = "test_story_canon_timeline_gate"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "timeline gate", "fantasy", "classic")
    try:
        try:
            db.save_volumes(novel_id, [{
                "volume_index": 1,
                "chapter_count": 2,
                "chapters_outline": [
                    {"chapter_index": 1, "timeline_anchor": {"date": "0312-03-16"}},
                    {"chapter_index": 2, "timeline_anchor": {"date": "0312-03-12"}},
                ],
            }])
        except ValueError as exc:
            assert "時間線" in str(exc)
        else:
            raise AssertionError("timeline regression was persisted")
        assert db.get_volumes(novel_id) == []
    finally:
        db.delete_novel(novel_id)


def test_chapter_patch_path_cannot_bypass_timeline_gate():
    novel_id = "test_story_canon_patch_gate"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "patch gate", "fantasy", "classic")
    try:
        db.save_volumes(novel_id, [{
            "volume_index": 1,
            "chapter_count": 2,
            "chapters_outline": [
                {"chapter_index": 1, "timeline_anchor": {"date": "0312-03-16"}},
                {"chapter_index": 2, "timeline_anchor": {"date": "0312-03-17"}},
            ],
        }])
        with pytest.raises(ValueError):
            db.save_plot_chapters(novel_id, {
                "chapters": [
                    {"chapter_index": 1, "timeline_anchor": {"date": "0312-03-16"}},
                    {"chapter_index": 2, "timeline_anchor": {"date": "0312-03-12"}},
                ]
            }, skip_volume_sync=True)
        saved = db.get_volumes(novel_id)[0]["chapters_outline"]
        assert saved[1]["timeline_anchor"]["date"] == "0312-03-17"
    finally:
        db.delete_novel(novel_id)


def test_chapter_only_outline_requires_canonical_volume_schedule():
    novel_id = "test_story_canon_outline_requires_volume"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "outline volume", "fantasy", "classic")
    try:
        with pytest.raises(ValueError, match="尚未建立篇卷"):
            db.save_plot_chapters(
                novel_id,
                {"chapters": [{"chapter_index": 1, "time_setting": "3 月 16 日"}]},
            )
        assert db.get_volumes(novel_id) == []
    finally:
        db.delete_novel(novel_id)


def test_target_volume_patch_cannot_regress_against_previous_volume():
    novel_id = "test_story_canon_target_volume_gate"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "target volume gate", "fantasy", "classic")
    try:
        db.save_volumes(novel_id, [
            {
                "volume_index": 1,
                "chapter_count": 1,
                "chapters_outline": [
                    {"chapter_index": 1, "timeline_anchor": {"date": "0312-03-16"}},
                ],
            },
            {
                "volume_index": 2,
                "chapter_count": 1,
                "chapters_outline": [
                    {"chapter_index": 2, "timeline_anchor": {"date": "0312-03-17"}},
                ],
            },
        ])
        with pytest.raises(ValueError):
            db.save_volumes(
                novel_id,
                [{
                    "volume_index": 2,
                    "chapter_count": 1,
                    "chapters_outline": [
                        {"chapter_index": 2, "timeline_anchor": {"date": "0312-03-12"}},
                    ],
                }],
                target_vol_idx=2,
            )
        assert db.get_volumes(novel_id)[1]["chapters_outline"][0]["timeline_anchor"]["date"] == "0312-03-17"
    finally:
        db.delete_novel(novel_id)


def test_identical_retry_does_not_create_duplicate_chapter_version():
    novel_id = "test_story_canon_idempotent_save"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "idempotent", "fantasy", "classic")
    try:
        first = db.save_chapter(novel_id, 1, "同一份正文", synopsis="同一摘要")
        second = db.save_chapter(novel_id, 1, "同一份正文", synopsis="同一摘要")
        assert first == second == 1
        assert len(db.get_all_chapters_latest(novel_id)) == 1
    finally:
        db.delete_novel(novel_id)


def test_identical_unresolved_narrative_audit_is_idempotent():
    novel_id = "test_story_audit_idempotency"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "audit idempotency", "fantasy", "classic")
    try:
        first = db.add_narrative_audit(
            novel_id, 4, "temporal_graph_compliance", "critical",
            "楚風未經授權再次行動。", "請依契約修正。", True,
        )
        second = db.add_narrative_audit(
            novel_id, 4, "temporal_graph_compliance", "critical",
            "楚風未經授權再次行動。", "另一個修正說明。", True,
        )
        assert first["id"] == second["id"]
        assert len(db.get_narrative_audits(novel_id, unresolved_only=True)) == 1
    finally:
        db.delete_novel(novel_id)


def test_graph_observation_inserts_are_idempotent_and_keep_planned_events():
    novel_id = "test_story_graph_idempotency"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "graph idempotency", "fantasy", "classic")
    try:
        db.upsert_story_event(
            novel_id, 3, {"event_type": "death", "character": "拜蒙"}, status="planned"
        )
        first_episode = db.save_episode(novel_id, 3, "chapter", "hash-3")
        second_episode = db.save_episode(novel_id, 3, "chapter", "hash-3")
        assert first_episode["id"] == second_episode["id"]

        first_fact = db.add_fact(
            novel_id, "拜蒙看見星光", 3, relation_type="observation", episode_id=first_episode["id"]
        )
        second_fact = db.add_fact(
            novel_id, "拜蒙看見星光", 3, relation_type="observation", episode_id=first_episode["id"]
        )
        assert first_fact["id"] == second_fact["id"]
        assert len(db.get_facts_at_chapter(novel_id, 3)) == 1

        from backend.persistence.repositories.temporal_graph import delete_chapter_slice
        delete_chapter_slice(novel_id, 3)
        assert len(db.get_story_events(novel_id, chapter_index=3, status="planned")) == 1
        assert db.get_story_events(novel_id, chapter_index=3, status="occurred") == []
    finally:
        db.delete_novel(novel_id)


def test_graph_extractor_fallback_is_read_only(monkeypatch):
    novel_id = "test_story_graph_fallback"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "graph fallback", "fantasy", "classic")
    try:
        from backend.services.graphiti import extractor

        def fail_llm(**_kwargs):
            raise RuntimeError("simulated extractor failure")

        monkeypatch.setattr(extractor, "call_llm", fail_llm)
        result = extractor.ChapterFactExtractor.process_chapter_prose(
            novel_id, 3, "這是一段足夠長的正文。" * 20
        )
        assert result["status"] == "fallback"
        assert result["used_fallback"] is True
        assert db.get_episodes(novel_id) == []
        assert db.get_facts_at_chapter(novel_id, 3) == []
        assert db.get_entities(novel_id) == []
    finally:
        db.delete_novel(novel_id)
