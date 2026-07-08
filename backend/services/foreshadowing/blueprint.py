# -*- coding: utf-8 -*-
"""Deterministic foreshadowing/turning-point allocation service.

The database module stores and fetches rows. This module owns the hard
calculation rules for where seeds and turning points are assigned.
"""

import hashlib
import json
import random

from backend.services.foreshadowing.chapter_math import get_total_chapter_count, get_volume_chapter_range


def canonical_seed_id(seed_index):
    return f"FS{seed_index + 1:03d}"


def coerce_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def normalize_allocation_pair(pair, total_chapters):
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    plant_chapter = coerce_int(pair[0])
    payoff_chapter = coerce_int(pair[1])
    if total_chapters <= 0:
        total_chapters = max(plant_chapter, payoff_chapter, 1)
    plant_chapter = max(1, min(total_chapters, plant_chapter))
    payoff_chapter = max(1, min(total_chapters, payoff_chapter))
    if total_chapters > 1 and payoff_chapter <= plant_chapter:
        plant_chapter = max(1, min(total_chapters - 1, plant_chapter))
        payoff_chapter = plant_chapter + 1
    return plant_chapter, payoff_chapter


def is_valid_foreshadowing_blueprint(blueprint, seed_count, turn_count, total_chapters):
    if not isinstance(blueprint, dict):
        return False
    allocations = blueprint.get("foreshadowing_allocations", [])
    turns = blueprint.get("turning_allocations", [])
    if len(allocations) != seed_count or len(turns) != turn_count:
        return False
    if total_chapters <= 1:
        return True
    for pair in allocations:
        normalized = normalize_allocation_pair(pair, total_chapters)
        if not normalized:
            return False
        plant_chapter, payoff_chapter = normalized
        if total_chapters > 1 and plant_chapter >= payoff_chapter:
            return False
    for turn_chapter in turns:
        turn_chapter = coerce_int(turn_chapter)
        if turn_chapter < 1 or (total_chapters > 0 and turn_chapter > total_chapters):
            return False
    return True


def build_canonical_foreshadowing_task_map(novel_id):
    """Return chapter_index -> canonical allocated_tasks from the deterministic blueprint."""
    from backend import persistence as db

    volumes = db.get_volumes(novel_id)
    if not volumes:
        return {}
    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    seeds = worldview.get("foreshadowing_seeds", []) or []
    turns = worldview.get("key_turning_points", []) or []
    blueprint = get_global_foreshadowing_blueprint(novel_id)
    total_chapters = coerce_int(blueprint.get("T"), get_total_chapter_count(volumes))

    task_map = {}

    def chapter_tasks(chapter_index):
        chapter_index = int(chapter_index)
        if chapter_index not in task_map:
            task_map[chapter_index] = {
                "foreshadowing_plants": [],
                "foreshadowing_payoffs": [],
                "turning_points": [],
            }
        return task_map[chapter_index]

    for idx, pair in enumerate(blueprint.get("foreshadowing_allocations", [])[:len(seeds)]):
        normalized = normalize_allocation_pair(pair, total_chapters)
        if not normalized:
            continue
        plant_chapter, payoff_chapter = normalized
        seed_id = canonical_seed_id(idx)
        chapter_tasks(plant_chapter)["foreshadowing_plants"].append(seed_id)
        chapter_tasks(payoff_chapter)["foreshadowing_payoffs"].append(seed_id)

    for idx, turn_chapter in enumerate(blueprint.get("turning_allocations", [])[:len(turns)]):
        turn_chapter = coerce_int(turn_chapter)
        if turn_chapter <= 0:
            continue
        chapter_tasks(turn_chapter)["turning_points"].append(f"TP{idx + 1:03d}")

    return task_map


def apply_canonical_allocated_tasks_to_chapters(novel_id, chapters):
    """Overwrite foreshadowing/turn allocations so each seed has one plant and one payoff."""
    task_map = build_canonical_foreshadowing_task_map(novel_id)
    normalized = {}
    for chapter in chapters or []:
        if not isinstance(chapter, dict):
            continue
        chapter_index = chapter.get("chapter_index")
        if chapter_index is None:
            continue
        chapter_index = int(chapter_index)
        chapter["chapter_index"] = chapter_index
        allocated = chapter.get("allocated_tasks")
        if not isinstance(allocated, dict):
            allocated = {}
        canonical = task_map.get(chapter_index, {})
        allocated["foreshadowing_plants"] = list(canonical.get("foreshadowing_plants", []))
        allocated["foreshadowing_payoffs"] = list(canonical.get("foreshadowing_payoffs", []))
        allocated["turning_points"] = list(canonical.get("turning_points", []))
        chapter["allocated_tasks"] = allocated
        for stale_key in (
            "foreshadowing_plant",
            "foreshadowing_plants",
            "foreshadowing_payoff",
            "foreshadowing_payoffs",
            "foreshadowing",
        ):
            chapter.pop(stale_key, None)
        normalized[chapter_index] = chapter
    return normalized


def repair_foreshadowing_allocations(novel_id, volume_index=None):
    """Rewrite existing volume skeletons and stitched plot with deterministic allocations."""
    from backend import persistence as db

    conn = db.get_db_connection()
    cursor = conn.cursor()
    if volume_index is None:
        rows = cursor.execute(
            "SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC",
            (novel_id,),
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT * FROM volumes WHERE novel_id = ? AND volume_index = ? ORDER BY volume_index ASC",
            (novel_id, int(volume_index)),
        ).fetchall()

    all_chapters = []
    touched = 0
    for row in rows:
        volume = dict(row)
        try:
            chapters = json.loads(volume.get("chapters_outline") or "[]")
        except Exception:
            chapters = []
        if not isinstance(chapters, list):
            chapters = []
        canonical_map = apply_canonical_allocated_tasks_to_chapters(novel_id, chapters)
        canonical_list = list(canonical_map.values())
        canonical_list.sort(key=lambda item: int(item.get("chapter_index", 0)))
        cursor.execute(
            "UPDATE volumes SET chapters_outline = ? WHERE id = ?",
            (json.dumps(db._convert_obj_to_traditional(canonical_list), ensure_ascii=False), volume["id"]),
        )
        all_chapters.extend(canonical_list)
        touched += 1

    if volume_index is None and all_chapters:
        all_chapters.sort(key=lambda item: int(item.get("chapter_index", 0)))
        row_max = cursor.execute(
            "SELECT MAX(version) as max_v FROM plot_chapters WHERE novel_id = ?",
            (novel_id,),
        ).fetchone()
        next_version = (row_max["max_v"] or 0) + 1
        cursor.execute(
            "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, ?, 0)",
            (
                novel_id,
                json.dumps({"chapters": db._convert_obj_to_traditional(all_chapters)}, ensure_ascii=False),
                next_version,
            ),
        )

    conn.commit()
    conn.close()
    return touched


def precompute_global_foreshadowing(novel_id):
    """Precompute and persist deterministic global foreshadowing allocations."""
    from backend import persistence as db

    volumes = db.get_volumes(novel_id)
    if not volumes:
        from backend.common.config import MIN_CHAPTERS_PER_VOLUME, MIN_VOLUME_COUNT

        return {
            "T": MIN_VOLUME_COUNT * MIN_CHAPTERS_PER_VOLUME,
            "foreshadowing_allocations": [],
            "turning_allocations": [],
        }

    sorted_volumes = sorted(volumes, key=lambda item: int(item.get("volume_index", 0)))
    _, total_chapters = get_volume_chapter_range(volumes, sorted_volumes[-1]["volume_index"])

    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview.get("foreshadowing_seeds", [])
    all_turns = worldview.get("key_turning_points", [])

    random_seed = int(hashlib.md5(f"global_blueprint_{novel_id}".encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(random_seed)

    foreshadowing_allocations = []
    volume_count = len(sorted_volumes)
    min_payoff_distance = max(20, int(total_chapters * 0.05))

    for idx, _seed in enumerate(all_seeds):
        if volume_count <= 1:
            start_p, end_p = get_volume_chapter_range(volumes, sorted_volumes[0]["volume_index"])
            if end_p - start_p >= 1:
                plant_chapter = rng.randint(start_p, end_p - 1)
                payoff_chapter = rng.randint(plant_chapter + 1, end_p)
            else:
                plant_chapter = start_p
                payoff_chapter = end_p
        else:
            plant_volume_index = (idx % volume_count) + 1
            if plant_volume_index < volume_count:
                payoff_volume_index = rng.randint(plant_volume_index + 1, volume_count)
            else:
                plant_volume_index = rng.randint(1, volume_count - 1)
                payoff_volume_index = volume_count

            start_p, end_p = get_volume_chapter_range(volumes, plant_volume_index)
            start_r, end_r = get_volume_chapter_range(volumes, payoff_volume_index)
            plant_chapter = rng.randint(start_p, end_p)

            low = max(start_r, plant_chapter + min_payoff_distance)
            high = end_r
            if low > high:
                low = start_r
            if low > high:
                low = high
            payoff_chapter = rng.randint(low, high)

        normalized_pair = normalize_allocation_pair((plant_chapter, payoff_chapter), total_chapters)
        if normalized_pair:
            foreshadowing_allocations.append(normalized_pair)

    turning_allocations = []
    for idx, _turn in enumerate(all_turns):
        if volume_count > 0:
            turn_volume_index = (idx % volume_count) + 1
            start_k, end_k = get_volume_chapter_range(volumes, turn_volume_index)
            turn_chapter = rng.randint(start_k, end_k)
        else:
            turn_chapter = rng.randint(1, total_chapters)
        turning_allocations.append(turn_chapter)

    blueprint = {
        "T": total_chapters,
        "foreshadowing_allocations": foreshadowing_allocations,
        "turning_allocations": turning_allocations,
    }

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO foreshadowing_blueprints (novel_id, blueprint_json) VALUES (?, ?)",
        (novel_id, json.dumps(blueprint, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    print(f"[DB] Global foreshadowing blueprint precomputed successfully for novel {novel_id} (T={total_chapters})")
    return blueprint


def get_global_foreshadowing_blueprint(novel_id):
    """Fetch the persisted blueprint, recomputing when stale or missing."""
    from backend import persistence as db

    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview.get("foreshadowing_seeds", [])
    all_turns = worldview.get("key_turning_points", [])

    conn = db.get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT blueprint_json FROM foreshadowing_blueprints WHERE novel_id = ?", (novel_id,)).fetchone()
    conn.close()

    if row:
        try:
            blueprint = json.loads(row["blueprint_json"])
            total_chapters = coerce_int(blueprint.get("T"), get_total_chapter_count(db.get_volumes(novel_id)))
            if is_valid_foreshadowing_blueprint(blueprint, len(all_seeds), len(all_turns), total_chapters):
                return blueprint
        except Exception as exc:
            print(f"[WARN] Failed to load/validate global blueprint: {exc}")

    return precompute_global_foreshadowing(novel_id)
