# -*- coding: utf-8 -*-
"""
Graphiti-inspired Temporal Knowledge Graph Repository.
Handles Episodes, Entities, and Facts with temporal validity windows (valid_from / invalid_from).
"""
import uuid
import json
from typing import Dict, Any, List, Optional
from backend.persistence.connection import get_db_connection

def save_episode(novel_id: str, chapter_index: int, summary: str = "", content_hash: str = "") -> Dict[str, Any]:
    existing = get_db_connection().execute(
        "SELECT id, novel_id, chapter_index, content_hash, summary "
        "FROM temporal_episodes WHERE novel_id = ? AND chapter_index = ? AND content_hash = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (novel_id, int(chapter_index), content_hash),
    ).fetchone()
    if existing:
        return {
            "id": existing["id"],
            "novel_id": existing["novel_id"],
            "chapter_index": existing["chapter_index"],
            "content_hash": existing["content_hash"],
            "summary": existing["summary"],
        }
    episode_id = f"ep_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO temporal_episodes (id, novel_id, chapter_index, content_hash, summary)
        VALUES (?, ?, ?, ?, ?)
    """, (episode_id, novel_id, chapter_index, content_hash, summary))
    conn.commit()
    return {
        "id": episode_id,
        "novel_id": novel_id,
        "chapter_index": chapter_index,
        "content_hash": content_hash,
        "summary": summary
    }

def get_episodes(novel_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, novel_id, chapter_index, content_hash, summary, created_at
        FROM temporal_episodes
        WHERE novel_id = ?
        ORDER BY chapter_index ASC
    """, (novel_id,))
    rows = cursor.fetchall()
    return [{
        "id": r["id"],
        "novel_id": r["novel_id"],
        "chapter_index": r["chapter_index"],
        "content_hash": r["content_hash"],
        "summary": r["summary"],
        "created_at": str(r["created_at"])
    } for r in rows]

def upsert_entity(
    novel_id: str,
    name: str,
    entity_type: str,
    summary: str = "",
    attributes: Optional[Dict[str, Any]] = None,
    chapter_index: int = 1,
    life_status: Optional[str] = None,
    source: str = "authoritative",
    conn=None,
) -> Dict[str, Any]:
    owns_connection = conn is None
    if owns_connection:
        conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, life_status, life_status_source, life_status_chapter, attributes_json "
        "FROM temporal_entities WHERE novel_id = ? AND name = ?",
        (novel_id, name),
    )
    row = cursor.fetchone()
    attr_str = json.dumps(attributes or {}, ensure_ascii=False)
    # Graph extraction is observational. It may create an unknown entity, but it
    # cannot rewrite a planned or already-established life state.
    observational = str(source or "").lower() in {"extractor", "llm", "graphiti"}
    normalized_status = None if observational else (life_status if life_status in {"alive", "dead", "unknown"} else None)
    if row and normalized_status is None:
        normalized_status = row["life_status"]
    status_source = row["life_status_source"] if row else "unknown"
    status_chapter = row["life_status_chapter"] if row else None
    if not observational and life_status in {"alive", "dead", "unknown"}:
        status_source = str(source or "authoritative")
        status_chapter = int(chapter_index or 0)
    
    if row:
        ent_id = row["id"]
        # Observation refreshes descriptions, but never advances the canonical
        # fate timestamp.  Otherwise a dead character observed in chapter 300
        # would look as if it first became dead in chapter 300.
        cursor.execute("""
            UPDATE temporal_entities
            SET entity_type = ?, life_status = COALESCE(?, life_status),
                life_status_source = COALESCE(?, life_status_source),
                life_status_chapter = COALESCE(?, life_status_chapter),
                summary = ?, attributes_json = ?, updated_chapter = ?
            WHERE id = ?
        """, (entity_type, normalized_status, status_source, status_chapter,
               summary, attr_str, chapter_index, ent_id))
    else:
        ent_id = f"ent_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO temporal_entities
            (id, novel_id, name, entity_type, life_status, life_status_source,
             life_status_chapter, summary, attributes_json, created_chapter, updated_chapter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ent_id, novel_id, name, entity_type, normalized_status, status_source,
               status_chapter, summary, attr_str, chapter_index, chapter_index))
    if owns_connection:
        conn.commit()
    return {
        "id": ent_id,
        "novel_id": novel_id,
        "name": name,
        "entity_type": entity_type,
        "life_status": normalized_status,
        "life_status_source": status_source,
        "life_status_chapter": status_chapter,
        "summary": summary,
        "attributes": attributes or {},
        "updated_chapter": chapter_index
    }

def get_entities(novel_id: str, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if entity_type:
        cursor.execute("""
            SELECT id, novel_id, name, entity_type, life_status, life_status_source,
                   life_status_chapter, summary, attributes_json, created_chapter, updated_chapter
            FROM temporal_entities WHERE novel_id = ? AND entity_type = ?
            ORDER BY name ASC
        """, (novel_id, entity_type))
    else:
        cursor.execute("""
            SELECT id, novel_id, name, entity_type, life_status, life_status_source,
                   life_status_chapter, summary, attributes_json, created_chapter, updated_chapter
            FROM temporal_entities WHERE novel_id = ?
            ORDER BY entity_type ASC, name ASC
        """, (novel_id,))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        attrs = {}
        try:
            if r["attributes_json"]:
                attrs = json.loads(r["attributes_json"])
        except Exception as e:
            print(f"[WARN] Failed to parse temporal entity attributes for {r['name']}: {e}")
        result.append({
            "id": r["id"],
            "novel_id": r["novel_id"],
            "name": r["name"],
            "entity_type": r["entity_type"],
            "life_status": r["life_status"],
        "life_status_source": r["life_status_source"],
        "life_status_chapter": r["life_status_chapter"],
            "summary": r["summary"],
            "attributes": attrs,
            "created_chapter": r["created_chapter"],
            "updated_chapter": r["updated_chapter"]
        })
    return result


def apply_authorized_life_transition(
    novel_id: str,
    name: str,
    life_status: str,
    chapter_index: int,
    event_type: str,
    reason: str = "",
    conn=None,
) -> Dict[str, Any]:
    """Apply a planned death/revival event explicitly.

    This is the only normal mutation path that can change an established life
    state. The caller must supply the matching plot event type, so Graphiti
    extraction cannot accidentally create a resurrection.
    """
    desired = str(life_status or "").lower().strip()
    kind = str(event_type or "").lower().strip()
    if desired not in {"alive", "dead"}:
        raise ValueError("life_status must be alive or dead")
    if desired == "dead" and kind not in {"death", "dead", "kill"}:
        raise ValueError("death transition requires a death event")
    if desired == "alive" and kind not in {"resurrection", "revival", "revive"}:
        raise ValueError("alive transition requires a resurrection event")

    owns_connection = conn is None
    conn = conn or get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT id, entity_type, attributes_json, life_status FROM temporal_entities WHERE novel_id = ? AND name = ?",
        (novel_id, name),
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown entity: {name}")
    current = row["life_status"]
    if current == desired:
        return {"name": name, "life_status": desired, "chapter_index": chapter_index, "unchanged": True}
    if current == "dead" and desired == "alive" and kind not in {"resurrection", "revival", "revive"}:
        raise ValueError("dead entity requires an explicit resurrection event")
    attrs = {}
    try:
        attrs = json.loads(row["attributes_json"] or "{}")
    except Exception:
        attrs = {}
    history = attrs.get("life_events") if isinstance(attrs, dict) else None
    if not isinstance(history, list):
        history = []
    history.append({"event_type": kind, "chapter_index": int(chapter_index), "reason": reason})
    attrs["life_events"] = history
    cursor.execute(
        "UPDATE temporal_entities SET life_status = ?, life_status_source = ?, "
        "life_status_chapter = ?, attributes_json = ?, updated_chapter = ? WHERE id = ?",
        (desired, "story_event", int(chapter_index), json.dumps(attrs, ensure_ascii=False),
         int(chapter_index), row["id"]),
    )
    if owns_connection:
        conn.commit()
    return {"name": name, "life_status": desired, "chapter_index": chapter_index, "event_type": kind}

def add_fact(
    novel_id: str,
    fact_statement: str,
    valid_from_chapter: int,
    source_entity_id: Optional[str] = None,
    target_entity_id: Optional[str] = None,
    relation_type: Optional[str] = None,
    episode_id: Optional[str] = None
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    existing = cursor.execute(
        "SELECT * FROM temporal_facts WHERE novel_id = ? AND valid_from_chapter = ? "
        "AND fact_statement = ? AND COALESCE(source_entity_id, '') = COALESCE(?, '') "
        "AND COALESCE(target_entity_id, '') = COALESCE(?, '') "
        "AND COALESCE(relation_type, '') = COALESCE(?, '') "
        "AND COALESCE(episode_id, '') = COALESCE(?, '') LIMIT 1",
        (novel_id, int(valid_from_chapter), fact_statement, source_entity_id,
         target_entity_id, relation_type, episode_id),
    ).fetchone()
    if existing:
        return {
            "id": existing["id"],
            "novel_id": existing["novel_id"],
            "fact_statement": existing["fact_statement"],
            "valid_from_chapter": existing["valid_from_chapter"],
            "invalid_from_chapter": existing["invalid_from_chapter"],
            "is_active": bool(existing["is_active"]),
            "source_entity_id": existing["source_entity_id"],
            "target_entity_id": existing["target_entity_id"],
            "relation_type": existing["relation_type"],
            "episode_id": existing["episode_id"],
            "deduplicated": True,
        }
    fact_id = f"fact_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO temporal_facts (
            id, novel_id, source_entity_id, target_entity_id, relation_type,
            fact_statement, valid_from_chapter, invalid_from_chapter, is_active, superseded_by, episode_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 1, NULL, ?)
    """, (fact_id, novel_id, source_entity_id, target_entity_id, relation_type, fact_statement, valid_from_chapter, episode_id))
    conn.commit()
    return {
        "id": fact_id,
        "novel_id": novel_id,
        "fact_statement": fact_statement,
        "valid_from_chapter": valid_from_chapter,
        "invalid_from_chapter": None,
        "is_active": True,
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "relation_type": relation_type,
        "episode_id": episode_id
    }


def record_temporal_fact(
    novel_id: str,
    statement: str,
    valid_from: int = 1,
    invalid_from: Optional[int] = None,
    source_entity_id: Optional[str] = None,
    target_entity_id: Optional[str] = None,
    relation_type: Optional[str] = None,
    episode_id: Optional[str] = None,
) -> Dict[str, Any]:
    """快捷寫入時序事實記錄 (相容測試與外部介面)"""
    fact_id = f"fact_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    is_active = 0 if invalid_from is not None else 1
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO temporal_facts (
            id, novel_id, source_entity_id, target_entity_id, relation_type,
            fact_statement, valid_from_chapter, invalid_from_chapter, is_active, superseded_by, episode_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
    """, (fact_id, novel_id, source_entity_id, target_entity_id, relation_type, statement, valid_from, invalid_from, is_active, episode_id))
    conn.commit()
    return {
        "id": fact_id,
        "novel_id": novel_id,
        "fact_statement": statement,
        "valid_from_chapter": valid_from,
        "invalid_from_chapter": invalid_from,
        "is_active": bool(is_active)
    }

def invalidate_fact(fact_id: str, invalid_from_chapter: int, superseded_by: Optional[str] = None) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE temporal_facts
        SET invalid_from_chapter = ?, is_active = 0, superseded_by = ?
        WHERE id = ?
    """, (invalid_from_chapter, superseded_by, fact_id))
    conn.commit()
    return cursor.rowcount > 0

def get_facts_at_chapter(novel_id: str, chapter_index: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.novel_id, f.source_entity_id, f.target_entity_id, f.relation_type,
               f.fact_statement, f.valid_from_chapter, f.invalid_from_chapter, f.is_active,
               f.superseded_by, f.episode_id,
               e1.name as source_name, e2.name as target_name
        FROM temporal_facts f
        LEFT JOIN temporal_entities e1 ON f.source_entity_id = e1.id
        LEFT JOIN temporal_entities e2 ON f.target_entity_id = e2.id
        WHERE f.novel_id = ?
          AND f.valid_from_chapter <= ?
          AND (f.invalid_from_chapter IS NULL OR f.invalid_from_chapter > ?)
        ORDER BY f.valid_from_chapter ASC
    """, (novel_id, chapter_index, chapter_index))
    rows = cursor.fetchall()
    return [{
        "id": r["id"],
        "novel_id": r["novel_id"],
        "source_entity_id": r["source_entity_id"],
        "target_entity_id": r["target_entity_id"],
        "source_name": r["source_name"] or "",
        "target_name": r["target_name"] or "",
        "relation_type": r["relation_type"] or "",
        "fact_statement": r["fact_statement"],
        "valid_from_chapter": r["valid_from_chapter"],
        "invalid_from_chapter": r["invalid_from_chapter"],
        "is_active": bool(r["is_active"]),
        "superseded_by": r["superseded_by"]
    } for r in rows]

def get_all_facts(novel_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.novel_id, f.source_entity_id, f.target_entity_id, f.relation_type,
               f.fact_statement, f.valid_from_chapter, f.invalid_from_chapter, f.is_active,
               f.superseded_by, f.episode_id,
               e1.name as source_name, e2.name as target_name
        FROM temporal_facts f
        LEFT JOIN temporal_entities e1 ON f.source_entity_id = e1.id
        LEFT JOIN temporal_entities e2 ON f.target_entity_id = e2.id
        WHERE f.novel_id = ?
        ORDER BY f.valid_from_chapter ASC, f.id ASC
    """, (novel_id,))
    rows = cursor.fetchall()
    return [{
        "id": r["id"],
        "novel_id": r["novel_id"],
        "source_entity_id": r["source_entity_id"],
        "target_entity_id": r["target_entity_id"],
        "source_name": r["source_name"] or "",
        "target_name": r["target_name"] or "",
        "relation_type": r["relation_type"] or "",
        "fact_statement": r["fact_statement"],
        "valid_from_chapter": r["valid_from_chapter"],
        "invalid_from_chapter": r["invalid_from_chapter"],
        "is_active": bool(r["is_active"]),
        "superseded_by": r["superseded_by"]
    } for r in rows]

def delete_chapter_slice(novel_id: str, chapter_index: int) -> Dict[str, int]:
    """刪除指定章節衍生的時序圖譜物件（單章正文清除時的連動清理）。

    - 刪除 valid_from_chapter == 該章的事實命題
    - 刪除該章的 episodes（其餘掛載事實經由 FK CASCADE 一併清除）
    - 刪除僅在該章出現過的實體（created_chapter == updated_chapter == 該章）
    - 將「於該章被作廢」的事實回滾為有效（作廢依據已不存在）
    回傳各項刪除/回滾筆數。
    """
    chapter_index = int(chapter_index)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM temporal_facts WHERE novel_id = ? AND valid_from_chapter = ?",
        (novel_id, chapter_index),
    )
    facts_deleted = cursor.rowcount
    cursor.execute(
        "DELETE FROM temporal_episodes WHERE novel_id = ? AND chapter_index = ?",
        (novel_id, chapter_index),
    )
    episodes_deleted = cursor.rowcount
    cursor.execute(
        "DELETE FROM story_events WHERE novel_id = ? AND chapter_index = ? "
        "AND status IN ('occurred', 'observed')",
        (novel_id, chapter_index),
    )
    events_deleted = cursor.rowcount
    cursor.execute(
        "DELETE FROM temporal_entities WHERE novel_id = ? AND created_chapter = ? AND updated_chapter = ?",
        (novel_id, chapter_index, chapter_index),
    )
    entities_deleted = cursor.rowcount
    cursor.execute("""
        UPDATE temporal_facts
        SET invalid_from_chapter = NULL, is_active = 1, superseded_by = NULL
        WHERE novel_id = ? AND invalid_from_chapter = ?
    """, (novel_id, chapter_index))
    facts_reactivated = cursor.rowcount
    conn.commit()
    return {
        "facts_deleted": facts_deleted,
        "episodes_deleted": episodes_deleted,
        "events_deleted": events_deleted,
        "entities_deleted": entities_deleted,
        "facts_reactivated": facts_reactivated,
    }


def clear_novel_graph(novel_id: str) -> Dict[str, int]:
    """清空該小說全部時序圖譜（整批正文清除時使用）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM temporal_facts WHERE novel_id = ?", (novel_id,))
    facts_deleted = cursor.rowcount
    cursor.execute("DELETE FROM temporal_episodes WHERE novel_id = ?", (novel_id,))
    episodes_deleted = cursor.rowcount
    cursor.execute(
        "DELETE FROM story_events WHERE novel_id = ? AND status IN ('occurred', 'observed')",
        (novel_id,),
    )
    events_deleted = cursor.rowcount
    cursor.execute("DELETE FROM temporal_entities WHERE novel_id = ?", (novel_id,))
    entities_deleted = cursor.rowcount
    conn.commit()
    return {
        "facts_deleted": facts_deleted,
        "episodes_deleted": episodes_deleted,
        "events_deleted": events_deleted,
        "entities_deleted": entities_deleted,
    }


def shift_graph_chapters(novel_id: str, after_chapter: int, delta: int) -> Dict[str, int]:
    """將指定章節之後的圖譜章節標記平移（用於刪章後的索引對齊）。"""
    after_chapter = int(after_chapter)
    delta = int(delta)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE temporal_facts SET valid_from_chapter = valid_from_chapter + ? WHERE novel_id = ? AND valid_from_chapter > ?",
        (delta, novel_id, after_chapter),
    )
    valid_shifted = cursor.rowcount
    cursor.execute(
        "UPDATE temporal_facts SET invalid_from_chapter = invalid_from_chapter + ? WHERE novel_id = ? AND invalid_from_chapter IS NOT NULL AND invalid_from_chapter > ?",
        (delta, novel_id, after_chapter),
    )
    invalid_shifted = cursor.rowcount
    cursor.execute(
        "UPDATE temporal_episodes SET chapter_index = chapter_index + ? WHERE novel_id = ? AND chapter_index > ?",
        (delta, novel_id, after_chapter),
    )
    episodes_shifted = cursor.rowcount
    cursor.execute(
        "UPDATE story_events SET chapter_index = chapter_index + ? WHERE novel_id = ? AND chapter_index > ?",
        (delta, novel_id, after_chapter),
    )
    events_shifted = cursor.rowcount
    cursor.execute(
        "UPDATE temporal_entities SET life_status_chapter = life_status_chapter + ? "
        "WHERE novel_id = ? AND life_status_chapter IS NOT NULL AND life_status_chapter > ?",
        (delta, novel_id, after_chapter),
    )
    cursor.execute(
        "UPDATE temporal_entities SET created_chapter = created_chapter + ? WHERE novel_id = ? AND created_chapter > ?",
        (delta, novel_id, after_chapter),
    )
    created_shifted = cursor.rowcount
    cursor.execute(
        "UPDATE temporal_entities SET updated_chapter = updated_chapter + ? WHERE novel_id = ? AND updated_chapter > ?",
        (delta, novel_id, after_chapter),
    )
    updated_shifted = cursor.rowcount
    conn.commit()
    return {
        "facts_valid_shifted": valid_shifted,
        "facts_invalid_shifted": invalid_shifted,
        "episodes_shifted": episodes_shifted,
        "events_shifted": events_shifted,
        "entities_created_shifted": created_shifted,
        "entities_updated_shifted": updated_shifted,
    }


def delete_entity(entity_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM temporal_entities WHERE id = ?", (entity_id,))
    conn.commit()
    return cursor.rowcount > 0

def delete_fact(fact_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM temporal_facts WHERE id = ?", (fact_id,))
    conn.commit()
    return cursor.rowcount > 0
