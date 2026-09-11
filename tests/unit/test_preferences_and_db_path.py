# -*- coding: utf-8 -*-
import os
from fastapi.testclient import TestClient
from backend.app import app
from backend.persistence import (
    db_init,
    set_app_preference,
    get_app_preference,
    get_all_app_preferences,
    DB_PATH,
)


def test_app_preferences_persistence():
    db_init()
    # 測試單一鍵值存取
    set_app_preference("theme", "neutral")
    assert get_app_preference("theme") == "neutral"

    set_app_preference("editor_font_size", 18)
    assert str(get_app_preference("editor_font_size")) == "18"

    all_prefs = get_all_app_preferences()
    assert all_prefs.get("theme") == "neutral"
    assert all_prefs.get("editor_font_size") == "18"


def test_preferences_api_endpoints():
    client = TestClient(app)

    # 測試 POST /api/settings/preferences
    res = client.post(
        "/api/settings/preferences",
        json={"preferences": {"theme": "light", "editor_font_size": 20}},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["preferences"]["theme"] == "light"
    assert res.json()["preferences"]["editor_font_size"] == "20"

    # 測試 GET /api/settings/preferences
    get_res = client.get("/api/settings/preferences")
    assert get_res.status_code == 200
    assert get_res.json()["preferences"]["theme"] == "light"

    # 測試 GET /api/settings 包含 _preferences 與 _dbPath
    settings_res = client.get("/api/settings")
    assert settings_res.status_code == 200
    snap = settings_res.json()
    assert "_preferences" in snap
    assert snap["_preferences"]["theme"] == "light"
    assert "_dbPath" in snap
    assert os.path.isabs(snap["_dbPath"])


def test_sync_status_db_path_is_absolute():
    client = TestClient(app)
    res = client.get("/api/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert "db_path" in data
    assert os.path.isabs(data["db_path"])
    assert data["db_path"] == os.path.abspath(DB_PATH)
