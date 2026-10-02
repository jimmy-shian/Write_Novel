# -*- coding: utf-8 -*-
"""Test frontend build integration and static serving in FastAPI."""

import os
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_static_index_serves_react():
    """Verify GET / returns the built React app from frontend/dist."""
    response = client.get("/")
    assert response.status_code == 200
    # Must contain Vite / React entry tags
    assert "OpenDesign" in response.text or "root" in response.text
    assert "<div id=\"root\"></div>" in response.text

def test_api_version_endpoint_matches_ssot():
    """Verify backend API version matches version.json (SSOT)."""
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "version.json"), encoding="utf-8") as f:
        ssot = json.load(f)
    from backend.common.version import get_version, get_app_info
    info = get_app_info()
    assert info["version"] == ssot["version"]
    assert app.version == ssot["version"]
    assert get_version() == ssot["version"]

def test_legacy_static_files_removed():
    """Verify that frontend/static legacy files have been completely deprecated and removed."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    legacy_static_dir = os.path.join(root, "frontend", "static")
    assert not os.path.exists(legacy_static_dir), f"Legacy directory {legacy_static_dir} should not exist."

def test_get_static_dir_exclusively_targets_dist():
    """Verify get_static_dir returns frontend/dist and never falls back to legacy static."""
    from backend.app import get_static_dir
    static_dir = get_static_dir()
    assert static_dir is not None
    assert static_dir.endswith("dist")
    assert os.path.exists(os.path.join(static_dir, "index.html"))

def test_get_static_dir_returns_none_when_dist_missing(monkeypatch):
    """Verify get_static_dir returns None when frontend/dist/index.html is missing, with no legacy fallback."""
    from backend.app import get_static_dir
    original_exists = os.path.exists

    def mock_exists(path):
        if "frontend" in path and ("dist" in path or "static" in path):
            return False
        return original_exists(path)

    monkeypatch.setattr(os.path, "exists", mock_exists)
    assert get_static_dir() is None

def test_serve_index_when_dist_missing_returns_helpful_message(monkeypatch):
    """Verify GET / returns a clear message when dist is missing."""
    import backend.app as app_module
    monkeypatch.setattr(app_module, "get_static_dir", lambda: None)
    monkeypatch.setattr(app_module, "static_dir", None)
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Novel Factory" in response.text


