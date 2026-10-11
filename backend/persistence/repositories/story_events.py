# -*- coding: utf-8 -*-
"""Planned and observed story-event records."""

import hashlib
import json
from typing import Any, Dict, List, Optional

from backend.persistence.connection import get_db_connection


def _event_id(novel_id: str, chapter_index: int, event: Dict[str, Any], status: str) -> str:
    stable = json.dumps({
        "novel_id": novel_id,
        "chapter_index": int(chapter_index),
        "status": status,
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type") or event.get("type"),
        "character": event.get("character") or event.get("character_name") or event.get("name"),
        "description": event.get("description") or event.get("summary") or event.get("content"),
    }, ensure_ascii=False, sort_keys=True)
    return "sev_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def upsert_story_event(
    novel_id: str,
    chapter_index: int,
    event: Dict[str, Any],
    status: str = "planned",
    source: str = "outline",
    conn=None,
) -> Dict[str, Any]:
    status = str(status or "planned").lower()
    if status not in {"planned", "occurred", "observed", "cancelled"}:
        raise ValueError("invalid story event status")
    event_id = _event_id(novel_id, chapter_index, event, status)
    event_type = str(event.get("event_type") or event.get("type") or "event").strip()
    character = str(event.get("character") or event.get("character_name") or event.get("name") or "").strip()
    description = str(event.get("description") or event.get("summary") or event.get("content") or "").strip()
    owns_connection = conn is None
    conn = conn or get_db_connection()
    conn.execute(
        """INSERT OR REPLACE INTO story_events
        (id, novel_id, chapter_index, status, event_type, character_name, description, payload_json, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, novel_id, int(chapter_index), status, event_type, character, description,
         json.dumps(event, ensure_ascii=False), source),
    )
    if owns_connection:
        conn.commit()
    return {"id": event_id, "novel_id": novel_id, "chapter_index": int(chapter_index), "status": status,
            "event_type": event_type, "character_name": character, "description": description, "payload": event, "source": source}


def get_story_events(novel_id: str, chapter_index: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM story_events WHERE novel_id = ?"
    params: List[Any] = [novel_id]
    if chapter_index is not None:
        query += " AND chapter_index = ?"
        params.append(int(chapter_index))
    if status:
        query += " AND status = ?"
        params.append(str(status).lower())
    query += " ORDER BY chapter_index ASC, id ASC"
    rows = get_db_connection().execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except Exception:
            item["payload"] = {}
        result.append(item)
    return result


def sync_planned_story_events(novel_id: str, chapters: List[Dict[str, Any]], conn=None) -> int:
    """Synchronize the outline event schedule without touching occurred history.

    Planned rows are a projection of the current outline.  Stale planned rows
    must be removed when an outline patch replaces an event; occurred/observed
    rows remain immutable history.  ``conn`` lets outline writes and schedule
    writes share one transaction.
    """
    owns_connection = conn is None
    conn = conn or get_db_connection()
    desired_by_chapter: Dict[int, set] = {}
    events_to_write = []
    keys = ("planned_events", "story_events", "life_events", "character_events", "events")
    for chapter in chapters or []:
        index = int(chapter.get("chapter_index") or chapter.get("chapter") or 0)
        if not index:
            continue
        desired_by_chapter.setdefault(index, set())
        for key in keys:
            events = chapter.get(key)
            if not isinstance(events, list):
                continue
            for event in events:
                if isinstance(event, dict) and (event.get("event_type") or event.get("type")):
                    event_id = _event_id(novel_id, index, event, "planned")
                    if event_id in desired_by_chapter[index]:
                        continue
                    desired_by_chapter[index].add(event_id)
                    events_to_write.append((index, event, event_id))

    count = 0
    with conn:
        for index, desired_ids in desired_by_chapter.items():
            placeholders = ",".join("?" for _ in desired_ids)
            params: List[Any] = [novel_id, int(index)]
            if placeholders:
                params.extend(sorted(desired_ids))
                conn.execute(
                    f"DELETE FROM story_events WHERE novel_id = ? AND chapter_index = ? "
                    f"AND status = 'planned' AND id NOT IN ({placeholders})",
                    params,
                )
            else:
                conn.execute(
                    "DELETE FROM story_events WHERE novel_id = ? AND chapter_index = ? AND status = 'planned'",
                    params,
                )
        for index, event, _event_id_value in events_to_write:
            upsert_story_event(
                novel_id, index, event, status="planned", source="outline", conn=conn
            )
            count += 1
    if owns_connection:
        conn.commit()
    return count
