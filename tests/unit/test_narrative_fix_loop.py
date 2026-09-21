# -*- coding: utf-8 -*-
"""
Story Engine 2.0: 閉環修正迴圈（fix_chapter_until_pass）回歸測試
鎖住「修到總監/引擎評斷通過」行為：
- 一輪即通過 / 多輪後通過 / 達安全上限停止 / Editor 無改動即中止
- 流水線 2.7 已改接此迴圈（import 健全性檢查）
"""

import pytest
from backend import persistence as db
from backend.services.narrative import NarrativeAuditor, ConflictLedger
from backend.services.narrative.fix import (
    fix_chapter_until_pass,
    build_director_user_instruction,
    DEFAULT_MAX_FIX_ROUNDS,
)


@pytest.fixture(autouse=True)
def _mock_director_llm(monkeypatch):
    """所有測試一律 mock 總監 LLM：不外呼，並記錄收到的 user_prompt 供斷言。"""
    import backend.common.llm as llm_mod
    captured = {"prompts": []}

    def fake_call_llm(agent_name, system_prompt, user_prompt, **kwargs):
        captured["prompts"].append({"system": system_prompt, "user": user_prompt})
        return "請把模板化動作換成角色獨特微動作，並為破局補上實質代價。"

    monkeypatch.setattr(llm_mod, "call_llm", fake_call_llm)
    yield captured


@pytest.fixture(autouse=True)
def _mock_writer_agent(monkeypatch):
    """預設 mock chapter writer，回傳空 generator；個別測試可自行覆寫。"""
    def fake_writer(novel_id, chapter_index, user_prompt="", stream=False, **kwargs):
        def _gen():
            yield "data: [DONE]"
        return _gen()
    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", fake_writer)


GESTURE_A = "嘴角微微勾起一抹冷笑"
GESTURE_B = "眼神深處閃過一抹寒芒"


def _bad_prose(seed: str = "") -> str:
    """含兩類套路口癖（合計 > 3 次）→ voice_integrity warning + action_required → REVISE"""
    base = (
        f"李斯特冷冷注視著眼前的軍官，{GESTURE_A}。"
        f"『區區螻蟻，也敢擋我的路？』他開口時{GESTURE_B}，四周空氣彷彿凝固。"
        "軍官握緊長槍，喉結滾動，卻不敢後退半步，汗水沿著頭盔內緣滑落。"
    )
    prose = (base * 14) + seed
    assert len(prose) >= 1000, "editor 階段硬性校驗要求正文至少 1000 字"
    return prose


def _clean_prose(seed: str = "") -> str:
    """無任何套路口癖的健全正文 → 審計 PASS"""
    base = (
        "李斯特把油燈芯撥低，指尖沿著地圖上的一道舊折痕慢慢壓平，"
        "紙面邊緣還留著昨夜雨水滲進帳篷時暈開的潮氣。"
        "軍官把令牌推回桌心，沒有再多說一個字，只把披風上的扣环繫緊了半格。"
    )
    prose = (base * 15) + seed
    assert len(prose) >= 1000, "editor 階段硬性校驗要求正文至少 1000 字"
    return prose


def _negotiation_prose() -> str:
    """談判斡旋與利益交換的健全正文 -> ConflictLedger 提取 strategy=negotiation, outcome=uneasy_truce"""
    base = (
        "李斯特在長桌前緩緩坐下，將手中的利益協議推至對方面前，"
        "以北境三座礦脈的開採份額作為談判條件，換取邊界駐軍的退讓。"
        "雙方在羊皮紙上簽下名字，長達數月的對峙至此達成和解與暫歇。"
    )
    prose = (base * 15)
    assert len(prose) >= 1000, "editor 階段硬性校驗要求正文至少 1000 字"
    return prose


def _make_writer_mock(script):
    """
    產生假的 run_chapter_writer：依 script 順序把新正文寫入 DB（模擬 Writer 重構草稿），
    回傳 SSE 生成器以符合 fix_chapter_from_audits 的消費方式。
    """
    state = {"calls": 0, "prompts": []}

    def fake_run_chapter_writer(novel_id, chapter_index, user_prompt="", stream=False, **kwargs):
        state["calls"] += 1
        state["prompts"].append(user_prompt)
        content = script[min(state["calls"] - 1, len(script) - 1)]
        db.save_chapter(novel_id, chapter_index, content)

        def _gen():
            yield "data: [DONE]"
        return _gen()

    return fake_run_chapter_writer, state


def _make_editor_mock(script):
    """
    產生假的 run_editor_agent：依 script 順序把新正文寫入 DB（模擬 Editor 存檔），
    回傳 SSE 生成器以符合 fix_chapter_from_audits 的消費方式。
    """
    state = {"calls": 0}

    def fake_run_editor_agent(novel_id, chapter_index, edit_instructions="", stream=False, **kwargs):
        assert edit_instructions, "必須攜帶診斷編輯指示"
        content = script[min(state["calls"], len(script) - 1)]
        state["calls"] += 1
        db.save_chapter(novel_id, chapter_index, content)

        def _gen():
            yield "data: [DONE]"
        return _gen()

    return fake_run_editor_agent, state


def test_fix_loop_passes_in_one_round(monkeypatch):
    novel_id = "test_fix_loop_pass1"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "閉環一輪通過", "玄幻", "升級")
    db.save_chapter(novel_id, 1, _bad_prose())

    audit = NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id, chapter_index=1,
        prose_text=_bad_prose(), current_outline={"scene_function": "climax"},
    )
    assert audit["overall_action"] == "REVISE"

    fake, state = _make_editor_mock([_clean_prose()])
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", fake)

    res = fix_chapter_until_pass(novel_id, 1)
    assert res["status"] == "passed"
    assert len(res["rounds"]) == 1
    assert state["calls"] == 1
    assert res["final_action"] in ("PASS", "NO_ACTION_REQUIRED")
    assert res["director_check"] is not None
    assert res["director_check"]["passed"] is True
    # 所有診斷應已全數處置
    audits = db.get_narrative_audits(novel_id, chapter_index=1)
    assert audits and all(a.get("resolved") in (1, True) for a in audits)

    db.delete_novel(novel_id)


def test_fix_loop_keeps_fixing_until_pass(monkeypatch):
    """第一輪重寫後仍 REVISE，必須繼續修到引擎判通過，不得只修一次就放行。"""
    novel_id = "test_fix_loop_multi"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "閉環多輪通過", "玄幻", "升級")
    db.save_chapter(novel_id, 1, _bad_prose())

    NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id, chapter_index=1,
        prose_text=_bad_prose(), current_outline={"scene_function": "climax"},
    )

    # 第 1 輪改了但仍是壞稿；第 2 輪才修乾淨
    fake, state = _make_editor_mock([_bad_prose(seed="（第一輪殘稿）"), _clean_prose()])
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", fake)

    res = fix_chapter_until_pass(novel_id, 1)
    assert res["status"] == "passed"
    assert len(res["rounds"]) == 2
    assert state["calls"] == 2
    assert res["rounds"][0]["reaudit"]["overall_action"] == "REVISE"
    assert res["rounds"][1]["reaudit"]["overall_action"] in ("PASS", "NO_ACTION_REQUIRED")
    assert res["total_fixed"] >= 2

    db.delete_novel(novel_id)


def test_fix_loop_stops_at_max_rounds(monkeypatch):
    """達安全上限仍未通過 → status=max_rounds，不得無限迴圈。"""
    novel_id = "test_fix_loop_max"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "閉環上限測試", "玄幻", "升級")
    db.save_chapter(novel_id, 1, _bad_prose())

    NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id, chapter_index=1,
        prose_text=_bad_prose(), current_outline={"scene_function": "climax"},
    )

    # 每輪都改出新版本但始終不乾淨
    fake, state = _make_editor_mock([_bad_prose(seed=f"（殘稿{ i }）") for i in range(1, 6)])
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", fake)

    res = fix_chapter_until_pass(novel_id, 1, max_rounds=2)
    assert res["status"] == "max_rounds"
    assert len(res["rounds"]) == 2
    assert state["calls"] == 2
    assert res["final_action"] == "REVISE"

    db.delete_novel(novel_id)


def test_fix_loop_stops_when_editor_no_change(monkeypatch):
    """Editor 未產生新版（原文保留）→ status=no_change，立即中止不空轉。"""
    novel_id = "test_fix_loop_nochg"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "閉環無改動", "玄幻", "升級")
    original = _bad_prose()
    db.save_chapter(novel_id, 1, original)

    NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id, chapter_index=1,
        prose_text=original, current_outline={"scene_function": "climax"},
    )

    fake, state = _make_editor_mock([original])  # 寫回原稿 → changed=False
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", fake)

    res = fix_chapter_until_pass(novel_id, 1)
    assert res["status"] == "no_change"
    assert len(res["rounds"]) == 1
    assert state["calls"] == 1
    assert res["total_fixed"] == 0

    db.delete_novel(novel_id)


def test_director_instruction_includes_engine_and_reaudit_findings(_mock_director_llm):
    """總監合成 user 指令時，必須納入引擎診斷與上一輪重審的殘留建議。"""
    targets = [{
        "dimension": "voice_integrity",
        "evidence": "嘴角勾起笑意/冷笑 (出現 5 次)",
        "recommendation": "替換為角色獨特微動作",
    }]
    reaudit_findings = [{
        "dimension": "ability_constraints",
        "severity": "watch",
        "evidence": "破局後未體現任何代價",
        "recommendation": "補上能力冷卻與情報暴露描寫",
    }]
    instruction = build_director_user_instruction(
        "test_novel_any", 3, targets, reaudit_findings=reaudit_findings,
    )
    # LLM 有回應 → 採用總監合成指令，且紅線附註保留
    assert "總監指令" not in instruction  # 非 JSON/模板抬頭
    assert "不得改變本章大綱" in instruction
    # 引擎重審建議必須出現在餵給總監的 user_prompt 中
    sent = _mock_director_llm["prompts"][-1]["user"]
    assert "引擎重審" in sent
    assert "補上能力冷卻與情報暴露描寫" in sent
    assert "替換為角色獨特微動作" in sent


def test_director_instruction_falls_back_offline(_mock_director_llm, monkeypatch):
    """LLM 掛掉時降級回離線模板，閉環不斷鏈。"""
    import backend.common.llm as llm_mod

    def boom(*a, **kw):
        raise RuntimeError("LLM offline")
    monkeypatch.setattr(llm_mod, "call_llm", boom)

    targets = [{
        "dimension": "voice_integrity",
        "evidence": "嘴角勾起笑意/冷笑 (出現 5 次)",
        "recommendation": "替換為角色獨特微動作",
    }]
    instruction = build_director_user_instruction("test_novel_any", 1, targets)
    assert "總監 2.0 敘事診斷定向修正" in instruction
    assert "替換為角色獨特微動作" in instruction
    assert "不得改變本章大綱" in instruction


def test_loop_feeds_reaudit_findings_to_director_next_round(monkeypatch, _mock_director_llm):
    """第 2 輪給總監的 user_prompt 必須含第 1 輪引擎重審的殘留建議。"""
    novel_id = "test_fix_loop_director"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "閉環總監指令", "玄幻", "升級")
    db.save_chapter(novel_id, 1, _bad_prose())

    NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id, chapter_index=1,
        prose_text=_bad_prose(), current_outline={"scene_function": "climax"},
    )

    fake, state = _make_editor_mock([_bad_prose(seed="（第一輪殘稿）"), _clean_prose()])
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", fake)

    res = fix_chapter_until_pass(novel_id, 1)
    assert res["status"] == "passed"
    assert len(res["rounds"]) == 2
    # 兩輪都呼叫過總監 LLM；第 2 輪的 user_prompt 必須帶入第 1 輪重審 findings
    assert len(_mock_director_llm["prompts"]) >= 2
    second_user = _mock_director_llm["prompts"][1]["user"]
    assert "引擎重審" in second_user

    db.delete_novel(novel_id)


def test_pipeline_wires_until_pass_loop():
    """流水線 2.7 必須接上 fix_chapter_until_pass（修到通過），不得回退為單輪修正。"""
    import inspect
    import backend.services.autonomous_pipeline as ap
    src = inspect.getsource(ap)
    assert "fix_chapter_until_pass" in src
    assert "fix_chapter_from_audits as _auto_fix(" not in src
    from backend.services.autonomous_pipeline import autonomous_manager  # noqa: F401
    assert DEFAULT_MAX_FIX_ROUNDS >= 2


def test_fix_loop_resolves_conflict_novelty(monkeypatch, _mock_director_llm):
    """
    核心架構測試：
    當出現 conflict_novelty 重複警告時，
    閉環走「Writer 重寫因果模式 -> Editor 潤色 -> 重新提取簽名 -> 重審通過」流程，
    徹底打破舊簽名重複導致的死胡同。
    """
    novel_id = "test_fix_loop_novelty"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "衝突防重複閉環", "玄幻", "升級")

    # 第 1 章已記錄簽名：衝突推進 -> 裝傻示弱 -> 震驚
    ConflictLedger.record_signature(
        novel_id=novel_id,
        chapter_start=1,
        chapter_end=1,
        pressure_type="衝突推進",
        protagonist_strategy="play_dumb_or_weak",
        outcome="public_shock",
        initiator="執法長老",
    )

    # 第 2 章初稿：因果模式完全一致（打壓 -> 裝傻示弱 -> 震驚）
    bad_chap2 = (
        "長老院的執事冷笑著步步逼近，氣勢凌人地進行打壓。"
        "李斯特低下頭，故意裝傻示弱，任由對方嘲弄。"
        "直到關鍵時刻他暴起反制，全場長老駭然呆滯，陷入巨大的震驚之中。"
    ) * 12
    db.save_chapter(novel_id, 2, bad_chap2)

    # 第 2 章初次審計並寫入 DB
    ch2_sig = ConflictLedger.extract_signature_from_chapter(
        novel_id=novel_id,
        chapter_index=2,
        prose_text=bad_chap2,
    )
    audit = NarrativeAuditor.audit_chapter_prose(
        novel_id=novel_id,
        chapter_index=2,
        prose_text=bad_chap2,
        candidate_conflict_sig=ch2_sig,
    )
    assert audit["overall_action"] == "REVISE"
    novelty_findings = [f for f in audit["findings"] if f["dimension"] == "conflict_novelty"]
    assert len(novelty_findings) > 0
    assert novelty_findings[0]["action_required"] is True

    # 模擬 Writer 依總監指令重構情節（改為談判與利益交換）
    writer_prose = _negotiation_prose()
    w_fake, w_state = _make_writer_mock([writer_prose])
    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", w_fake)

    # Editor 潤色（保持談判內容並精修）
    e_fake, e_state = _make_editor_mock([writer_prose])
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", e_fake)

    res = fix_chapter_until_pass(novel_id, 2)

    # 斷言：一輪即重構因果並通過
    assert res["status"] == "passed"
    assert len(res["rounds"]) == 1
    assert w_state["calls"] == 1
    assert e_state["calls"] == 1

    # 斷言：總監 prompt 與重審皆已解決 conflict_novelty
    reaudit = res["final_reaudit"]
    assert reaudit is not None
    assert reaudit["overall_action"] in ("PASS", "NO_ACTION_REQUIRED")
    remaining_novelty = [f for f in reaudit.get("findings", []) if f["dimension"] == "conflict_novelty"]
    assert len(remaining_novelty) == 0

    # 斷言：帳本中第 2 章的衝突簽名已被更新為談判斡旋，不再是裝傻
    signatures = db.get_conflict_signatures(novel_id)
    ch2_updated_sig = next((s for s in signatures if s["chapter_start"] == 2), None)
    assert ch2_updated_sig is not None
    assert ch2_updated_sig["protagonist_strategy"] == "negotiation"

    db.delete_novel(novel_id)