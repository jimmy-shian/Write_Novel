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
    chapter_index: int = 1
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, attributes_json FROM temporal_entities WHERE novel_id = ? AND name = ?", (novel_id, name))
    row = cursor.fetchone()
    attr_str = json.dumps(attributes or {}, ensure_ascii=False)
    
    if row:
        ent_id = row["id"]
        cursor.execute("""
            UPDATE temporal_entities
            SET entity_type = ?, summary = ?, attributes_json = ?, updated_chapter = ?
            WHERE id = ?
        """, (entity_type, summary, attr_str, chapter_index, ent_id))
    else:
        ent_id = f"ent_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO temporal_entities (id, novel_id, name, entity_type, summary, attributes_json, created_chapter, updated_chapter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (ent_id, novel_id, name, entity_type, summary, attr_str, chapter_index, chapter_index))
    conn.commit()
    return {
        "id": ent_id,
        "novel_id": novel_id,
        "name": name,
        "entity_type": entity_type,
        "summary": summary,
        "attributes": attributes or {},
        "updated_chapter": chapter_index
    }

def get_entities(novel_id: str, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if entity_type:
        cursor.execute("""
            SELECT id, novel_id, name, entity_type, summary, attributes_json, created_chapter, updated_chapter
            FROM temporal_entities WHERE novel_id = ? AND entity_type = ?
            ORDER BY name ASC
        """, (novel_id, entity_type))
    else:
        cursor.execute("""
            SELECT id, novel_id, name, entity_type, summary, attributes_json, created_chapter, updated_chapter
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
        except Exception:
            pass
        result.append({
            "id": r["id"],
            "novel_id": r["novel_id"],
            "name": r["name"],
            "entity_type": r["entity_type"],
            "summary": r["summary"],
            "attributes": attrs,
            "created_chapter": r["created_chapter"],
            "updated_chapter": r["updated_chapter"]
        })
    return result

def add_fact(
    novel_id: str,
    fact_statement: str,
    valid_from_chapter: int,
    source_entity_id: Optional[str] = None,
    target_entity_id: Optional[str] = None,
    relation_type: Optional[str] = None,
    episode_id: Optional[str] = None
) -> Dict[str, Any]:
    fact_id = f"fact_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    cursor = conn.cursor()
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
    cursor.execute("DELETE FROM temporal_entities WHERE novel_id = ?", (novel_id,))
    entities_deleted = cursor.rowcount
    conn.commit()
    return {
        "facts_deleted": facts_deleted,
        "episodes_deleted": episodes_deleted,
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
