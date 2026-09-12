# -*- coding: utf-8 -*-
import pytest
from backend.common.version import get_version, get_app_info
from backend import persistence as db
from backend.services.graphiti import TemporalGraphService

def test_version_single_source_of_truth():
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "version.json"), encoding="utf-8") as f:
        ssot = json.load(f)
    app_info = get_app_info()
    assert "version" in app_info
    assert app_info["version"] == ssot["version"]
    assert get_version() == ssot["version"]

def test_temporal_graph_lifecycle():
    novel_id = "test_novel_graphiti"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "時序圖譜測試小說", "仙俠", "熱血")

    # 1. Upsert Entities
    e1 = db.upsert_entity(novel_id, "林動", "character", "大荒宗弟子", {"cultivation": "造化境"}, chapter_index=1)
    e2 = db.upsert_entity(novel_id, "大荒古碑", "location", "遠古遺跡", {}, chapter_index=1)
    e3 = db.upsert_entity(novel_id, "吞噬祖符", "item", "遠古神物", {}, chapter_index=1)

    assert e1["name"] == "林動"
    assert len(db.get_entities(novel_id)) >= 3

    # 2. Add Facts
    f1 = db.add_fact(
        novel_id=novel_id,
        fact_statement="林動在古碑中首次感應到祖符波動",
        valid_from_chapter=1,
        source_entity_id=e1["id"],
        target_entity_id=e3["id"],
        relation_type="感應"
    )
    assert f1["valid_from_chapter"] == 1
    assert f1["is_active"] is True

    f2 = db.add_fact(
        novel_id=novel_id,
        fact_statement="林動尚未認主吞噬祖符",
        valid_from_chapter=1,
        source_entity_id=e1["id"],
        target_entity_id=e3["id"],
        relation_type="未認主"
    )

    # At chapter 2, both facts are active
    facts_ch2 = db.get_facts_at_chapter(novel_id, 2)
    assert len(facts_ch2) == 2

    # Invalidate f2 at chapter 5 (林動成功認主吞噬祖符)
    f3 = db.add_fact(
        novel_id=novel_id,
        fact_statement="林動成功煉化並認主吞噬祖符",
        valid_from_chapter=5,
        source_entity_id=e1["id"],
        target_entity_id=e3["id"],
        relation_type="持有並認主"
    )
    db.invalidate_fact(f2["id"], invalid_from_chapter=5, superseded_by=f3["id"])

    # At chapter 3: f1 and f2 are active, f3 is NOT yet valid
    facts_ch3 = db.get_facts_at_chapter(novel_id, 3)
    statements_ch3 = [f["fact_statement"] for f in facts_ch3]
    assert "林動在古碑中首次感應到祖符波動" in statements_ch3
    assert "林動尚未認主吞噬祖符" in statements_ch3
    assert "林動成功煉化並認主吞噬祖符" not in statements_ch3

    # At chapter 6: f1 and f3 are active, f2 is INVALIDATED
    facts_ch6 = db.get_facts_at_chapter(novel_id, 6)
    statements_ch6 = [f["fact_statement"] for f in facts_ch6]
    assert "林動在古碑中首次感應到祖符波動" in statements_ch6
    assert "林動尚未認主吞噬祖符" not in statements_ch6
    assert "林動成功煉化並認主吞噬祖符" in statements_ch6

    # Test TemporalGraphService context generator
    ctx_ch6 = TemporalGraphService.build_narrative_context(
        novel_id=novel_id,
        at_chapter=6,
        active_characters=["林動"]
    )
    assert "Graphiti 時序動態記憶" in ctx_ch6
    assert "林動成功煉化並認主吞噬祖符" in ctx_ch6
    assert "於第 5 章已失效/被顛覆" in ctx_ch6
    db.delete_novel(novel_id)

def test_story_terms_lifecycle():
    novel_id = "test_novel_terms"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "術語測試小說", "玄幻", "史詩")

    t1 = db.create_term(novel_id, "功法", "大荒囚天指", "大荒帝所創武學，共分五指", "主角核心攻擊技能")
    assert t1["term"] == "大荒囚天指"

    terms = db.get_terms(novel_id)
    assert any(t["term"] == "大荒囚天指" for t in terms)

    db.update_term(t1["id"], "天階武學", "大荒囚天指(半步天階)", "大荒帝所創武學，進化為半步天階", "更強威力")
    updated = db.get_terms(novel_id)
    assert any(t["term"] == "大荒囚天指(半步天階)" for t in updated)

    db.delete_term(t1["id"])
    assert not any(t["term"] == "大荒囚天指(半步天階)" for t in db.get_terms(novel_id))
    db.delete_novel(novel_id)

def test_chapter_clear_cascade_and_term_sync():
    from backend.services.graphiti.cascade import clear_chapter_cascade
    novel_id = "test_novel_cascade"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "連動測試小說", "玄幻", "史詩")

    db.save_chapter(novel_id, 3, "第三章正文")
    e1 = db.upsert_entity(novel_id, "林夜", "character", "主角", {}, chapter_index=3)
    e2 = db.upsert_entity(novel_id, "陳銳", "character", "配角", {}, chapter_index=2)
    ep = db.save_episode(novel_id, 3, "ch3", "hash3")
    db.add_fact(novel_id, "林夜測試測能儀", valid_from_chapter=3,
                source_entity_id=e1["id"], episode_id=ep["id"])
    f_old = db.add_fact(novel_id, "舊事實待回滾", valid_from_chapter=1)
    db.invalidate_fact(f_old["id"], invalid_from_chapter=3, superseded_by="ch3")
    db.upsert_term(novel_id, "角色", "林夜", "主角", "", source_chapter=3, updated_chapter=3)
    db.create_term(novel_id, "功法", "大荒囚天指", "武學", "手動")

    # 手動術語優先：自動同步不得覆寫
    kept = db.upsert_term(novel_id, "角色", "大荒囚天指", "自動定義", "",
                          source_chapter=3, updated_chapter=3)
    assert kept["action"] == "kept_manual"

    # 存空正文即連動清除
    db.save_chapter(novel_id, 3, "   ")
    stmts = [f["fact_statement"] for f in db.get_all_facts(novel_id)]
    assert "林夜測試測能儀" not in stmts
    assert "舊事實待回滾" in stmts  # 作廢被回滾
    assert db.get_episodes(novel_id) == []
    names = {e["name"] for e in db.get_entities(novel_id)}
    assert "林夜" not in names and "陳銳" in names
    terms = {t["term"] for t in db.get_terms(novel_id)}
    assert "林夜" not in terms and "大荒囚天指" in terms

    # cascade 服務＋reset chapters 範圍
    db.save_chapter(novel_id, 5, "第五章")
    db.upsert_entity(novel_id, "新實體", "item", "道具", {}, chapter_index=5)
    db.upsert_term(novel_id, "道具", "新實體", "道具", "", source_chapter=5, updated_chapter=5)
    s = clear_chapter_cascade(novel_id, 5)
    assert s["facts_deleted"] == 0 and s["entities_deleted"] == 1 and s["auto_terms_deleted"] == 1
    assert db.reset_novel_content(novel_id, scopes=["chapters"]) == ["chapters"]
    assert db.get_all_facts(novel_id) == [] and db.get_entities(novel_id) == []
    assert {t["term"] for t in db.get_terms(novel_id)} == {"大荒囚天指"}
    db.delete_novel(novel_id)

def test_draft_proposals_lifecycle():
    novel_id = "test_novel_proposals"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "提案測試小說", "科幻", "賽博龐克")

    prop = db.create_proposal(
        novel_id=novel_id,
        chapter_index=1,
        proposed_text="雨夜，霓虹燈倒映在義體醫師的鏡片上...",
        original_text="這是一個普通的雨天。",
        review_comments=[{"type": "atmosphere", "comment": "加強賽博感"}]
    )
    assert prop["status"] == "pending"

    props = db.get_proposals(novel_id, chapter_index=1)
    assert len(props) == 1

    # Update proposal status
    db.update_proposal_status(prop["id"], "accepted")
    updated = db.get_proposal(prop["id"])
    assert updated["status"] == "accepted"
    db.delete_novel(novel_id)


def test_settings_save_both_payload_formats():
    from backend.services.settings.service import apply_settings_payload, build_settings_snapshot
    from backend import persistence as db

    initial_configs = db.get_agent_configs()
    try:
        # Test format 1: { "agents": { "global": { ... } } }
        res1 = apply_settings_payload({
            "agents": {
                "global": {
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o",
                    "temperature": 0.8,
                }
            }
        })
        assert res1["status"] == "success"

        # Test format 2: { "configs": { "writer": { ... } } }
        res2 = apply_settings_payload({
            "configs": {
                "writer": {
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "model": "deepseek-ai/deepseek-v4-flash-0731",
                    "temperature": 0.7,
                }
            }
        })
        assert res2["status"] == "success"

        # Test format 3: direct agent update { "agent_name": "architect", "model": "claude-3-5-sonnet" }
        res3 = apply_settings_payload({
            "agent_name": "architect",
            "model": "claude-3-5-sonnet",
        })
        assert res3["status"] == "success"

        snapshot = build_settings_snapshot()
        assert snapshot["writer"]["model"] == "deepseek-ai/deepseek-v4-flash-0731"
        assert snapshot["architect"]["model"] == "claude-3-5-sonnet"
    finally:
        if initial_configs:
            apply_settings_payload({"configs": initial_configs})


def test_pipeline_prompt_and_autonomous_status_lifecycle():
    from backend.services.autonomous_pipeline import autonomous_manager

    test_novel_id = "test_novel_pipeline_prompt_suite"
    db.delete_novel(test_novel_id)
    db.create_novel(test_novel_id, "符鎮山河測試", "仙俠", "爽文快節奏")

    # 1. Pipeline prompt persistence and update
    prompt_text = "主角攜帶太古鎮魔神符穿越至山河破碎之世，以符道重定乾坤。"
    db.update_novel_pipeline_prompt(test_novel_id, prompt_text)
    novel = db.get_novel(test_novel_id)
    assert novel is not None
    assert novel["pipeline_prompt"] == prompt_text

    # 2. Autonomous pipeline status contract check (is_running and running compatibility)
    status = autonomous_manager.get_status(test_novel_id)
    assert "is_running" in status
    assert "running" in status
    assert status["is_running"] == status["running"]
    assert "logs" in status
    assert isinstance(status["logs"], list)

    # 3. Autonomous start contract check
    res = autonomous_manager.start_pipeline(test_novel_id, prompt="", max_chapters=1)
    assert res["status"] in ("started", "already_running")
    assert res.get("success") is True
    assert "message" in res

    # 4. Immediate status check reflects running and task tracking
    running_status = autonomous_manager.get_status(test_novel_id)
    assert running_status["is_running"] is True
    assert running_status["running"] is True
    assert running_status["novel_id"] == test_novel_id

    # 5. Stop pipeline
    stop_res = autonomous_manager.stop_pipeline(test_novel_id)
    assert stop_res["status"] == "stopping"
    assert stop_res.get("success") is True

    db.delete_novel(test_novel_id)


