# -*- coding: utf-8 -*-
"""
Unit tests for Story Engine 2.0 (Narrative Reasoning System) REST API endpoints.
"""

import json
from fastapi.testclient import TestClient
from backend.app import app
from backend import persistence as db

client = TestClient(app)


def test_narrative_profile_api():
    novel_id = "test_novel_narrative_api_profile"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "畫像測試作品", "玄幻升級", "熱血")

    # 1. 取得預設畫像
    res = client.get(f"/api/novels/{novel_id}/narrative-profile")
    assert res.status_code == 200
    data = res.json()
    assert data["novel_id"] == novel_id
    assert "power_fantasy_level" in data["profile"]

    # 2. 更新畫像
    payload = {
        "commercial_positioning": "長篇爽文標竿",
        "power_fantasy_level": "high",
        "pacing_preference": "大開大闔、重伏筆",
    }
    update_res = client.put(f"/api/novels/{novel_id}/narrative-profile", json=payload)
    assert update_res.status_code == 200
    updated_profile = update_res.json()["profile"]
    assert updated_profile["commercial_positioning"] == "長篇爽文標竿"
    assert updated_profile["power_fantasy_level"] == "high"

    # 清理
    db.delete_novel(novel_id)


def test_setting_systems_api():
    novel_id = "test_novel_narrative_api_settings"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "設定系統測試作品", "仙俠", "正統")

    # 1. 手動建立設定系統
    sys_payload = {
        "name": "天道靈脈律",
        "type": "ecological_law",
        "mechanism": "修士引天地靈氣入體淬鍊金丹，天地靈壓隨修士進階指數倍增",
        "cost": "經脈負荷過載即有道基崩碎之厄",
        "boundary": "不可憑空扭轉五行相剋法則",
        "failure_condition": "靈氣枯竭或天劫雷罰",
        "current_state": "active",
    }
    res = client.post(f"/api/novels/{novel_id}/setting-systems", json=sys_payload)
    assert res.status_code == 200
    created = res.json()["setting_system"]
    assert created["name"] == "天道靈脈律"
    assert created["cost"] == sys_payload["cost"]

    # 2. 查詢列表
    list_res = client.get(f"/api/novels/{novel_id}/setting-systems")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 3. 審查健康度
    health_res = client.get(f"/api/novels/{novel_id}/setting-systems/health")
    assert health_res.status_code == 200
    health = health_res.json()["health"]
    assert "score" in health
    assert health["score"] >= 80

    # 4. 模擬世界觀同步
    db.save_worldbuilding(novel_id, json.dumps({
        "worldview": "太虛修真大世界",
        "main_conflict": "宗門暗戰與異域魔劫",
        "macro_outline": "從底層散修到逆天登仙",
        "theme": "人定勝天",
        "power_system": "練氣、築基、金丹、元嬰、化神九重天律",
        "rules": [{"rule_name": "因果誓言反噬律", "details": "違背神魂誓約者立遭心魔劫火焚身", "boundary": "天道見證"}],
        "factions": [{"name": "太虛劍宗", "position": "正道領袖", "resources": "靈礦九座"}],
    }))
    sync_res = client.post(f"/api/novels/{novel_id}/setting-systems/sync")
    assert sync_res.status_code == 200
    assert sync_res.json()["synced_count"] >= 2

    # 清理
    db.delete_novel(novel_id)


def test_conflict_signatures_and_repetition_api():
    novel_id = "test_novel_narrative_api_conflicts"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "衝突特徵測試作品", "科幻", "硬科幻")

    # 1. 登記第一筆衝突因果
    sig_payload = {
        "chapter_start": 1,
        "chapter_end": 3,
        "initiator": "行星安全理事會",
        "pressure_type": "資源封鎖與物資禁運",
        "protagonist_strategy": "秘密重構反物質推進陣列",
        "power_used": "次世代黑洞引擎",
        "outcome": "成功突圍並重挫理事會巡邏艦隊",
        "cost": "消耗最後一枚同位素電池，維生系統降載30%",
    }
    create_res = client.post(f"/api/novels/{novel_id}/conflict-signatures", json=sig_payload)
    assert create_res.status_code == 200
    sig = create_res.json()["signature"]
    assert sig["pressure_type"] == "資源封鎖與物資禁運"

    # 2. 檢索衝突特徵清單
    list_res = client.get(f"/api/novels/{novel_id}/conflict-signatures")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 3. 測試長程重複診斷沙盒
    # 候選 A: 高度相似的因果策略
    rep_req_same = {
        "candidate_signature": {
            "pressure_type": "資源封鎖",
            "protagonist_strategy": "秘密重構反物質推進陣列",
            "outcome": "成功突圍並重挫敵方",
            "cost": "無",
        },
        "threshold": 0.5,
    }
    check_res = client.post(f"/api/novels/{novel_id}/conflict-signatures/check-repetition", json=rep_req_same)
    assert check_res.status_code == 200
    diag = check_res.json()["diagnosis"]
    assert diag["has_repetition"] is True
    assert diag["max_similarity"] >= 0.5

    # 候選 B: 全新因果模式 (利益談判，零相似度)
    rep_req_diff = {
        "candidate_signature": {
            "pressure_type": "公理法規訴訟",
            "protagonist_strategy": "提交跨星系商業反壟斷訴狀",
            "outcome": "凍結對手資產",
            "cost": "承諾五年技術專利開放",
        },
        "threshold": 0.7,
    }
    check_res_diff = client.post(f"/api/novels/{novel_id}/conflict-signatures/check-repetition", json=rep_req_diff)
    assert check_res_diff.status_code == 200
    diag_diff = check_res_diff.json()["diagnosis"]
    assert diag_diff["has_repetition"] is False

    # 清理
    db.delete_novel(novel_id)


def test_narrative_audits_lifecycle_and_run_api():
    novel_id = "test_novel_narrative_api_audits"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "審計診斷測試作品", "都市", "懸疑")

    # 寫入第 1 章正文（刻意包含高頻口癖）
    prose = "陳巡捕嘴角微微勾起一抹冷笑，眼神深處閃過一抹冷冽。區區螻蟻也敢反抗！這不可能！空氣瞬間凝固。"
    db.save_chapter(novel_id, 1, prose)

    # 1. 執行即時審計
    run_res = client.post(f"/api/novels/{novel_id}/narrative-audits/run", json={"chapter_index": 1})
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "success"
    assert run_data["result"]["overall_action"] in ("WATCH", "REVISE", "CRITICAL")
    assert len(run_data["audits"]) >= 1

    first_audit = run_data["audits"][0]
    audit_id = first_audit["id"]
    assert first_audit["resolved"] == 0

    # 2. 標記處置
    resolve_res = client.post(f"/api/narrative-audits/{audit_id}/resolve")
    assert resolve_res.status_code == 200
    assert resolve_res.json()["resolved"] is True

    # 3. 查詢已處置後的 unresolved 列表
    unresolved_res = client.get(f"/api/novels/{novel_id}/narrative-audits?chapter_index=1&unresolved_only=true")
    assert unresolved_res.status_code == 200
    unresolved_ids = [a["id"] for a in unresolved_res.json()["audits"]]
    assert audit_id not in unresolved_ids

    # 清理
    db.delete_novel(novel_id)
