# -*- coding: utf-8 -*-
"""
Draft Proposals Repository.
Stores AI draft suggestions and review checklists for human review before final application.
"""
import uuid
import json
import sqlite3
from typing import Dict, Any, List, Optional
from backend.persistence.connection import ConnectionProvider, get_db_connection, transaction

def create_proposal(
    novel_id: str,
    chapter_index: int,
    proposed_text: str,
    original_text: str = "",
    review_comments: Optional[List[Dict[str, Any]]] = None,
    *,
    connection: Optional[sqlite3.Connection] = None,
    connection_provider: Optional[ConnectionProvider] = None,
) -> Dict[str, Any]:
    from backend.common.refusal_filter import assert_not_refusal
    if proposed_text and str(proposed_text).strip():
        assert_not_refusal(str(proposed_text), f"Proposal Chapter {chapter_index}")

    proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
    comments_str = json.dumps(review_comments or [], ensure_ascii=False)
    with transaction(connection=connection, provider=connection_provider) as conn:
        conn.execute("""
            INSERT INTO draft_proposals (id, novel_id, chapter_index, original_text, proposed_text, review_comments_json, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (proposal_id, novel_id, chapter_index, original_text, proposed_text, comments_str))
    return {
        "id": proposal_id,
        "novel_id": novel_id,
        "chapter_index": chapter_index,
        "original_text": original_text,
        "proposed_text": proposed_text,
        "review_comments": review_comments or [],
        "status": "pending"
    }

def get_proposals(novel_id: str, chapter_index: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT id, novel_id, chapter_index, original_text, proposed_text, review_comments_json, status, created_at FROM draft_proposals WHERE novel_id = ?"
    params: List[Any] = [novel_id]
    if chapter_index is not None:
        query += " AND chapter_index = ?"
        params.append(chapter_index)
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        comments = []
        try:
            if r["review_comments_json"]:
                comments = json.loads(r["review_comments_json"])
        except Exception as e:
            print(f"[WARN] Failed to parse review comments for proposal {r['id']}: {e}")
        result.append({
            "id": r["id"],
            "novel_id": r["novel_id"],
            "chapter_index": r["chapter_index"],
            "original_text": r["original_text"] or "",
            "proposed_text": r["proposed_text"],
            "review_comments": comments,
            "status": r["status"],
            "created_at": str(r["created_at"])
        })
    return result

def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, novel_id, chapter_index, original_text, proposed_text, review_comments_json, status, created_at
        FROM draft_proposals WHERE id = ?
    """, (proposal_id,))
    r = cursor.fetchone()
    if not r:
        return None
    comments = []
    try:
        if r["review_comments_json"]:
            comments = json.loads(r["review_comments_json"])
    except Exception as e:
        print(f"[WARN] Failed to parse review comments for proposal {proposal_id}: {e}")
    return {
        "id": r["id"],
        "novel_id": r["novel_id"],
        "chapter_index": r["chapter_index"],
        "original_text": r["original_text"] or "",
        "proposed_text": r["proposed_text"],
        "review_comments": comments,
        "status": r["status"],
        "created_at": str(r["created_at"])
    }

def update_proposal_status(
    proposal_id: str,
    status: str,
    *,
    connection: Optional[sqlite3.Connection] = None,
    connection_provider: Optional[ConnectionProvider] = None,
) -> bool:
    with transaction(connection=connection, provider=connection_provider) as conn:
        cursor = conn.execute("UPDATE draft_proposals SET status = ? WHERE id = ?", (status, proposal_id))
        updated = cursor.rowcount > 0
    return updated

def update_proposal_content(
    proposal_id: str,
    proposed_text: str,
    review_comments: Optional[List[Dict[str, Any]]] = None,
    *,
    connection: Optional[sqlite3.Connection] = None,
    connection_provider: Optional[ConnectionProvider] = None,
) -> bool:
    with transaction(connection=connection, provider=connection_provider) as conn:
        if review_comments is not None:
            comments_str = json.dumps(review_comments, ensure_ascii=False)
            cursor = conn.execute("""
                UPDATE draft_proposals SET proposed_text = ?, review_comments_json = ? WHERE id = ?
            """, (proposed_text, comments_str, proposal_id))
        else:
            cursor = conn.execute("UPDATE draft_proposals SET proposed_text = ? WHERE id = ?", (proposed_text, proposal_id))
        updated = cursor.rowcount > 0
    return updated

def delete_proposal(
    proposal_id: str,
    *,
    connection: Optional[sqlite3.Connection] = None,
    connection_provider: Optional[ConnectionProvider] = None,
) -> bool:
    with transaction(connection=connection, provider=connection_provider) as conn:
        cursor = conn.execute("DELETE FROM draft_proposals WHERE id = ?", (proposal_id,))
        deleted = cursor.rowcount > 0
    return deleted
