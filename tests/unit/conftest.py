# -*- coding: utf-8 -*-
"""
tests/unit 共用 fixtures：
- 載入時確保 DB schema 為最新
- novel_factory：建立測試用小說，測試結束自動級聯刪除
"""
import uuid

import pytest

from backend import persistence as db

# 確保測試執行前 DB schema 最新
db.db_init()


@pytest.fixture
def novel_factory():
    """建立測試小說，並在測試結束後自動清理（含所有關聯資料）。"""
    created_ids = []

    def _create(title="測試小說", genre="玄幻", style="熱血", novel_id=None):
        nid = novel_id or f"test_{uuid.uuid4().hex[:12]}"
        db.delete_novel(nid)  # 確保乾淨起點
        db.create_novel(nid, title, genre, style)
        created_ids.append(nid)
        return nid

    yield _create

    for nid in created_ids:
        try:
            db.delete_novel(nid)
        except Exception:
            pass