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
        try:
            cursor.execute(
                """
                INSERT INTO chat_memory (novel_id, role, content, thinking, message_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (novel_id, role, _to_traditional(content), _to_traditional(thinking) if thinking else None, message_type)
            )
        except Exception as e:
            print(f"[WARN] Failed to save chat message for novel {novel_id}: {e}")
            return
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
            except Exception as e:
                print(f"[WARN] Failed to prune pipeline chat_memory for novel {novel_id}: {e}")


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


def get_chapter_editor_review_status(novel_id: str, chapter_index: int) -> Optional[Dict[str, Any]]:
    """取得指定章節最近一次 Editor 精修驗收記錄（供管線接續判斷是否需重試 Editor）。

    回傳最新一筆 stage_name='editor' 且 chapter_index 相符的記錄；
    成功精修會留下 status='passed'，品質閘門放行會留下 'revise'，
    Editor 階段異常失敗會留下 'failed'，無記錄代表舊版章節或從未進過 Editor。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        """
        SELECT * FROM director_reviews
        WHERE novel_id = ? AND stage_name = 'editor' AND chapter_index = ?
        ORDER BY id DESC LIMIT 1
        """,
        (novel_id, int(chapter_index)),
    ).fetchone()
    return dict(row) if row else None


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