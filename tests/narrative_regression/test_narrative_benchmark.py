# -*- coding: utf-8 -*-
"""
Narrative Regression Benchmark Suite
"""

import random
import re
from typing import Any, Dict, List, Tuple
import pytest

CLICHE_PATTERNS = [
    r"指尖(?:輕微)?顫抖",
    r"空氣(?:彷彿)?(?:瞬間)?凝固",
    r"命運的重量",
    r"喉嚨(?:一陣)?發緊",
    r"心頭(?:不由得)?一緊",
    r"像被撕裂的碎片",
    r"倒吸一口涼氣",
]

MECHANICAL_CATCHPHRASE_PATTERNS = [
    r"……啊[？!！。，\s」』]",
    r"呦[？!！。，\s」』]",
    r"是。[？!！。，\s」』]",
]


def detect_cliches(prose: str) -> List[str]:
    found = []
    for pat in CLICHE_PATTERNS:
        matches = re.findall(pat, prose)
        if matches:
            found.extend(matches)
    return found


def detect_mechanical_catchphrases(prose: str) -> List[str]:
    found = []
    for pat in MECHANICAL_CATCHPHRASE_PATTERNS:
        matches = re.findall(pat, prose)
        if matches:
            found.extend(matches)
    return found


def detect_info_dump_markers(prose: str) -> List[str]:
    patterns = [
        r"根據.*?組織設定",
        r"根據.*?的設定",
        r"在世界觀中",
        r"所謂的.*?體系分為",
        r"按照.*?的規則來說",
        r"作為一個擁有.*?身份的人",
    ]
    found = []
    for pat in patterns:
        matches = re.findall(pat, prose)
        if matches:
            found.extend(matches)
    return found


def pairwise_blind_eval(
    candidate_a: str,
    candidate_b: str,
    eval_metric_fn,
) -> Tuple[float, float]:
    score_a_1 = eval_metric_fn(candidate_a)
    score_b_1 = eval_metric_fn(candidate_b)

    order = random.choice([True, False])
    if order:
        first, second = candidate_a, candidate_b
        s_first, s_second = eval_metric_fn(first), eval_metric_fn(second)
        total_a = (score_a_1 + s_first) / 2.0
        total_b = (score_b_1 + s_second) / 2.0
    else:
        first, second = candidate_b, candidate_a
        s_first, s_second = eval_metric_fn(first), eval_metric_fn(second)
        total_a = (score_a_1 + s_second) / 2.0
        total_b = (score_b_1 + s_first) / 2.0

    return total_a, total_b


def test_benchmark_scenario_high_tension_interrogation():
    good_prose = """
    昏黃的檯燈在鐵桌中央投下一道刺眼的冷光。林澤拉開鐵椅坐下，金屬摩擦地面的尖銳聲在審訊室內迴盪。
    對面的男人雙手被銬在桌沿，指關節泛白，但目光始終停留在林澤領口微露的徽記上。
    「你只有三分鐘。」林澤翻開文件夾，推到桌子正中，「昨夜三號倉庫的火，是誰點的？」
    男人嘴角動了動，發出一聲極輕的冷笑，沒有立刻回答。他避開了林澤審視的視線，抬頭看向天花板旋轉的排風扇。
    「林調查官，你比任何人都清楚那裡放著什麼。」男人的聲音沙啞，措辭極其緩慢，「若真是我做的，你現在拿到的就不會是這份未簽字的轉移單。」
    林澤盯著他的眼睛。對方的呼吸節奏沒有亂，但放在膝蓋上的手指正無意識地扣緊布料——他在隱瞞更深的事情，而不是這場火本身。
    """

    bad_prose = """
    林澤走進審訊室。根據帝國第三情報部的組織設定，審訊官擁有最高處置權。
    李四坐在對面，李四心裡非常害怕，李四心想：完了，林澤肯定已經知道了昨晚的秘密，我絕對不能供出幕後黑手張三！
    林澤感到指尖輕微顫抖，空氣瞬間凝固，彷彿有命運的重量壓在胸口。
    「你說不說……啊？」林澤問道，語氣帶著他的口頭禪。
    「我不知道呦。」李四回答道。
    """

    assert len(detect_cliches(good_prose)) == 0
    assert len(detect_mechanical_catchphrases(good_prose)) == 0
    assert len(detect_info_dump_markers(good_prose)) == 0

    bad_cliches = detect_cliches(bad_prose)
    assert len(bad_cliches) >= 2

    bad_catchphrases = detect_mechanical_catchphrases(bad_prose)
    assert len(bad_catchphrases) >= 2

    bad_dumps = detect_info_dump_markers(bad_prose)
    assert len(bad_dumps) >= 1


def test_benchmark_scenario_travel_transition():
    efficient_transition = """
    車隊在暴風雪中跋涉了四天。穿過黑松林時凍死了兩匹馱馬，原本預計在第七天抵達的北境防線，直到第五天黃昏才在風雪的裂隙中露出哨塔的黑影。
    林澤跳下馬車，靴底深陷進半尺厚的積雪中。城門下的哨兵裹著厚重的獸皮，長槍上的鐵鏽已被凍成了暗黑色。
    「通行證。」哨兵的聲音隔著面罩傳來。
    林澤遞出蓋有密印的羊皮紙，掌心已感受不到金屬令牌的冰冷。
    """

    assert len(efficient_transition.strip()) > 100
    assert "四天" in efficient_transition
    assert len(detect_cliches(efficient_transition)) == 0


def test_position_bias_mitigation():
    def dummy_quality_scorer(text: str) -> float:
        score = 10.0
        score -= len(detect_cliches(text)) * 2.0
        score -= len(detect_mechanical_catchphrases(text)) * 2.0
        score -= len(detect_info_dump_markers(text)) * 3.0
        return max(0.0, score)

    good = "林澤推開木門，冷風灌入走廊。他看了一眼手錶，距離交接還有十分鐘。"
    flawed = "林澤推開木門。指尖輕微顫抖，空氣凝固了……啊。根據組織設定，這座城堡有三百年歷史。"

    score_good, score_flawed = pairwise_blind_eval(good, flawed, dummy_quality_scorer)
    assert score_good > score_flawed
    assert score_good == 10.0
    assert score_flawed <= 5.0
