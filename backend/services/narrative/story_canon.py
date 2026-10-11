# -*- coding: utf-8 -*-
"""Story canon helpers.

The outline is the planned-canon source and temporal facts are the occurred-canon
source.  LLM extraction is observational only; it must not silently rewrite
planned character fate or the chapter timeline.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


_DATE_RE = re.compile(r"(?P<year>\d{1,6})\s*[年./-]\s*(?P<month>\d{1,2})\s*[月./-]\s*(?P<day>\d{1,2})\s*日?")
_MONTH_DAY_RE = re.compile(r"(?<!\d)(?P<month>\d{1,2})\s*(?:月|/)\s*(?P<day>\d{1,2})\s*日?")
_TIME_ORDER = {
    "dawn": 4,
    "morning": 8,
    "noon": 12,
    "afternoon": 15,
    "evening": 18,
    "night": 21,
    "深夜": 23,
    "清晨": 6,
    "早晨": 8,
    "上午": 10,
    "中午": 12,
    "下午": 15,
    "傍晚": 18,
    "晚上": 20,
    "夜": 21,
}


def normalize_timeline_anchor(value: Any, chapter_index: int = 0) -> Optional[Dict[str, Any]]:
    """Normalize structured or legacy time text into a comparable anchor."""
    if isinstance(value, dict):
        raw_date = value.get("date") or value.get("calendar_date") or value.get("date_anchor")
        ordinal = value.get("story_day", value.get("ordinal"))
        if isinstance(raw_date, dict):
            value = {**value, **raw_date}
            raw_date = value.get("date")
        date_text = str(raw_date or "").strip()
        year = value.get("year")
        month = value.get("month")
        day = value.get("day")
        time_of_day = str(value.get("time_of_day") or value.get("time") or "").strip().lower()
        sequence = value.get("sequence", value.get("event_sequence", 0))
        duration = value.get("duration_from_previous_minutes", 0)
    else:
        date_text = str(value or "").strip()
        ordinal = None
        year = month = day = None
        time_of_day = date_text.lower()
        sequence = 0
        duration = 0

    try:
        normalized_sequence = int(sequence or 0)
    except (TypeError, ValueError):
        normalized_sequence = 0

    if ordinal is not None:
        try:
            return {
                "story_day": int(ordinal),
                "time_of_day": time_of_day,
                "sequence": normalized_sequence,
                "duration_from_previous_minutes": int(duration or 0),
                "chapter_index": int(chapter_index or 0),
            }
        except (TypeError, ValueError):
            return None
    calendar_mode = "logical"
    if not (year and month and day):
        match = _DATE_RE.search(date_text)
        if match:
            year, month, day = (int(match.group(k)) for k in ("year", "month", "day"))
            calendar_mode = "full_date"
        else:
            partial_match = _MONTH_DAY_RE.search(date_text)
            if partial_match:
                month, day = (int(partial_match.group(k)) for k in ("month", "day"))
                try:
                    if not (1 <= month <= 12 and 1 <= day <= 31):
                        return None
                except (TypeError, ValueError):
                    return None
                try:
                    duration_minutes = int(duration or 0)
                except (TypeError, ValueError):
                    duration_minutes = 0
                return {
                    "date": f"{int(month):02d}-{int(day):02d}",
                    "story_day": int(month) * 32 + int(day),
                    "calendar_mode": "partial_date",
                    "time_of_day": time_of_day,
                    "sequence": normalized_sequence,
                    "duration_from_previous_minutes": duration_minutes,
                    "chapter_index": int(chapter_index or 0),
                }
    elif year and month and day:
        calendar_mode = "full_date"
    try:
        if not (year and month and day):
            return None
        dt = datetime(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None

    if not time_of_day:
        source = date_text.lower()
        time_of_day = next((key for key in _TIME_ORDER if key in source), "")
    try:
        duration_minutes = int(duration or 0)
    except (TypeError, ValueError):
        duration_minutes = 0
    return {
        "date": dt.strftime("%Y-%m-%d"),
        # Ordinal day gives date-based anchors the same comparable
        # axis as generated logical story_day anchors.
        "story_day": dt.toordinal(),
        "calendar_mode": calendar_mode,
        "time_of_day": time_of_day,
        "sequence": normalized_sequence,
        "duration_from_previous_minutes": duration_minutes,
        "chapter_index": int(chapter_index or 0),
    }


def compare_timeline_anchors(previous: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]) -> Optional[str]:
    if not previous or not current:
        return None
    previous_mode = previous.get("calendar_mode")
    current_mode = current.get("calendar_mode")
    if previous_mode and current_mode and previous_mode != current_mode:
        # A full calendar date and a yearless month/day cannot be compared
        # safely without inventing a year.
        return None
    if "story_day" in previous or "story_day" in current:
        left = (
            int(previous.get("story_day", 0)),
            _TIME_ORDER.get(str(previous.get("time_of_day", "")).lower(), 0),
            previous.get("sequence", 0),
        )
        right = (
            int(current.get("story_day", 0)),
            _TIME_ORDER.get(str(current.get("time_of_day", "")).lower(), 0),
            current.get("sequence", 0),
        )
    else:
        left = (previous["date"], _TIME_ORDER.get(previous.get("time_of_day", ""), 0), previous.get("sequence", 0))
        right = (current["date"], _TIME_ORDER.get(current.get("time_of_day", ""), 0), current.get("sequence", 0))
    try:
        duration = int(current.get("duration_from_previous_minutes", 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration < 0:
        return f"第 {current.get('chapter_index')} 章時間跨度不可為負數"
    if right < left:
        return f"第 {current.get('chapter_index')} 章時間倒流：{previous.get('date', previous.get('story_day'))} → {current.get('date', current.get('story_day'))}"
    return None


def iter_outline_chapters(volumes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    chapters: List[Dict[str, Any]] = []
    for volume in volumes or []:
        raw = volume.get("chapters_outline") or []
        if isinstance(raw, str):
            try:
                import json
                raw = json.loads(raw)
            except Exception:
                raw = []
        if isinstance(raw, list):
            chapters.extend(c for c in raw if isinstance(c, dict))
    return sorted(chapters, key=lambda item: int(item.get("chapter_index") or item.get("chapter") or 0))


def validate_timeline(volumes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate structured anchors and supported legacy date/time fields."""
    issues: List[Dict[str, Any]] = []
    previous = None
    for chapter in iter_outline_chapters(volumes):
        index = int(chapter.get("chapter_index") or chapter.get("chapter") or 0)
        anchor = normalize_timeline_anchor(chapter.get("timeline_anchor"), index)
        if anchor is None:
            anchor = normalize_timeline_anchor(chapter.get("date_anchor"), index)
        if anchor is None and chapter.get("time_setting") is not None:
            anchor = normalize_timeline_anchor(chapter.get("time_setting"), index)
        if anchor is None:
            continue
        error = compare_timeline_anchors(previous, anchor)
        if error:
            issues.append({"chapter_index": index, "severity": "critical", "dimension": "timeline", "evidence": error})
        previous = anchor
    return issues


def ensure_timeline_anchors(chapters: Iterable[Dict[str, Any]], previous_anchor: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Fill missing anchors deterministically without inventing calendar dates."""
    result = []
    cursor_day = int((previous_anchor or {}).get("story_day", 0))
    for sequence, chapter in enumerate(sorted((c for c in chapters if isinstance(c, dict)), key=lambda c: int(c.get("chapter_index") or 0)), 1):
        item = dict(chapter)
        index = int(item.get("chapter_index") or item.get("chapter") or sequence)
        anchor = normalize_timeline_anchor(item.get("timeline_anchor"), index)
        if anchor is None:
            anchor = normalize_timeline_anchor(item.get("date_anchor"), index)
        if anchor is None and item.get("time_setting") is not None:
            anchor = normalize_timeline_anchor(item.get("time_setting"), index)
        if anchor is None:
            cursor_day += 1 if previous_anchor or result else 0
            anchor = {
                "story_day": cursor_day,
                "time_of_day": "",
                "sequence": index,
                "duration_from_previous_minutes": 0,
                "chapter_index": index,
                "source": "deterministic_schedule",
            }
        else:
            cursor_day = int(anchor.get("story_day", cursor_day)) if "story_day" in anchor else cursor_day
        item["timeline_anchor"] = anchor
        result.append(item)
    return result


def planned_life_events(outline: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(outline, dict):
        return []
    candidates = []
    for key in ("planned_events", "story_events", "life_events", "character_events", "events"):
        value = outline.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    return [item for item in candidates if str(item.get("event_type") or item.get("type") or "").lower() in {
        "death", "dead", "kill", "resurrection", "revival", "revive", "life_status"
    }]


_DEATH_EVENT_TYPES = {"death", "dead", "kill"}
_REVIVAL_EVENT_TYPES = {"resurrection", "revival", "revive"}


def _life_transition(event: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Return (desired status, authorized event kind) for a life event."""
    kind = _event_type(event)
    if kind in _DEATH_EVENT_TYPES:
        return "dead", kind
    if kind in _REVIVAL_EVENT_TYPES:
        return "alive", kind
    if kind == "life_status":
        desired = str(event.get("life_status") or event.get("status") or "").strip().lower()
        if desired == "dead":
            return "dead", "death"
        if desired == "alive":
            return "alive", "revival"
    return None


def _event_character_names(event: Dict[str, Any]) -> List[str]:
    value = (
        event.get("character_name")
        or event.get("character")
        or event.get("name")
        or event.get("target_character")
    )
    if isinstance(value, list):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if item and str(item).strip()]


def _event_type(event: Dict[str, Any]) -> str:
    return str(event.get("event_type") or event.get("type") or "").strip().lower()


def get_life_status_at_chapter(novel_id: str, chapter_index: int) -> Dict[str, Dict[str, Any]]:
    """Return canonical life state as-of a chapter, not the database's latest snapshot.

    Planned rows are intentionally excluded.  They become occurred only when
    that chapter is committed, so a future death cannot make an earlier Writer
    chapter see a dead character.
    """
    from backend import persistence as db

    limit = int(chapter_index or 0)
    states: Dict[str, Dict[str, Any]] = {}
    try:
        entities = db.get_entities(novel_id, entity_type="character")
    except Exception:
        entities = []
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        status = str(entity.get("life_status") or "").lower().strip()
        status_chapter = entity.get("life_status_chapter")
        source = str(entity.get("life_status_source") or "unknown")
        try:
            status_chapter = int(status_chapter) if status_chapter is not None else None
        except (TypeError, ValueError):
            status_chapter = None
        if name and status in {"alive", "dead"} and source in {"authoritative", "outline", "story_event"} \
                and (status_chapter is None or status_chapter <= limit):
            states[name] = {"name": name, "life_status": status, "chapter_index": status_chapter, "source": source}

    try:
        events = db.get_story_events(novel_id, status="occurred")
    except Exception:
        events = []
    for event in sorted(events, key=lambda item: int(item.get("chapter_index") or 0)):
        # Graphiti/extractor rows are observations only.  They are useful for
        # auditing evidence, but cannot mutate the canonical life timeline.
        if str(event.get("source") or "").lower() not in {
            "story_canon_schedule", "authoritative", "backfill"
        }:
            continue
        event_chapter = int(event.get("chapter_index") or 0)
        if event_chapter > limit:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
        event_data = {**event, **payload}
        transition_spec = _life_transition(event_data)
        if not transition_spec:
            continue
        status, _kind = transition_spec
        for name in _event_character_names(event_data):
            states[name] = {
                "name": name,
                "life_status": status,
                "chapter_index": event_chapter,
                "source": "story_event",
            }
    return states


def get_authoritative_life_statuses(novel_id: str, chapter_index: int) -> List[Dict[str, Any]]:
    return list(get_life_status_at_chapter(novel_id, chapter_index).values())


def advance_story_canon_for_chapter(novel_id: str, chapter_index: int) -> Dict[str, Any]:
    """Commit planned life events for a completed chapter.

    This is the only normal path that turns a planned fate into an occurred
    fact.  Writer text and Graphiti observations can report evidence, but they
    cannot perform this transition.
    """
    from backend import persistence as db
    from backend.persistence.repositories.temporal_graph import (
        apply_authorized_life_transition,
        upsert_entity,
    )
    from backend.persistence.repositories.story_events import upsert_story_event

    planned = db.get_story_events(novel_id, chapter_index=int(chapter_index), status="planned")
    applied: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    def _event_sequence(item: Dict[str, Any]) -> int:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        try:
            return int(payload.get("sequence", payload.get("event_sequence", 0)) or 0)
        except (TypeError, ValueError):
            return 0

    planned = sorted(planned, key=_event_sequence)
    prepared: List[Tuple[Dict[str, Any], Dict[str, Any], str, str, List[str]]] = []
    for event in planned:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
        event_data = {**event, **payload}
        transition_spec = _life_transition(event_data)
        if not transition_spec:
            continue
        desired, kind = transition_spec
        names = _event_character_names(event_data)
        if not names:
            issues.append({"event_type": kind, "error": "生命事件缺少 character/name"})
            continue
        prepared.append((event, payload, desired, kind, names))

    # Preflight the complete chapter before mutating any life state.  This
    # prevents a malformed second character in one event from leaving the
    # first character half-committed.
    if issues:
        return {
            "chapter_index": int(chapter_index),
            "planned_events": len(planned),
            "applied": [],
            "issues": issues,
        }

    conn = db.get_db_connection()
    try:
        with conn:
            # Placeholder entities and their life transitions belong to the
            # same transaction.  A malformed later transition must not leave
            # behind a half-created character record.
            existing_entities = {
                item.get("name")
                for item in db.get_entities(novel_id, entity_type="character")
            }
            for _event, _payload, _desired, _kind, names in prepared:
                for name in names:
                    if name not in existing_entities:
                        upsert_entity(
                            novel_id, name, "character", summary="由章綱生命事件建立的角色實體",
                            life_status="unknown", chapter_index=int(chapter_index), source="outline",
                            conn=conn,
                        )
                        existing_entities.add(name)
            for event, payload, desired, kind, names in prepared:
                for name in names:
                    transition = apply_authorized_life_transition(
                        novel_id, name, desired, int(chapter_index), kind,
                        reason=str(event.get("description") or payload.get("description") or "chapter contract"),
                        conn=conn,
                    )
                    applied.append({"name": name, "event_type": kind, **transition})
                upsert_story_event(
                    novel_id, int(chapter_index), payload, status="occurred",
                    source="story_canon_schedule", conn=conn,
                )
    except Exception as exc:
        return {
            "chapter_index": int(chapter_index),
            "planned_events": len(planned),
            "applied": [],
            "issues": [{"error": str(exc)}],
        }
    return {"chapter_index": int(chapter_index), "planned_events": len(planned), "applied": applied, "issues": issues}


def validate_publication_canon(novel_id: str) -> List[Dict[str, Any]]:
    """Publication-boundary checks for timeline and committed life events."""
    from backend import persistence as db

    issues = []
    volumes = db.get_volumes(novel_id) or []
    issues.extend(validate_timeline(volumes))
    clean_chapters = {
        int(row.get("chapter_index") or 0)
        for row in (db.get_all_chapters_latest(novel_id) or [])
        if str(row.get("content") or "").strip() and not row.get("is_dirty")
    }
    try:
        planned = db.get_story_events(novel_id, status="planned")
        occurred = db.get_story_events(novel_id, status="occurred")
    except Exception:
        planned, occurred = [], []
    occurred_keys = set()
    for item in occurred:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        occurred_keys.add((int(item.get("chapter_index") or 0), _event_type({**item, **payload}), tuple(_event_character_names({**item, **payload}))))
    for item in planned:
        chapter = int(item.get("chapter_index") or 0)
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        key = (chapter, _event_type({**item, **payload}), tuple(_event_character_names({**item, **payload})))
        event_data = {**item, **payload}
        transition_spec = _life_transition(event_data)
        if chapter in clean_chapters and transition_spec and key not in occurred_keys:
            issues.append({
                "chapter_index": chapter,
                "severity": "critical",
                "dimension": "life_event_commit",
                "evidence": f"第 {chapter} 章已發稿，但規劃生命事件尚未提交為 occurred：{key[1]} {key[2]}",
            })
    return issues


def build_canon_context(outline: Optional[Dict[str, Any]], chapter_index: int, entity_statuses: Optional[List[Dict[str, Any]]] = None) -> str:
    import json
    anchor = normalize_timeline_anchor((outline or {}).get("timeline_anchor"), chapter_index)
    events = planned_life_events(outline)
    lines = ["【Story Canon 權威契約】", "Writer 可創作敘事細節，但不得未經授權改寫以下因果與命運。"]
    if anchor:
        lines.append("本章機器時間錨點：" + json.dumps(anchor, ensure_ascii=False))
    else:
        lines.append("本章尚無機器時間錨點，禁止自行創造精確日期；請承接章綱時間。")
    if events:
        lines.append("本章預定生命事件：" + json.dumps(events, ensure_ascii=False))
    if entity_statuses:
        lines.append("已確立角色狀態：" + json.dumps(entity_statuses, ensure_ascii=False))
    lines.append("死亡與復活均可發生，但必須對應本章預定事件或已確立事件紀錄；回憶、幻象與平行線需明確標註。")
    return "\n".join(lines)


def build_chapter_contract(
    outline: Optional[Dict[str, Any]],
    chapter_index: int,
    setting_names: Optional[Any] = None,
    terms: Optional[List[Dict[str, Any]]] = None,
    foreshadowing: Optional[str] = None,
    conflict: Optional[str] = None,
) -> str:
    """Render one compact contract that points every helper at the same chapter."""
    import json
    outline = outline or {}
    payload = {
        "chapter_index": int(chapter_index),
        "timeline_anchor": outline.get("timeline_anchor"),
        "planned_events": planned_life_events(outline),
        "setting_usage": setting_names or outline.get("setting_usage") or [],
        "story_terms": terms or [],
        "foreshadowing_tasks": foreshadowing or "",
        "conflict_signature": outline.get("conflict_signature_hint") or conflict or "",
    }
    return "【Chapter Contract 統一章節契約】\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def validate_life_contract(novel_id: str, chapter_index: int, outline: Optional[Dict[str, Any]], prose: str) -> List[Dict[str, Any]]:
    """Find unauthorized fate changes before chapter save.

    The outline may authorize either death or revival in the current chapter.
    Without that authorization, an established alive character cannot be
    killed in prose and an established dead character cannot act or revive in
    present time.  Only known canonical character names are inspected, so an
    unrelated person's death sentence is not treated as evidence about every
    character in the database.
    """
    if not prose or not novel_id:
        return []
    statuses = get_life_status_at_chapter(novel_id, max(0, int(chapter_index) - 1))
    planned_by_character: Dict[str, set] = {}
    for event in planned_life_events(outline):
        transition_spec = _life_transition(event)
        kind = transition_spec[1] if transition_spec else _event_type(event)
        for name in _event_character_names(event):
            planned_by_character.setdefault(name, set()).add(kind)
    memory_markers = ("回憶", "記憶", "夢境", "幻象", "亡靈", "靈魂", "傳說", "傳聞", "聽說", "據說", "謠言", "昔日", "當年")
    active_markers = ("說", "回答", "走進", "站在", "開口", "施法", "拔劍", "命令", "望向")
    death_markers = (
        "戰死", "身亡", "犧牲", "隕落", "死亡", "消散", "陣亡", "死去", "被殺",
        "身死道消", "斬首", "灰飛煙滅", "形神俱滅", "魂飛魄散", "化為齏粉", "化灰",
    )
    revival_markers = ("復活", "重生", "復甦", "起死回生", "重新活著", "活了過來", "死而復生")
    issues = []
    for name, state in statuses.items():
        if not name or state.get("life_status") not in {"alive", "dead"}:
            continue
        allowed_events = planned_by_character.get(name, set())
        for sentence in re.split(r"(?<=[。！？!?])\s*|\n+", prose):
            if name not in sentence:
                continue
            if any(marker in sentence for marker in memory_markers):
                continue
            current_status = state.get("life_status")
            if current_status == "dead":
                # A planned revival is the explicit authorization for present
                # agency.  It is intentionally not a permanent lock.
                if allowed_events & _REVIVAL_EVENT_TYPES:
                    continue
                if any(marker in sentence for marker in active_markers + revival_markers):
                    issues.append({
                        "chapter_index": int(chapter_index),
                        "dimension": "life_status",
                        "severity": "critical",
                        "character": name,
                        "evidence": sentence.strip()[:240],
                        "recommendation": f"角色「{name}」已由故事事實標記死亡，請補上本章授權復活事件，或改寫為回憶／幻象／亡靈等明確敘事層。",
                    })
                    break
            elif any(marker in sentence for marker in death_markers):
                # An alive canonical character may die, but only when the
                # current chapter contract explicitly schedules that fate.
                if allowed_events & _DEATH_EVENT_TYPES:
                    continue
                issues.append({
                    "chapter_index": int(chapter_index),
                    "dimension": "life_status",
                    "severity": "critical",
                    "character": name,
                    "evidence": sentence.strip()[:240],
                    "recommendation": f"角色「{name}」的死亡未出現在本章劇情契約，請補入預定死亡事件或保留既有命運。",
                })
                break
    return issues
