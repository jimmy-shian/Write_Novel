# -*- coding: utf-8 -*-
"""
Story Terms / Glossary Repository.
Tracks novel-specific terminology, proper nouns, and constraints.
"""
import uuid
from typing import Dict, Any, List, Optional
from backend.persistence.connection import get_db_connection

def _term_columns(conn) -> List[str]:
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(story_terms)").fetchall()]
    except Exception:
        return []


def create_term(
    novel_id: str,
    category: str,
    term: str,
    definition: str,
    notes: str = "",
    source_chapter: Optional[int] = None,
    updated_chapter: Optional[int] = None,
) -> Dict[str, Any]:
    """建立術語。source_chapter 為 None 代表手動術語，不隨章節清除連動刪除。"""
    term_id = f"term_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    cursor = conn.cursor()
    has_chapter_cols = "source_chapter" in _term_columns(conn)
    if has_chapter_cols:
        cursor.execute("""
            INSERT INTO story_terms (id, novel_id, category, term, definition, notes, source_chapter, updated_chapter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (term_id, novel_id, category.strip(), term.strip(), definition.strip(),
              notes.strip(), source_chapter, updated_chapter if updated_chapter is not None else source_chapter))
    else:
        cursor.execute("""
            INSERT INTO story_terms (id, novel_id, category, term, definition, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (term_id, novel_id, category.strip(), term.strip(), definition.strip(), notes.strip()))
    conn.commit()
    return {
        "id": term_id,
        "novel_id": novel_id,
        "category": category.strip(),
        "term": term.strip(),
        "definition": definition.strip(),
        "notes": notes.strip(),
        "source_chapter": source_chapter,
        "updated_chapter": updated_chapter if updated_chapter is not None else source_chapter,
    }


def upsert_term(
    novel_id: str,
    category: str,
    term: str,
    definition: str,
    notes: str = "",
    source_chapter: Optional[int] = None,
    updated_chapter: Optional[int] = None,
) -> Dict[str, Any]:
    """按 (novel_id, term) 去重寫入。

    - 手動術語 (source_chapter IS NULL) 優先保留：自動同步不會覆寫其分類/定義。
    - 自動術語以最新章節的整理結果為準並更新 updated_chapter。
    回傳包含 "action" ("created"/"updated"/"kept_manual") 的 dict。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    has_chapter_cols = "source_chapter" in _term_columns(conn)
    name = (term or "").strip()
    if not name:
        raise ValueError("Term is required")
    if has_chapter_cols:
        row = cursor.execute(
            "SELECT * FROM story_terms WHERE novel_id = ? AND term = ? LIMIT 1",
            (novel_id, name),
        ).fetchone()
    else:
        row = cursor.execute(
            "SELECT * FROM story_terms WHERE novel_id = ? AND term = ? LIMIT 1",
            (novel_id, name),
        ).fetchone()
    if row:
        existing = dict(row)
        if has_chapter_cols and existing.get("source_chapter") is None and source_chapter is not None:
            # 手動術語優先：自動同步不覆寫，僅回報。
            return {**_row_to_term(existing), "action": "kept_manual"}
        if has_chapter_cols:
            cursor.execute("""
                UPDATE story_terms
                SET category = ?, definition = ?, notes = ?, updated_chapter = ?
                WHERE id = ?
            """, (category.strip() or existing.get("category", ""), definition.strip(),
                  notes.strip(), updated_chapter if updated_chapter is not None else source_chapter,
                  existing["id"]))
        else:
            cursor.execute("""
                UPDATE story_terms
                SET category = ?, definition = ?, notes = ?
                WHERE id = ?
            """, (category.strip() or existing.get("category", ""), definition.strip(),
                  notes.strip(), existing["id"]))
        conn.commit()
        refreshed = cursor.execute("SELECT * FROM story_terms WHERE id = ?", (existing["id"],)).fetchone()
        return {**_row_to_term(dict(refreshed)), "action": "updated"}
    created = create_term(novel_id, category, name, definition, notes,
                          source_chapter=source_chapter, updated_chapter=updated_chapter)
    return {**created, "action": "created"}


def _row_to_term(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "novel_id": r["novel_id"],
        "category": r["category"],
        "term": r["term"],
        "definition": r["definition"],
        "notes": r.get("notes") or "",
        "source_chapter": r.get("source_chapter"),
        "updated_chapter": r.get("updated_chapter"),
        "created_at": str(r.get("created_at")) if r.get("created_at") else None,
    }

def get_terms(novel_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute("""
            SELECT * FROM story_terms WHERE novel_id = ? AND category = ?
            ORDER BY term ASC
        """, (novel_id, category))
    else:
        cursor.execute("""
            SELECT * FROM story_terms WHERE novel_id = ?
            ORDER BY category ASC, term ASC
        """, (novel_id,))
    rows = cursor.fetchall()
    return [_row_to_term(dict(r)) for r in rows]


def delete_terms_by_chapter(novel_id: str, chapter_index: int) -> int:
    """刪除由指定章節自動衍生的術語（手動術語 source_chapter IS NULL 會保留）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if "source_chapter" not in _term_columns(conn):
        return 0
    cursor.execute(
        "DELETE FROM story_terms WHERE novel_id = ? AND source_chapter = ?",
        (novel_id, int(chapter_index)),
    )
    conn.commit()
    return cursor.rowcount


def delete_auto_terms(novel_id: str) -> int:
    """刪除該小說全部自動衍生術語（手動術語保留）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if "source_chapter" not in _term_columns(conn):
        return 0
    cursor.execute(
        "DELETE FROM story_terms WHERE novel_id = ? AND source_chapter IS NOT NULL",
        (novel_id,),
    )
    conn.commit()
    return cursor.rowcount


def shift_term_chapters(novel_id: str, after_chapter: int, delta: int) -> int:
    """將指定章節之後的術語章節標記平移（用於刪章後的索引對齊）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if "source_chapter" not in _term_columns(conn):
        return 0
    cursor.execute(
        "UPDATE story_terms SET source_chapter = source_chapter + ? WHERE novel_id = ? AND source_chapter > ?",
        (int(delta), novel_id, int(after_chapter)),
    )
    n = cursor.rowcount
    cursor.execute(
        "UPDATE story_terms SET updated_chapter = updated_chapter + ? WHERE novel_id = ? AND updated_chapter > ?",
        (int(delta), novel_id, int(after_chapter)),
    )
    conn.commit()
    return n

def update_term(term_id: str, category: str, term: str, definition: str, notes: str = "") -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE story_terms
        SET category = ?, term = ?, definition = ?, notes = ?
        WHERE id = ?
    """, (category.strip(), term.strip(), definition.strip(), notes.strip(), term_id))
    conn.commit()
    return cursor.rowcount > 0

def delete_term(term_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM story_terms WHERE id = ?", (term_id,))
    conn.commit()
    return cursor.rowcount > 0

def search_terms(novel_id: str, query: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    pattern = f"%{query}%"
    cursor.execute("""
        SELECT *
        FROM story_terms
        WHERE novel_id = ? AND (term LIKE ? OR definition LIKE ? OR notes LIKE ?)
        ORDER BY term ASC
    """, (novel_id, pattern, pattern, pattern))
    rows = cursor.fetchall()
    return [_row_to_term(dict(r)) for r in rows]
