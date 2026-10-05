# -*- coding: utf-8 -*-
"""
Milestone 2 Unit & Integration Tests:
- Director Action Contracts (SPLIT_CHAPTER_OUTLINE, EXPAND_CHAPTER_OUTLINE)
- Dynamic Outline Splitting & Persistence Cascade (split_and_expand_chapter_outline)
- Chapter Outline Density Overload Detection (is_chapter_outline_density_overloaded)
- fix_chapter_until_pass Overhaul (Disappearing Targets Bug fix, Premature no_change escalation, Dynamic Split)
"""

import copy
import pytest
from backend import persistence as db
from backend.agents.director.contracts import EXECUTABLE_DIRECTOR_ACTIONS
from backend.agents.director.runner import _director_decision_needs_recovery
from backend.services.narrative.density import (
    is_chapter_outline_density_overloaded,
    build_split_chapter_outlines,
)
from backend.persistence.repositories.volumes import (
    split_and_expand_chapter_outline,
    get_volumes,
    save_volumes,
)
from backend.services.narrative.fix import (
    fix_chapter_until_pass,
    fix_chapter_from_audits,
)
from backend.services.narrative.narrative_auditor import NarrativeAuditor


@pytest.fixture(autouse=True)
def _mock_director_llm(monkeypatch):
    """Mock Director LLM to avoid real external calls during tests."""
    import backend.common.llm as llm_mod

    def fake_call_llm(agent_name, system_prompt, user_prompt, **kwargs):
        return "請替換模板化開篇與口癖，並在因果博弈中展現真實體力消耗與情報代價。"

    monkeypatch.setattr(llm_mod, "call_llm", fake_call_llm)


@pytest.fixture(autouse=True)
def _mock_writer_agent(monkeypatch):
    """預設 mock chapter writer，回傳空 generator；個別測試可自行覆寫。"""
    def fake_writer(novel_id, chapter_index, user_prompt="", stream=False, **kwargs):
        def _gen():
            yield "data: [DONE]"
        return _gen()
    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", fake_writer)



def _good_prose(seed: str = "") -> str:
    base = (
        "李斯特把油燈芯撥低，指尖沿著地圖上的一道舊折痕慢慢壓平，"
        "紙面邊緣還留著昨夜雨水滲進帳篷時暈開的潮氣。"
        "軍官把令牌推回桌心，沒有再多說一個字，只把披風上的扣环繫緊了半格。"
    )
    return (base * 15) + seed


def _bad_prose(seed: str = "") -> str:
    base = (
        "李斯特冷冷注視著眼前的軍官，嘴角微微勾起一抹冷笑。"
        "『區區螻蟻，也敢擋我的路？』他開口時眼神深處閃過一抹寒芒，四周空氣彷彿凝固。"
        "軍官握緊長槍，喉結滾動，卻不敢後退半步，汗水沿著頭盔內緣滑落。"
    )
    return (base * 14) + seed


# =========================================================================
# 1. Director Action Contracts Tests
# =========================================================================

def test_director_contracts_contain_split_and_expand():
    """驗證 EXECUTABLE_DIRECTOR_ACTIONS 包含 SPLIT_CHAPTER_OUTLINE 與 EXPAND_CHAPTER_OUTLINE"""
    assert "SPLIT_CHAPTER_OUTLINE" in EXECUTABLE_DIRECTOR_ACTIONS
    assert "EXPAND_CHAPTER_OUTLINE" in EXECUTABLE_DIRECTOR_ACTIONS


def test_director_decision_validation_accepts_split_outline():
    """驗證 Director runner 決策校驗正確接受 SPLIT_CHAPTER_OUTLINE 動作信封"""
    valid_split_decision = {
        "action": "SPLIT_CHAPTER_OUTLINE",
        "target": "writer",
        "chapter_index": 5,
        "volume_index": 1,
        "reason": "第 5 章細綱包含 2 個重大轉折與多個場景跳躍，資訊密度過載，拆分為兩章以保證敘事張力。",
        "split_plan": {
            "split_count": 2,
            "chapters": [
                {
                    "chapter_title": "第 5 章：暗流初動",
                    "chapter_summary": "第一階段：主角潛入港口遭遇巡哨",
                    "events": [{"scene_index": 1, "location": "黑水港口", "content": "潛入遭遇伏擊"}],
                    "allocated_tasks": {"foreshadowing_plants": ["seed_1"], "foreshadowing_payoffs": [], "turning_points": []},
                    "scene_function": "confrontation"
                },
                {
                    "chapter_title": "第 6 章：破局交鋒",
                    "chapter_summary": "第二階段：主角突破重圍進入禁室",
                    "events": [{"scene_index": 1, "location": "地下禁室", "content": "與宿敵對決揭示真相"}],
                    "allocated_tasks": {"foreshadowing_plants": [], "foreshadowing_payoffs": ["seed_2"], "turning_points": ["turn_1"]},
                    "scene_function": "climax"
                }
            ]
        }
    }
    assert _director_decision_needs_recovery(valid_split_decision) is False


# =========================================================================
# 2. Density Overload Detection Tests
# =========================================================================

def test_density_overload_detection_criteria():
    """驗證密度過載輔助函式在各項門檻上的精準觸發與邊界判定"""
    # 1. 轉折點 >= 2 觸發過載
    outline_tp = {
        "allocated_tasks": {"turning_points": ["tp1", "tp2"], "foreshadowing_plants": [], "foreshadowing_payoffs": []},
        "events": [{"scene_index": 1}],
    }
    assert is_chapter_outline_density_overloaded(outline_tp) is True

    # 轉折點 < 2 不觸發
    outline_normal = {
        "allocated_tasks": {"turning_points": ["tp1"], "foreshadowing_plants": ["p1"], "foreshadowing_payoffs": []},
        "events": [{"scene_index": 1}],
    }
    assert is_chapter_outline_density_overloaded(outline_normal) is False

    # 2. 伏筆任務 (plants + payoffs) >= 4 觸發過載
    outline_fs = {
        "allocated_tasks": {"turning_points": [], "foreshadowing_plants": ["p1", "p2"], "foreshadowing_payoffs": ["pay1", "pay2"]},
        "events": [{"scene_index": 1}],
    }
    assert is_chapter_outline_density_overloaded(outline_fs) is True

    # 3. 事件/場景數 >= 3 觸發過載
    outline_ev = {
        "allocated_tasks": {"turning_points": [], "foreshadowing_plants": [], "foreshadowing_payoffs": []},
        "events": [
            {"scene_index": 1, "location": "A"},
            {"scene_index": 2, "location": "B"},
            {"scene_index": 3, "location": "C"},
        ],
    }
    assert is_chapter_outline_density_overloaded(outline_ev) is True

    # 4. 場景跳躍 + 角色轉折觸發過載
    outline_jumps = {
        "scene_jumps": 2,
        "character_turns": 1,
        "events": [{"scene_index": 1}],
    }
    assert is_chapter_outline_density_overloaded(outline_jumps) is True

    # 空或非法輸入容錯
    assert is_chapter_outline_density_overloaded(None) is False
    assert is_chapter_outline_density_overloaded({}) is False


def test_build_split_chapter_outlines_structure():
    """驗證 build_split_chapter_outlines 能夠均勻拆分事件與伏筆任務"""
    dense_outline = {
        "chapter_index": 10,
        "chapter_title": "第 10 章：夜襲要塞",
        "chapter_summary": "主角夜襲敵方要塞，付出代價後奪取密鑰並揭露真相。",
        "events": [
            {"scene_index": 1, "location": "城外密林", "content": "暗夜潛伏"},
            {"scene_index": 2, "location": "要塞城門", "content": "破門突入"},
            {"scene_index": 3, "location": "密室禁地", "content": "奪取密鑰"},
            {"scene_index": 4, "location": "頂樓祭壇", "content": "真相揭示"},
        ],
        "allocated_tasks": {
            "foreshadowing_plants": ["plant_seed_1"],
            "foreshadowing_payoffs": ["payoff_seed_2"],
            "turning_points": ["turn_point_A", "turn_point_B"],
        },
        "scene_function": "confrontation",
    }

    splits = build_split_chapter_outlines(dense_outline, split_count=2)
    assert len(splits) == 2
    part1, part2 = splits

    assert part1["chapter_index"] == 10
    assert "（上）" in part1["chapter_title"]
    assert len(part1["events"]) == 2
    assert part1["events"][0]["content"] == "暗夜潛伏"

    assert part2["chapter_index"] == 11
    assert "（下）" in part2["chapter_title"]
    assert len(part2["events"]) == 2
    assert part2["events"][1]["content"] == "真相揭示"

    # 轉折點被分流，單章不再密度過載
    assert not is_chapter_outline_density_overloaded(part1)


def test_split_outline_partitions_beats_and_preserves_scoped_fields():
    """拆章後 beats/任務互斥，且時間線與場景欄位不被覆寫或共享。"""
    outline = {
        "chapter_index": 7,
        "chapter_title": "第 7 章：密令",
        "chapter_summary": "沿著密令追查真相",
        "time_setting": "第三日黎明",
        "scene_setting": {"location": "北城檔案室", "weather": "細雨"},
        "scene_beats": ["潛入", "發現密令", "遭遇守衛", "帶走證據"],
        "allocated_tasks": {
            "turning_points": ["發現密令", "暴露身分"],
            "must_happen": ["取得密令", "留下線索"],
            "owner": "主角",
        },
    }

    part1, part2 = build_split_chapter_outlines(outline)

    assert part1["scene_beats"] == ["潛入", "發現密令"]
    assert part2["scene_beats"] == ["遭遇守衛", "帶走證據"]
    assert set(part1["scene_beats"]).isdisjoint(part2["scene_beats"])
    assert part1["allocated_tasks"]["turning_points"] == ["發現密令"]
    assert part2["allocated_tasks"]["turning_points"] == ["暴露身分"]
    assert part1["allocated_tasks"]["must_happen"] == ["取得密令"]
    assert part2["allocated_tasks"]["must_happen"] == ["留下線索"]
    assert part1["allocated_tasks"]["owner"] == part2["allocated_tasks"]["owner"] == "主角"
    assert part1["time_setting"] == part2["time_setting"] == outline["time_setting"]
    assert part1["scene_setting"] == part2["scene_setting"] == outline["scene_setting"]
    assert part1["scene_setting"] is not part2["scene_setting"]
    assert part1["allocated_tasks"] is not part2["allocated_tasks"]


# =========================================================================
# 3. Dynamic Outline Splitting & Persistence Cascade Tests
# =========================================================================

def test_split_and_expand_chapter_outline_database_cascade():
    """
    全量持久化級聯測試：
    1. 驗證 target_vol.chapter_count 增加 delta
    2. 驗證 target_vol.chapters_outline 插入新子章節，後續章節 index 順延
    3. 驗證下游篇卷 (Volume 2) 的章節 index 連動順延
    4. 驗證 chapters 與 chapter_memory 表中的已寫章節 index 降序安全平移
    5. 驗證 temporal 表與 arc_summaries 座標同步更新
    6. 驗證 GeometryGraph 若存在則同步平移節點座標
    """
    novel_id = "test_m2_split_cascade"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "拆章級聯測試", "奇幻", "冒險")

    # 建立 2 卷，每卷 3 章
    vol1_outline = [
        {"chapter_index": 1, "chapter_title": "第 1 章：啟程"},
        {"chapter_index": 2, "chapter_title": "第 2 章：過載章節"},
        {"chapter_index": 3, "chapter_title": "第 3 章：首卷收束"},
    ]
    vol2_outline = [
        {"chapter_index": 4, "chapter_title": "第 4 章：異域之行"},
        {"chapter_index": 5, "chapter_title": "第 5 章：古城迷影"},
        {"chapter_index": 6, "chapter_title": "第 6 章：真相初現"},
    ]
    volumes_data = [
        {
            "volume_index": 1,
            "title": "第 1 卷：初出茅廬",
            "summary": "第一卷概述",
            "chapter_count": 3,
            "chapters_outline": vol1_outline,
        },
        {
            "volume_index": 2,
            "title": "第 2 卷：風雲漸起",
            "summary": "第二卷概述",
            "chapter_count": 3,
            "chapters_outline": vol2_outline,
        },
    ]
    save_volumes(novel_id, volumes_data)

    # 模擬資料庫中已存在的正文與下游資料 (chapters 1..5)
    for c in range(1, 6):
        db.save_chapter(novel_id, c, f"第 {c} 章正文內容。" * 50)
        db.save_chapter_memory(novel_id, c, {"summary": f"第 {c} 章記憶摘要"})

    # 模擬 temporal 表
    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO temporal_episodes (id, novel_id, chapter_index, summary) VALUES (?, ?, ?, ?)",
            ("ep_3", novel_id, 3, "第 3 章情節快照"),
        )
        cursor.execute(
            "INSERT INTO temporal_episodes (id, novel_id, chapter_index, summary) VALUES (?, ?, ?, ?)",
            ("ep_4", novel_id, 4, "第 4 章情節快照"),
        )
        cursor.execute(
            "INSERT INTO temporal_facts (id, novel_id, fact_statement, valid_from_chapter) VALUES (?, ?, ?, ?)",
            ("tf_3", novel_id, "主角在第 3 章獲得古玉", 3),
        )
        cursor.execute(
            "INSERT INTO temporal_facts (id, novel_id, fact_statement, valid_from_chapter) VALUES (?, ?, ?, ?)",
            ("tf_4", novel_id, "主角在第 4 章到達異域", 4),
        )
        cursor.execute(
            "INSERT INTO arc_summaries (novel_id, arc_start, arc_end, summary_json) VALUES (?, ?, ?, ?)",
            (novel_id, 1, 3, "{\"arc\": \"初生弧線\"}"),
        )
        cursor.execute(
            "INSERT INTO arc_summaries (novel_id, arc_start, arc_end, summary_json) VALUES (?, ?, ?, ?)",
            (novel_id, 4, 6, "{\"arc\": \"成長弧線\"}"),
        )

    # 建立測試用幾何圖譜 (GeometryGraph)
    from backend.geometry.models import (
        GeometryGraph,
        GeometryNode,
        GeometryParams,
        NodeHierarchy,
        StructuralRole,
    )
    from backend.persistence.repositories.geometry import save_geometry_graph, load_geometry_graph
    geo_graph = GeometryGraph(
        params=GeometryParams(target_chapters=6, volume_count=2),
    )
    h1 = NodeHierarchy(volume_index=1, arc_index=1, sequence_index=1)
    node1 = GeometryNode(node_id="N_CH1", hierarchy=h1, chapter_window=(1, 1), structural_role=StructuralRole.OPEN_THREAD, primary_thread="T1")
    node2 = GeometryNode(node_id="N_CH2", hierarchy=h1, chapter_window=(2, 2), structural_role=StructuralRole.DEVELOP, primary_thread="T1")
    node3 = GeometryNode(node_id="N_CH3", hierarchy=h1, chapter_window=(3, 3), structural_role=StructuralRole.CONVERGE, primary_thread="T1")
    node4 = GeometryNode(node_id="N_CH4", hierarchy=h1, chapter_window=(4, 4), structural_role=StructuralRole.PAYOFF, primary_thread="T1")
    for n in (node1, node2, node3, node4):
        geo_graph.add_node(n)
    save_geometry_graph(novel_id, geo_graph)

    # 執行拆章：將第 2 章拆為 2 章
    split_chapters = [
        {"chapter_title": "第 2 章：突圍前夕（上）", "chapter_summary": "突圍前夕籌備"},
        {"chapter_title": "第 3 章：突圍之戰（下）", "chapter_summary": "突破封鎖線"},
    ]
    res = split_and_expand_chapter_outline(novel_id, chapter_index=2, split_chapters=split_chapters)
    assert res["success"] is True
    assert res["delta"] == 1
    assert res["new_chapter_count"] == 4  # 3 + 1 = 4

    # 斷言 1: Target Volume (Volume 1)
    vols = get_volumes(novel_id)
    v1 = next(v for v in vols if v["volume_index"] == 1)
    assert v1["chapter_count"] == 4
    v1_out = v1["chapters_outline"]
    assert len(v1_out) == 4
    assert v1_out[0]["chapter_index"] == 1
    assert v1_out[1]["chapter_index"] == 2
    assert "（上）" in v1_out[1]["chapter_title"]
    assert v1_out[2]["chapter_index"] == 3
    assert "（下）" in v1_out[2]["chapter_title"]
    assert v1_out[3]["chapter_index"] == 4  # 原第 3 章順延為第 4 章
    assert "首卷收束" in v1_out[3]["chapter_title"]

    # 斷言 2: Downstream Volume (Volume 2)
    v2 = next(v for v in vols if v["volume_index"] == 2)
    assert v2["chapter_count"] == 3
    v2_out = v2["chapters_outline"]
    assert len(v2_out) == 3
    assert v2_out[0]["chapter_index"] == 5  # 原 4 順延為 5
    assert v2_out[1]["chapter_index"] == 6  # 原 5 順延為 6
    assert v2_out[2]["chapter_index"] == 7  # 原 6 順延為 7

    # 斷言 3: chapters 表下游正文平移
    ch3_row = db.get_latest_chapter(novel_id, 3)
    ch4_row = db.get_latest_chapter(novel_id, 4)
    ch5_row = db.get_latest_chapter(novel_id, 5)
    ch6_row = db.get_latest_chapter(novel_id, 6)
    # 原第 3 章正文現在應在第 4 章
    assert "第 3 章正文內容" in ch4_row["content"]
    # 原第 4 章正文現在應在第 5 章
    assert "第 4 章正文內容" in ch5_row["content"]
    # 原第 5 章正文現在應在第 6 章
    assert "第 5 章正文內容" in ch6_row["content"]

    # 斷言 4: chapter_memory 表平移
    m4 = db.get_chapter_memory(novel_id, 4)
    m5 = db.get_chapter_memory(novel_id, 5)
    s4 = m4["summary_json"].get("summary") if isinstance(m4["summary_json"], dict) else str(m4["summary_json"])
    s5 = m5["summary_json"].get("summary") if isinstance(m5["summary_json"], dict) else str(m5["summary_json"])
    assert "第 3 章記憶摘要" in s4
    assert "第 4 章記憶摘要" in s5

    # 斷言 5: temporal 表與 arc_summaries 座標平移
    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        ep4 = cursor.execute("SELECT chapter_index FROM temporal_episodes WHERE id = 'ep_3'").fetchone()
        assert ep4["chapter_index"] == 4  # 原第 3 章平移為 4
        ep5 = cursor.execute("SELECT chapter_index FROM temporal_episodes WHERE id = 'ep_4'").fetchone()
        assert ep5["chapter_index"] == 5  # 原第 4 章平移為 5

        tf4 = cursor.execute("SELECT valid_from_chapter FROM temporal_facts WHERE id = 'tf_3'").fetchone()
        assert tf4["valid_from_chapter"] == 4
        tf5 = cursor.execute("SELECT valid_from_chapter FROM temporal_facts WHERE id = 'tf_4'").fetchone()
        assert tf5["valid_from_chapter"] == 5

        arc1 = cursor.execute("SELECT arc_start, arc_end FROM arc_summaries WHERE novel_id = ? AND arc_start = 1", (novel_id,)).fetchone()
        assert arc1["arc_end"] == 4  # 涵蓋拆分點，末端 +1 (1..4)
        arc2 = cursor.execute("SELECT arc_start, arc_end FROM arc_summaries WHERE novel_id = ? AND arc_start = 5", (novel_id,)).fetchone()
        assert arc2["arc_start"] == 5 and arc2["arc_end"] == 7  # 下游弧線整段平移 (5..7)

    # 斷言 6: GeometryGraph 同步平移
    loaded_geo = load_geometry_graph(novel_id)
    assert loaded_geo is not None
    assert loaded_geo.get_node("N_CH1").chapter_window == (1, 1)
    assert loaded_geo.get_node("N_CH2_A") is not None
    assert loaded_geo.get_node("N_CH2_A").chapter_window == (2, 2)
    assert loaded_geo.get_node("N_CH2_B") is not None
    assert loaded_geo.get_node("N_CH2_B").chapter_window == (3, 3)
    assert loaded_geo.get_node("N_CH3").chapter_window == (4, 4)
    assert loaded_geo.get_node("N_CH4").chapter_window == (5, 5)

    db.delete_novel(novel_id)


# =========================================================================
# 4. fix_chapter_until_pass Overhaul Tests
# =========================================================================

def test_fix_loop_recovers_from_director_check_failure(monkeypatch):
    """
    核心架構修復驗證（解決 Disappearing Targets Bug）：
    第 1 輪中 NarrativeAuditor 判定通過（原診斷 targets 已 resolve），
    但總監硬性校驗（evaluate_output）判定未過（例如命中公式化口癖/正文短小）。
    閉環不得拋出 ValueError('無未處置的敘事診斷') 終止，
    而應自動將總監 issues 具現化為待處置診斷，進入第 2 輪修訂並順利通過！
    """
    novel_id = "test_fix_disappearing_targets"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "消失診斷目標修復", "玄幻", "升級")
    db.save_chapter(novel_id, 1, _bad_prose())

    # 記錄一條初始敘事診斷
    db.add_narrative_audit(
        novel_id=novel_id,
        chapter_index=1,
        dimension="voice_integrity",
        severity="warning",
        evidence="嘴角勾起冷笑",
        recommendation="替換為獨特微動作",
        action_required=True,
    )

    # 模擬 Editor：第 1 輪修改出乾淨稿（使 NarrativeAuditor 判定 PASS），第 2 輪為定稿
    editor_calls = {"count": 0}
    def mock_editor(novel_id, chapter_index, edit_instructions=None, stream=False, **kwargs):
        editor_calls["count"] += 1
        if editor_calls["count"] == 1:
            db.save_chapter(novel_id, chapter_index, _good_prose(seed="（第一輪乾淨稿）"))
        else:
            db.save_chapter(novel_id, chapter_index, _good_prose(seed="（第二輪定稿）"))
        def _gen(): yield "data: [DONE]"
        return _gen()
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor)

    # 模擬總監硬性校驗：第 1 輪判定失敗 (passed=False)，第 2 輪判定成功 (passed=True)
    director_check_calls = {"count": 0}
    def mock_director_check(novel_id, chapter_index):
        director_check_calls["count"] += 1
        if director_check_calls["count"] == 1:
            return {
                "passed": False,
                "issues": ["【套路句檢查】正文第 2 段含公式化動作『嘴角勾起冷笑』"],
                "message": "總監硬性校驗發現套路口癖殘留",
            }
        return {
            "passed": True,
            "issues": [],
            "message": "總監硬性校驗通過",
        }
    monkeypatch.setattr("backend.services.narrative.fix._run_director_check", mock_director_check)

    res = fix_chapter_until_pass(novel_id, 1, max_rounds=3)

    # 斷言：未因 targets 消失而提前以 no_change 崩潰，而是順利進入第 2 輪修訂並通過！
    assert res["status"] == "passed"
    assert len(res["rounds"]) == 2
    assert editor_calls["count"] == 2
    assert director_check_calls["count"] == 2
    assert res["director_check"]["passed"] is True

    db.delete_novel(novel_id)


def test_fix_loop_escalates_to_writer_on_editor_no_change(monkeypatch):
    """
    核心架構修復驗證（解決 Premature no_change exit）：
    當 Editor 未產生實質改動（changed == False）且尚有待處置審計時，
    系統升級調用 Writer 依總監指示進行情節重構，重構成功後再由 Editor 潤色收尾，
    避免提前以 no_change 終止。
    """
    novel_id = "test_fix_writer_escalation"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "Editor無改動升級測試", "玄幻", "升級")
    original_bad = _bad_prose()
    db.save_chapter(novel_id, 1, original_bad)

    db.add_narrative_audit(
        novel_id=novel_id,
        chapter_index=1,
        dimension="voice_integrity",
        severity="warning",
        evidence="口癖重複",
        recommendation="替換微動作",
        action_required=True,
    )

    writer_called = {"count": 0}
    def mock_writer(novel_id, chapter_index, user_prompt=None, stream=False, **kwargs):
        writer_called["count"] += 1
        # Writer 介入重構，寫入全新正文草稿
        db.save_chapter(novel_id, chapter_index, _good_prose(seed="（Writer 重構草稿）"))
        def _gen(): yield "data: [DONE]"
        return _gen()
    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", mock_writer)

    editor_called = {"count": 0}
    def mock_editor(novel_id, chapter_index, edit_instructions=None, stream=False, **kwargs):
        editor_called["count"] += 1
        if editor_called["count"] == 1:
            # 第一次：Editor 無任何改動（直接寫回原文，模擬卡住）
            db.save_chapter(novel_id, chapter_index, original_bad)
        else:
            # 第二次：在 Writer 重構後，Editor 進行最後潤色
            db.save_chapter(novel_id, chapter_index, _good_prose(seed="（Editor 潤色定稿）"))
        def _gen(): yield "data: [DONE]"
        return _gen()
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor)

    # 模擬 NarrativeAuditor 重審：潤色後通過
    def mock_audit(novel_id, chapter_index, prose_text=None, **kwargs):
        if "Editor 潤色定稿" in (prose_text or ""):
            return {"overall_action": "PASS", "findings": []}
        return {
            "overall_action": "REVISE",
            "findings": [{"dimension": "voice_integrity", "severity": "warning", "evidence": "口癖重複", "action_required": True}],
        }
    monkeypatch.setattr(NarrativeAuditor, "audit_chapter_prose", mock_audit)

    res = fix_chapter_until_pass(novel_id, 1)

    # 斷言：成功升級至 Writer 重構，未提前 no_change 崩潰，最終通過
    assert res["status"] == "passed"
    assert writer_called["count"] >= 1
    assert editor_called["count"] == 2

    db.delete_novel(novel_id)


def test_fix_loop_dynamic_split_on_density_overloaded(monkeypatch):
    """
    動態拆章回退機制驗證：
    當章節大綱被檢測為資訊密度過載時，
    fix_chapter_until_pass 立即啟動 split_and_expand_chapter_outline，
    將該章拆分為兩章並平移後續結構，正文錨定第 1 階段修復推進並順利通過。
    """
    novel_id = "test_fix_dynamic_split"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "動態拆章閉環測試", "奇幻", "冒險")

    # 建立具有密度過載的大綱（2 個重大轉折 + 3 個事件）
    dense_chapter_outline = {
        "chapter_index": 1,
        "chapter_title": "第 1 章：暗夜決戰要塞",
        "chapter_summary": "第一卷開端，主角遭遇重兵合圍並突圍至祭壇破解真相。",
        "events": [
            {"scene_index": 1, "location": "要塞城外", "content": "暗夜遭遇敵哨兵圍攻"},
            {"scene_index": 2, "location": "城內大廳", "content": "與敵首領展開搏殺"},
            {"scene_index": 3, "location": "深處祭壇", "content": "破解古老封印石"},
        ],
        "allocated_tasks": {
            "foreshadowing_plants": ["seed_alpha"],
            "foreshadowing_payoffs": ["seed_omega"],
            "turning_points": ["turn_betrayal", "turn_sacrifice"],
        },
        "scene_function": "climax",
    }
    volumes_data = [
        {
            "volume_index": 1,
            "title": "第 1 卷：要塞風雲",
            "chapter_count": 2,
            "chapters_outline": [
                dense_chapter_outline,
                {"chapter_index": 2, "chapter_title": "第 2 章：戰後餘波"},
            ],
        }
    ]
    save_volumes(novel_id, volumes_data)
    db.save_chapter(novel_id, 1, _bad_prose())

    # 記錄一條初始診斷
    db.add_narrative_audit(
        novel_id=novel_id,
        chapter_index=1,
        dimension="pacing_balance",
        severity="warning",
        evidence="節奏過於倉促，轉折點堆積",
        recommendation="放緩節奏或拆分情節",
        action_required=True,
    )

    # 模擬 Editor 潤色乾淨稿
    def mock_editor(novel_id, chapter_index, edit_instructions=None, stream=False, **kwargs):
        db.save_chapter(novel_id, chapter_index, _good_prose())
        def _gen(): yield "data: [DONE]"
        return _gen()
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor)

    # 執行 fix_chapter_until_pass
    res = fix_chapter_until_pass(novel_id, 1)

    assert res["status"] == "passed"
    assert res.get("split_occurred") is True

    # 驗證資料庫中的 volumes：第 1 卷總章數增至 3，第 1 章成功拆為兩章
    vols = get_volumes(novel_id)
    v1 = vols[0]
    assert v1["chapter_count"] == 3
    outlines = v1["chapters_outline"]
    assert len(outlines) == 3
    assert outlines[0]["chapter_index"] == 1
    assert "（上）" in outlines[0]["chapter_title"]
    assert outlines[1]["chapter_index"] == 2
    assert "（下）" in outlines[1]["chapter_title"]
    assert outlines[2]["chapter_index"] == 3
    assert "戰後餘波" in outlines[2]["chapter_title"]

    db.delete_novel(novel_id)
