from backend.services.director.tool_registry.evaluator import (
    _validate_chapter_setting_and_continuity,
)


def test_scene_setting_keywords_accept_non_numeric_location():
    issues = _validate_chapter_setting_and_continuity(
        "北城檔案室的細雨沿著窗框滑落。",
        {"scene_setting": {"location": "北城檔案室", "weather": "細雨"}},
        "",
        1,
    )

    assert not any(issue.startswith("【場景地點漂移】") for issue in issues)


def test_scene_setting_keywords_reject_wrong_location():
    issues = _validate_chapter_setting_and_continuity(
        "南城檔案室的門在夜色裡敞開。",
        {"scene_setting": "北城檔案室"},
        "",
        1,
    )

    assert any(issue.startswith("【場景地點漂移】") for issue in issues)


def test_scene_setting_keywords_keep_numeric_room_check():
    issues = _validate_chapter_setting_and_continuity(
        "走進 204 房時，冷氣正滴著水。",
        {"scene_setting": "醫院 203 房"},
        "",
        1,
    )

    assert any("大綱指定房號為「203室」" in issue for issue in issues)


def test_long_chinese_description_does_not_trigger_critical():
    # 長中文場景描述：只有部分氛圍詞在首段，不含強地標，不得觸發 critical 的【場景地點漂移】
    issues = _validate_chapter_setting_and_continuity(
        "月色皎潔，夜風微涼，長廊下一片寂靜。",
        {"scene_setting": "月色皎潔，微風拂過青石小徑，四下幽靜無聲，空氣中帶著草木濕氣與隱隱的壓抑感"},
        "",
        1,
    )
    # 不應觸發 critical 的【場景地點漂移】
    assert not any(issue.startswith("【場景地點漂移】") for issue in issues)


def test_atmosphere_missing_is_warning_not_critical():
    # 完全沒有強地標，只有氣氛詞且完全缺失時，只給 warning
    issues = _validate_chapter_setting_and_continuity(
        "眾人紛紛舉杯高呼，喧鬧之聲震耳欲聾。",
        {"scene_setting": "幽暗陰鬱，寂靜森冷，寒氣刺骨"},
        "",
        1,
    )
    assert not any(issue.startswith("【場景地點漂移】") for issue in issues)
    assert any("【場景氛圍提醒】" in issue for issue in issues)


def test_wrong_room_triggers_critical():
    # 房號錯誤必須觸發 critical 的【場景地點漂移】
    issues = _validate_chapter_setting_and_continuity(
        "他推開 502 室的大門，裡面空無一人。",
        {"scene_setting": "辦公大樓 501 室"},
        "",
        1,
    )
    assert any(issue.startswith("【場景地點漂移】") and "501室" in issue for issue in issues)
