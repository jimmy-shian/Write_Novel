# -*- coding: utf-8 -*-
"""
Story Engine 2.0 敘事推理系統單元測試：
- ConflictLedger：衝突簽名與長程重複檢查（含 self-match 排除）
- SettingRegistry：設定同步、健康審計、使用記錄、writer 脈絡
- NarrativeAuditor：正文口癖與呼吸章診斷
- 級聯刪除：delete_novel 連動清除敘事子表
- 總監 evaluator 整合
"""
import json

from backend import persistence as db
from backend.services.narrative import (
    ConflictLedger,
    SettingRegistry,
    NarrativeAuditor,
)
from backend.services.director.tool_registry.evaluator import evaluate_output


def test_conflict_ledger_signature_and_repetition():
    novel_id = "test_novel_narrative_cl"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "衝突帳本測試", "玄幻", "升級")

    # 1. 建立重複性衝突簽名（模擬前文已重複出現的套路）
    sig1 = {
        "novel_id": novel_id,
        "chapter_index": 10,
        "initiator": "執法隊",
        "opponent": "主角",
        "underlying_cause": "階層特權壓迫",
        "escalation_mechanism": "公開羞辱與定罪",
        "protagonist_strategy": "play_dumb_or_weak",
        "turning_tactic": "secret_power_burst",
        "resolution_archetype": "public_shock",
        "cost": "無",
        "new_imbalance": "長老懷疑",
    }
    db.add_conflict_signature(sig1)

    sig2 = {
        "novel_id": novel_id,
        "chapter_index": 20,
        "initiator": "內門執事",
        "opponent": "主角",
        "underlying_cause": "特權打壓",
        "escalation_mechanism": "強徵配額並羞辱",
        "protagonist_strategy": "play_dumb_or_weak",
        "turning_tactic": "secret_power_burst",
        "resolution_archetype": "public_shock",
        "cost": "無",
        "new_imbalance": "宗門暗探注意",
    }
    db.add_conflict_signature(sig2)

    # 2. 候選簽名 A：高度相似的相同套路（裝傻 -> 爆發打臉 -> 眾人震驚）
    candidate_repetitive = {
        "chapter_index": 30,
        "initiator": "真傳弟子",
        "opponent": "主角",
        "underlying_cause": "搶奪資源",
        "escalation_mechanism": "當眾羞辱",
        "protagonist_strategy": "play_dumb_or_weak",
        "turning_tactic": "secret_power_burst",
        "resolution_archetype": "public_shock",
        "cost": "無",
        "new_imbalance": "更多弟子眼紅",
    }

    rep_result = ConflictLedger.check_long_range_repetition(novel_id, candidate_repetitive, threshold=0.70)
    assert rep_result["has_repetition"] is True
    assert len(rep_result["matches"]) >= 1
    match = rep_result["matches"][0]
    assert match["similarity"] >= 0.70
    assert any("策略" in r or "同質" in r or "套路" in r for r in match["reasons"])

    # 3. 候選簽名 B：全新破局維度（制度智鬥、非暴力妥協、付出情報代價）
    candidate_novel = {
        "chapter_index": 30,
        "initiator": "真傳弟子",
        "opponent": "主角",
        "underlying_cause": "搶奪資源",
        "escalation_mechanism": "動用宗門律法封鎖商路",
        "protagonist_strategy": "rules_loophole",
        "turning_tactic": "informational_blackmail",
        "resolution_archetype": "uneasy_truce",
        "cost": "出讓三成配額收益並暴露部分人脈",
        "new_imbalance": "商會掌櫃對主角產生敬畏與防備",
    }

    novel_result = ConflictLedger.check_long_range_repetition(novel_id, candidate_novel, threshold=0.70)
    assert novel_result["has_repetition"] is False

    db.delete_novel(novel_id)


def test_setting_registry_sync_and_auditing():
    novel_id = "test_novel_narrative_sr"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "設定註冊表測試", "奇幻", "西幻")

    # 1. 儲存世界觀 JSON
    worldview_json = {
        "theme": "禁忌真理與代價",
        "main_conflict": "神聖教會 vs 異端秘術",
        "worldview": "以靈界以太為能源的世界",
        "macro_outline": "主角從底層調查員晉升為破局者",
        "power_systems": [
            {
                "name": "以太詠唱術",
                "rules": "透過喉輪震動共鳴以太靈絲",
                "costs": "高頻詠唱會導致聲帶石化與短暫靈覺喪失",
                "boundaries": "不可在深淵磁暴環境中發動，否則引來虛空異形",
                "levels": ["學者", "秘儀祭司", "聖座引路人"],
            },
            {
                "name": "血脈禁咒",
                "rules": "消耗自體壽命換取瞬間物理抗拒力",
                "costs": "",  # 故意留空測試審計
                "boundaries": "",  # 故意留空測試審計
                "levels": ["初醒", "燃血"],
            }
        ]
    }
    db.save_worldbuilding(novel_id, json.dumps(worldview_json, ensure_ascii=False), validate=False)

    # 2. 同步設定體系
    synced_count = SettingRegistry.sync_systems_from_worldview(novel_id)
    assert synced_count == 2

    systems = db.get_setting_systems(novel_id)
    assert len(systems) == 2

    # 3. 執行設定健康審計：應抓出血脈禁咒缺乏 costs 與 boundaries
    audit_res = SettingRegistry.audit_setting_health(novel_id, current_chapter=1)
    assert audit_res["total_systems"] == 2
    boundary_missing = audit_res["boundary_missing_systems"]
    assert "血脈禁咒" in boundary_missing

    # 4. 記錄設定使用
    SettingRegistry.record_system_usage(
        novel_id=novel_id,
        system_name="以太詠唱術",
        chapter_index=5,
        cost_paid="喉輪灼傷，喪失聽覺三小時",
        boundary_tested="在地下礦坑弱以太區使用，威力衰減八成",
    )
    sys_record = db.get_setting_system_by_name(novel_id, "以太詠唱術")
    assert sys_record["last_used_chapter"] == 5
    assert sys_record["usage_count"] == 1

    # 5. Writer 設定脈絡提取
    context = SettingRegistry.get_setting_context_for_writer(
        novel_id=novel_id,
        active_systems=["以太詠唱術"],
    )
    assert "以太詠唱術" in context
    assert "高頻詠唱會導致聲帶石化" in context
    assert "不可在深淵磁暴環境中發動" in context

    db.delete_novel(novel_id)


def test_narrative_auditor_prose_diagnostics():
    novel_id = "test_novel_narrative_na"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "敘事診斷測試", "科幻", "末日")

    # 1. 套路動作與對白口癖堆疊
    bad_prose = (
        "李斯特看著眼前的軍官，嘴角微微勾起一抹冷笑。"
        "『區區螻蟻，也敢擋我的路？』他冷漠開口。"
        "眼神深處閃過一抹寒芒，周圍空氣瞬間凝固。"
        "軍官臉色大變，『這不可能！你怎麼可能突破防線！』"
        "旁邊的副官更是倒吸一口涼氣，渾身顫抖不已。"
        * 15  # 重複以達足夠長度
    )

    audit_bad = NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id,
        chapter_index=1,
        prose_text=bad_prose,
        current_outline={"scene_function": "climax"},
    )
    assert audit_bad["findings_count"] >= 1
    voice_findings = [f for f in audit_bad["findings"] if f["dimension"] == "voice_integrity"]
    assert len(voice_findings) >= 1
    assert "嘴角勾起笑意/冷笑" in voice_findings[0]["evidence"]

    # 2. 安靜呼吸章（Breathing Scene）→ NO_ACTION_REQUIRED
    quiet_prose = (
        "雨水順著簷角的鏽蝕鐵皮滴落，砸在泥濘的石板上，發出沉悶的聲響。"
        "林默坐在工作台前，將拆解開來的發條齒輪一顆顆浸入煤油中清洗。"
        "房間裡只有煤油燃燒的微弱劈啪聲與齒輪轉動的嗒嗒音韻。"
        "他沒有說話，只是凝視著窗外灰濛濛的天空，回想著昨日導師留下的警告。"
        "這一刻，城市彷彿睡去，暴風雨來臨前的寧靜浸透了每一吋空氣。"
        * 20
    )

    audit_quiet = NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id,
        chapter_index=2,
        prose_text=quiet_prose,
        current_outline={"scene_function": "reflection"},
    )
    assert audit_quiet["is_breathing_scene"] is True
    assert audit_quiet["overall_action"] == "NO_ACTION_REQUIRED"

    db.delete_novel(novel_id)


def test_audit_excludes_self_signature():
    """回歸測試：審計本章時不得拿本章自己的簽名比出相似度 1.0 的 self-match 誤報。"""
    novel_id = "test_novel_no_selfmatch"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "自比排除測試", "玄幻", "升級")

    sig = ConflictLedger.record_signature(
        novel_id=novel_id, chapter_start=1, chapter_end=1,
        pressure_type="suppression", protagonist_strategy="play_dumb_or_weak",
        outcome="reversal", initiator="執法隊", cost="", power_used="禁咒殘片",
    )
    res = NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id, chapter_index=1,
        prose_text="雨水順著簷角滴落，林默靜坐清洗齒輪。" * 20,
        current_outline={"scene_function": "reflection"},
        candidate_conflict_sig=sig,
    )
    assert not [f for f in res["findings"] if f["dimension"] == "conflict_novelty"]

    # 真實跨章重複仍須命中，且顯示為「第 X 章」而非「第 X-X 章」
    ConflictLedger.record_signature(
        novel_id=novel_id, chapter_start=2, chapter_end=2,
        pressure_type="suppression", protagonist_strategy="play_dumb_or_weak",
        outcome="reversal", initiator="內門執事", cost="", power_used="禁咒殘片",
    )
    rep = ConflictLedger.check_long_range_repetition(
        novel_id,
        {"pressure_type": "suppression", "protagonist_strategy": "play_dumb_or_weak",
         "outcome": "reversal", "cost": "", "power_used": "禁咒殘片"},
        exclude_chapter=3,
    )
    assert rep["has_repetition"] is True
    assert all("-" not in m["prior_chapter_range"] for m in rep["matches"])

    db.delete_novel(novel_id)


def test_cascading_deletion_of_narrative_tables():
    """刪除小說時必須連動清除 setting_systems / conflict_signatures / narrative_audits。"""
    novel_id = "test_novel_cascade_cleanup"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "級聯刪除測試小說", "懸疑", "推理")

    # 1. setting_systems
    db.upsert_setting_system(
        novel_id=novel_id,
        system_name="靈視推理法",
        system_type="cognitive_ability",
        rules="透過微表情與光譜重構犯罪現場",
        costs="造成劇烈偏頭痛與微血管破裂",
        boundaries="無法透視覆蓋鉛層的密室",
        vulnerabilities="強光干擾",
    )
    assert len(db.get_setting_systems(novel_id)) == 1

    # 2. conflict_signatures
    db.add_conflict_signature({
        "novel_id": novel_id,
        "chapter_index": 1,
        "initiator": "兇手",
        "opponent": "偵探",
        "underlying_cause": "掩蓋遺產侵吞",
        "escalation_mechanism": "偽造不在場證明",
        "protagonist_strategy": "deductive_trap",
        "turning_tactic": "physical_evidence",
        "resolution_archetype": "confession_under_pressure",
        "cost": "消耗最後一顆止痛藥",
        "new_imbalance": "發現幕後委託人另有其人",
    })
    assert len(db.get_conflict_signatures(novel_id)) == 1

    # 3. narrative_audits
    db.add_narrative_audit(
        novel_id=novel_id,
        chapter_index=1,
        dimension="voice_integrity",
        severity="watch",
        evidence="偵探口吻冷靜克制",
        recommendation="保持當前語調",
        action_required=False,
    )
    assert len(db.get_narrative_audits(novel_id)) == 1

    # 4. 級聯刪除
    db.delete_novel(novel_id)

    # 5. 所有子表皆應被徹底清除
    assert len(db.get_setting_systems(novel_id)) == 0
    assert len(db.get_conflict_signatures(novel_id)) == 0
    assert len(db.get_narrative_audits(novel_id)) == 0
    assert db.get_novel(novel_id) is None


def test_director_evaluator_integration():
    """evaluate_output 支援 NarrativeAuditor 診斷與輸出。"""
    novel_id = "test_novel_eval_director"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "總監評斷整合測試", "科幻", "賽博")

    prose = (
        "【正文開始】\n"
        "夜幕低垂，新九龍城的霓虹光帶在酸雨中扭曲成斑駁的色塊。\n"
        "陳恆靠在暗巷的通風管道旁，指尖輕敲著生鏽的金屬外殼。\n"
        "資料晶片已經送出，但他很清楚，真正的風暴才剛剛開始。\n"
    ) * 30

    output_content = f'{{"novel_id": "{novel_id}", "chapter_index": 1, "synopsis": "暗巷撤退", "content": "{prose}"}}'

    eval_result = evaluate_output(
        stage_name="writer",
        output_content=output_content,
        novel_id=novel_id,
    )

    assert eval_result["passed"] is True
    assert "narrative_audit" in eval_result
    assert eval_result["narrative_audit"]["chapter_index"] == 1

    db.delete_novel(novel_id)