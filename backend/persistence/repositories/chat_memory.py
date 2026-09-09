"""Chat memory and director reviews repository module."""

import json
from typing import Any, Dict, List, Optional
from backend.persistence.connection import get_db_connection
from backend.persistence.repositories.chapters import _to_traditional


def get_chat_memory(novel_id: str, limit: int = 100, message_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch chronological chat memory records for a novel.
    Returns id, role, content, thinking, message_type, timestamp.
    If message_type is None or 'all', returns all messages (pipeline, chat, director).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if message_type and message_type != 'all':
        rows = cursor.execute(
            """
            SELECT id, role, content, thinking, message_type, timestamp
            FROM chat_memory
            WHERE novel_id = ? AND message_type = ?
            ORDER BY id DESC LIMIT ?
            """,
            (novel_id, message_type, limit)
        ).fetchall()
    else:
        rows = cursor.execute(
            """
            SELECT id, role, content, thinking, message_type, timestamp
            FROM chat_memory
            WHERE novel_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (novel_id, limit)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def save_chat_message(
    novel_id: str,
    role: str,
    content: str,
    thinking: Optional[str] = None,
    message_type: str = 'chat'
) -> None:
    """Save a message to the chat_memory table with sliding retention for pipeline logs."""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_memory (novel_id, role, content, thinking, message_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (novel_id, role, _to_traditional(content), _to_traditional(thinking) if thinking else None, message_type)
        )
        if message_type == 'pipeline':
            # Sliding retention: keep latest 300 pipeline messages per novel
            try:
                cursor.execute(
                    """
                    DELETE FROM chat_memory
                    WHERE novel_id = ?
                      AND message_type = 'pipeline'
                      AND id NOT IN (
                          SELECT id FROM chat_memory
                          WHERE novel_id = ? AND message_type = 'pipeline'
                          ORDER BY id DESC LIMIT 300
                      )
                    """,
                    (novel_id, novel_id)
                )
            except Exception:
                pass


def delete_chat_message(novel_id: str, message_id: int) -> bool:
    """Delete a single chat_memory record by ID for a specific novel."""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        res = cursor.execute("DELETE FROM chat_memory WHERE novel_id = ? AND id = ?", (novel_id, message_id))
        return res.rowcount > 0


def clear_chat_memory(novel_id: str, message_type: Optional[str] = None) -> int:
    """Clear chat_memory records for a specific novel, optionally filtered by message_type."""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        if message_type and message_type != 'all':
            res = cursor.execute("DELETE FROM chat_memory WHERE novel_id = ? AND message_type = ?", (novel_id, message_type))
        else:
            res = cursor.execute("DELETE FROM chat_memory WHERE novel_id = ?", (novel_id,))
        return res.rowcount


def save_director_review_status(
    novel_id: str,
    stage_name: str,
    status: str,
    block_name: Optional[str] = None,
    volume_index: Optional[int] = None,
    chapter_index: Optional[int] = None,
    reason: str = "",
    decision_json: Any = None,
) -> None:
    """Append a Director review status record without mutating content tables."""
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        if decision_json is not None and not isinstance(decision_json, str):
            try:
                decision_json = json.dumps(decision_json, ensure_ascii=False, indent=2)
            except Exception:
                decision_json = str(decision_json)
        cursor.execute(
            """
            INSERT INTO director_reviews (
                novel_id, stage_name, status, block_name, volume_index, chapter_index, reason, decision_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (novel_id, stage_name, status, block_name, volume_index, chapter_index, reason, decision_json),
        )


def get_latest_director_review_status(novel_id: str, stage_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the latest Director review status record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if stage_name:
        row = cursor.execute(
            """
            SELECT * FROM director_reviews
            WHERE novel_id = ? AND stage_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (novel_id, stage_name),
        ).fetchone()
    else:
        row = cursor.execute(
            """
            SELECT * FROM director_reviews
            WHERE novel_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (novel_id,),
        ).fetchone()
    return dict(row) if row else None