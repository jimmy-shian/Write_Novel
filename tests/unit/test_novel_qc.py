# -*- coding: utf-8 -*-
"""novel_qc 純函數單元測試（不碰 DB）。"""
from tools.novel_qc import audit_engine as ae
from tools.novel_qc import context_pack as cp


def test_stratify_covers_five_strata():
    s = ae.stratify(550, 4)
    assert set(s) == {"前期", "中前期", "中期", "中後期", "後期"}
    assert all(len(v) == 4 for v in s.values())
    assert s["前期"][0] >= 1 and s["後期"][-1] <= 550


def test_adjacent_pairs():
    assert ae.adjacent_pairs(550, 3) == [(137, 138), (274, 275), (411, 412)] or \
        all(b - a == 1 for a, b in ae.adjacent_pairs(550, 3))


def test_jaccard_identical():
    assert ae.jaccard("林夜向前踏出一步", "林夜向前踏出一步") == 1.0
    assert ae.jaccard("完全不同的兩句話啊", "另一段毫不相干文字") < 0.5


def test_death_resurrection_detected():
    chs = [
        {"chapter_index": 1, "content": "林夜走進學院。"},
        {"chapter_index": 2, "content": "陸萬雄的身軀與靈魂在星隕下化作無數星屑，隨著陸萬雄的隕滅祭壇碎裂。"},
        {"chapter_index": 3, "content": "陸萬雄冷笑一聲，抬手說道：你們以為結束了嗎？"},
    ]
    out = ae.check_death_resurrection(chs, ["陸萬雄"])
    assert len(out) == 1
    assert out[0].death_chapters == [2]
    assert out[0].alive_after == [3]
    assert out[0].definitive


def test_death_with_note_not_flagged():
    chs = [
        {"chapter_index": 1, "content": "分身碎裂，陸萬雄的隕滅只是開始。"},
        {"chapter_index": 2, "content": "原來是分身！陸萬雄說道：本體還在。"},
    ]
    out = ae.check_death_resurrection(chs, ["陸萬雄"])
    assert out == []


def test_date_backflow():
    chs = [
        {"chapter_index": 1, "content": "魔法歷2148年3月16日中午，廣場集會。"},
        {"chapter_index": 2, "content": "魔法歷2148年3月12日清晨，指揮所動員。"},
    ]
    out = ae.check_date_monotonicity(chs)
    assert len(out) == 1 and out[0].chapter == 2 and not out[0].flashback_hint


def test_opener_stats():
    chs = [{"chapter_index": i,
            "content": "星軌綜合學院，高聳的魔力感應塔。" + "x" * 100}
           for i in range(1, 11)]
    stats = ae.check_opener_templates(chs)
    assert stats["markers"]["魔力感應塔"]["ratio"] == 1.0


def test_scoring_caps():
    findings = [{"id": "OPEN-01", "check": "opener_template", "severity": "minor",
                 "chapters": [], "evidence": []}
                for _ in range(50)]
    sc = cp.score_findings(findings)
    assert sc["scores"]["E"] >= 8  # 整體項封頂，不扣穿
    assert sc["scores"]["TOTAL"] <= 100
