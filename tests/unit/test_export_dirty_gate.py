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
