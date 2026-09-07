# -*- coding: utf-8 -*-
"""
Story Terms / Glossary Repository.
Tracks novel-specific terminology, proper nouns, and constraints.
"""
import uuid
from typing import Dict, Any, List, Optional
from backend.persistence.connection import get_db_connection

def create_term(novel_id: str, category: str, term: str, definition: str, notes: str = "") -> Dict[str, Any]:
    term_id = f"term_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    cursor = conn.cursor()
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
        "notes": notes.strip()
    }

def get_terms(novel_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute("""
            SELECT id, novel_id, category, term, definition, notes, created_at
            FROM story_terms WHERE novel_id = ? AND category = ?
            ORDER BY term ASC
        """, (novel_id, category))
    else:
        cursor.execute("""
            SELECT id, novel_id, category, term, definition, notes, created_at
            FROM story_terms WHERE novel_id = ?
            ORDER BY category ASC, term ASC
        """, (novel_id,))
    rows = cursor.fetchall()
    return [{
        "id": r["id"],
        "novel_id": r["novel_id"],
        "category": r["category"],
        "term": r["term"],
        "definition": r["definition"],
        "notes": r["notes"] or "",
        "created_at": str(r["created_at"])
    } for r in rows]

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
        SELECT id, novel_id, category, term, definition, notes
        FROM story_terms
        WHERE novel_id = ? AND (term LIKE ? OR definition LIKE ? OR notes LIKE ?)
        ORDER BY term ASC
    """, (novel_id, pattern, pattern, pattern))
    rows = cursor.fetchall()
    return [{
        "id": r["id"],
        "novel_id": r["novel_id"],
        "category": r["category"],
        "term": r["term"],
        "definition": r["definition"],
        "notes": r["notes"] or ""
    } for r in rows]
