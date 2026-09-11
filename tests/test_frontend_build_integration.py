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
