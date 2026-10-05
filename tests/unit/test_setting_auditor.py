from backend.agents.setting_auditor.runner import run_setting_audit


def test_chapter_audit_requires_scene_setting_coverage(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.setting_auditor.runner.SettingRegistry.record_setting_usage",
        lambda *args: True,
        raising=False,
    )

    result = run_setting_audit(
        "novel",
        "chapter",
        {
            "chapter_index": 3,
            "scene_setting": "北城檔案室",
            "content": "雨落在城外，兩人沉默地等待。",
        },
    )

    assert result["passed"] is False
    assert result["missing_keywords"]
    assert result["issues"]


def test_chapter_audit_accepts_explicit_scene_keywords(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.setting_auditor.runner.SettingRegistry.record_setting_usage",
        lambda *args: True,
        raising=False,
    )

    result = run_setting_audit(
        "novel",
        "chapter",
        {
            "chapter_index": 3,
            "scene_setting": "北城檔案室",
            "scene_setting_keywords": ["檔案室", "細雨"],
            "content": "檔案室裡落著細雨，燈影搖晃。",
        },
    )

    assert result["passed"] is True
    assert result["missing_keywords"] == []


def test_chapter_audit_without_prose_keeps_legacy_pass(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.setting_auditor.runner.SettingRegistry.record_setting_usage",
        lambda *args: True,
        raising=False,
    )

    result = run_setting_audit("novel", "chapter", {"chapter_index": 3})

    assert result["passed"] is True
