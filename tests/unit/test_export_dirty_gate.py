from fastapi.testclient import TestClient

from backend import persistence as db
from backend.app import app


client = TestClient(app)


def test_export_excludes_dirty_chapters_but_keeps_clean_chapters():
    novel_id = "test_export_dirty_gate"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "匯出 dirty gate", "奇幻", "沉浸")
    db.save_chapter(novel_id, 1, "乾淨章節應該出現在匯出結果。")
    db.save_chapter(novel_id, 2, "未通過的草稿不應該出現在匯出結果。", is_dirty=True)

    try:
        txt = client.get(f"/api/novels/{novel_id}/export?format=txt")
        assert txt.status_code == 200
        assert "乾淨章節應該出現在匯出結果" in txt.text
        assert "未通過的草稿不應該出現在匯出結果" not in txt.text

        html = client.get(f"/api/novels/{novel_id}/export?format=html")
        assert html.status_code == 200
        assert "乾淨章節應該出現在匯出結果" in html.text
        assert "未通過的草稿不應該出現在匯出結果" not in html.text
    finally:
        db.delete_novel(novel_id)


def test_export_blocks_unresolved_critical_audit():
    novel_id = "test_export_critical_gate"
    db.delete_novel(novel_id)
    db.create_novel(novel_id, "critical gate", "奇幻", "沉浸")
    db.save_chapter(novel_id, 1, "乾淨章節正文，內容長度與格式均符合匯出測試要求。")
    db.add_narrative_audit(
        novel_id=novel_id,
        chapter_index=1,
        dimension="timeline",
        severity="critical",
        evidence="時間倒流",
        recommendation="修正時間錨點",
        action_required=True,
    )
    try:
        response = client.get(f"/api/novels/{novel_id}/export?format=txt")
        assert response.status_code == 409
        assert "未結 critical" in response.text
    finally:
        db.delete_novel(novel_id)
