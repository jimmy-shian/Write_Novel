# -*- coding: utf-8 -*-
import json

from backend.persistence.connection import _convert_obj_to_traditional, get_db_connection


def _decode_summary(row):
    data = dict(row)
    try:
        data["summary_json"] = json.loads(data.get("summary_json") or "{}")
    except Exception:
        data["summary_json"] = {}
    return data


def save_chapter_memory(novel_id, chapter_index, summary_json, source_version=None):
    payload = _convert_obj_to_traditional(summary_json)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO chapter_memory (novel_id, chapter_index, summary_json, source_version)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(novel_id, chapter_index) DO UPDATE SET
            summary_json = excluded.summary_json,
            source_version = excluded.source_version,
            updated_at = CURRENT_TIMESTAMP
        """,
        (novel_id, int(chapter_index), json.dumps(payload, ensure_ascii=False), source_version),
    )
    conn.commit()
    conn.close()
    return True


def get_chapter_memory(novel_id, chapter_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM chapter_memory WHERE novel_id = ? AND chapter_index = ?",
        (novel_id, int(chapter_index)),
    ).fetchone()
    conn.close()
    return _decode_summary(row) if row else None


def get_chapter_memories(novel_id, start_chapter=None, end_chapter=None, limit=None):
    clauses = ["novel_id = ?"]
    params = [novel_id]
    if start_chapter is not None:
        clauses.append("chapter_index >= ?")
        params.append(int(start_chapter))
    if end_chapter is not None:
        clauses.append("chapter_index <= ?")
        params.append(int(end_chapter))
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        f"""
        SELECT * FROM chapter_memory
        WHERE {' AND '.join(clauses)}
        ORDER BY chapter_index ASC
        {limit_sql}
        """,
        params,
    ).fetchall()
    conn.close()
    return [_decode_summary(row) for row in rows]


def delete_chapter_memories_in_range(novel_id, start_chapter, end_chapter):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM chapter_memory
        WHERE novel_id = ? AND chapter_index >= ? AND chapter_index <= ?
        """,
        (novel_id, int(start_chapter), int(end_chapter)),
    )
    conn.commit()
    conn.close()


def shift_chapter_memories(novel_id, start_chapter, delta):
    delta = int(delta)
    if delta == 0:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE chapter_memory
        SET chapter_index = -chapter_index
        WHERE novel_id = ? AND chapter_index >= ?
        """,
        (novel_id, int(start_chapter)),
    )
    cursor.execute(
        """
        UPDATE chapter_memory
        SET chapter_index = (-chapter_index) + ?
        WHERE novel_id = ? AND chapter_index < 0
        """,
        (delta, novel_id),
    )
    cursor.execute("DELETE FROM arc_summaries WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()


def save_arc_summary(novel_id, arc_start, arc_end, summary_json):
    payload = _convert_obj_to_traditional(summary_json)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO arc_summaries (novel_id, arc_start, arc_end, summary_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(novel_id, arc_start, arc_end) DO UPDATE SET
            summary_json = excluded.summary_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (novel_id, int(arc_start), int(arc_end), json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return True


def get_arc_summary(novel_id, chapter_index=None, arc_start=None, arc_end=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if arc_start is not None and arc_end is not None:
        row = cursor.execute(
            """
            SELECT * FROM arc_summaries
            WHERE novel_id = ? AND arc_start = ? AND arc_end = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (novel_id, int(arc_start), int(arc_end)),
        ).fetchone()
    elif chapter_index is not None:
        row = cursor.execute(
            """
            SELECT * FROM arc_summaries
            WHERE novel_id = ? AND arc_start <= ? AND arc_end >= ?
            ORDER BY arc_end DESC LIMIT 1
            """,
            (novel_id, int(chapter_index), int(chapter_index)),
        ).fetchone()
    else:
        row = cursor.execute(
            """
            SELECT * FROM arc_summaries
            WHERE novel_id = ?
            ORDER BY arc_end DESC LIMIT 1
            """,
            (novel_id,),
        ).fetchone()
    conn.close()
    return _decode_summary(row) if row else None


def get_arc_summaries(novel_id, end_chapter=None):
    clauses = ["novel_id = ?"]
    params = [novel_id]
    if end_chapter is not None:
        clauses.append("arc_end <= ?")
        params.append(int(end_chapter))
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        f"""
        SELECT * FROM arc_summaries
        WHERE {' AND '.join(clauses)}
        ORDER BY arc_start ASC
        """,
        params,
    ).fetchall()
    conn.close()
    return [_decode_summary(row) for row in rows]


def clear_arc_summaries(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM arc_summaries WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()
