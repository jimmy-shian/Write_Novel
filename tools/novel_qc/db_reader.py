# -*- coding: utf-8 -*-
"""DB 讀取層：只做 SELECT，沿用 backend.persistence.connection 的官方連線。"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.persistence.connection import get_db_connection  # noqa: E402


def _table_exists(cur, table: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def resolve_novel(conn, novel_id_or_title: str) -> Dict[str, Any]:
    cur = conn.cursor()
    row = cur.execute("SELECT id, title FROM novels WHERE id=?",
                      (novel_id_or_title,)).fetchone()
    if row:
        return {"id": row[0], "title": row[1]}
    row = cur.execute("SELECT id, title FROM novels WHERE title LIKE ? LIMIT 1",
                      (f"%{novel_id_or_title}%",)).fetchone()
    if row:
        return {"id": row[0], "title": row[1]}
    raise ValueError(f"找不到小說：{novel_id_or_title}")


def load_chapters_latest(conn, novel_id: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT c.chapter_index, c.content, c.synopsis, c.version
        FROM chapters c
        INNER JOIN (SELECT chapter_index, MAX(version) AS mv FROM chapters
                    WHERE novel_id=? GROUP BY chapter_index) m
          ON m.chapter_index=c.chapter_index AND m.mv=c.version
        WHERE c.novel_id=? ORDER BY c.chapter_index ASC
    """, (novel_id, novel_id)).fetchall()
    return [{"chapter_index": r[0], "content": r[1] or "",
             "synopsis": r[2] or "", "version": r[3]} for r in rows]


def load_entities(conn, novel_id: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    if not _table_exists(cur, "temporal_entities"):
        return []
    rows = cur.execute(
        "SELECT name, entity_type, life_status, created_chapter, updated_chapter"
        " FROM temporal_entities WHERE novel_id=?", (novel_id,)).fetchall()
    return [{"name": r[0], "entity_type": r[1], "life_status": r[2],
             "created_chapter": r[3], "updated_chapter": r[4]} for r in rows]


def load_seeds(conn, novel_id: str) -> List[Dict[str, str]]:
    """收集伏筆種子：worldbuilding.foreshadowing_seeds ＋ foreshadowing_blueprints。"""
    seeds: List[Dict[str, str]] = []
    cur = conn.cursor()
    if _table_exists(cur, "worldbuilding"):
        # 只讀最新版本：歷史版本的種子名多為已廢棄措辭，會造成大面積誤報
        rows = cur.execute(
            "SELECT content FROM worldbuilding WHERE novel_id=? "
            "ORDER BY version DESC LIMIT 1", (novel_id,)).fetchall()
        for (content,) in rows:
            try:
                data = json.loads(content or "{}")
            except Exception:
                continue
            for s in data.get("foreshadowing_seeds") or []:
                if isinstance(s, dict) and s.get("name"):
                    seeds.append({"name": str(s["name"]), "source": "worldbuilding",
                                  "payoff": str(s.get("payoff_hint", ""))[:120]})
    if _table_exists(cur, "foreshadowing_blueprints"):
        for (blob,) in cur.execute(
                "SELECT blueprint_json FROM foreshadowing_blueprints WHERE novel_id=?",
                (novel_id,)):
            try:
                data = json.loads(blob or "{}")
            except Exception:
                continue
            items = data if isinstance(data, list) else data.get("seeds") or \
                data.get("items") or data.get("foreshadowings") or []
            for s in items if isinstance(items, list) else []:
                name = s.get("name") if isinstance(s, dict) else str(s)
                if name and all(x["name"] != name for x in seeds):
                    seeds.append({"name": str(name), "source": "blueprint", "payoff": ""})
    # 去重保序；前 10 枚視為策展級（worldbuilding 首批即正典 10 種子）
    seen, out = set(), []
    for i, s in enumerate(seeds):
        if s["name"] not in seen:
            seen.add(s["name"])
            s["curated"] = (i < 10)
            out.append(s)
    return out


def load_audit_stats(conn, novel_id: str) -> Dict[str, Any]:
    cur = conn.cursor()
    if not _table_exists(cur, "narrative_audits"):
        return {}
    out: Dict[str, Any] = {}
    for sev, cnt in cur.execute(
            "SELECT severity, COUNT(*) FROM narrative_audits WHERE novel_id=? GROUP BY severity",
            (novel_id,)):
        out[f"audit_{sev}"] = cnt
    return out


def open_conn():
    return get_db_connection()
