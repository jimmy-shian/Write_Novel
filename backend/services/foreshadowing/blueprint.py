# -*- coding: utf-8 -*-
"""Foreshadowing / Turning-point allocation service (Director-Dispatch 架構).

=== 演算法重劃 ===
原先版本使用 rng.randint + idx % volume_count 隨機撒網指派伏筆落點，
導致時序倒置（分卷前盲猜章節）、埋而未收（50+ 章逾期）與藍圖漂移。

新架構：
1. 總監透過 dispatch_foreshadowing_quota 工具主動派發每卷配額與落點。
2. Python 只做夾具驗證（1 <= plant < payoff <= T、章號在該卷區間內）。
3. 已有幾何圖譜 (Geometry) 的作品仍可由圖譜導出藍圖（確定性，無隨機數）。
4. 伏筆生命週期狀態機：PENDING -> PLANTED -> PAID / OVERDUE。
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.services.foreshadowing.chapter_math import get_total_chapter_count, get_volume_chapter_range


def canonical_seed_id(seed_index):
    return f"FS{seed_index + 1:03d}"


def coerce_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def foreshadowing_payoff_keywords(seed) -> List[str]:
    """Extract stable, human-authored payoff keywords from a seed.

    Old string/list-shaped seeds intentionally return an empty list so callers
    can keep the legacy existence-only behaviour.
    """
    if not isinstance(seed, dict):
        return []
    fields = (
        seed.get("name") or seed.get("title") or seed.get("seed_name") or seed.get("伏筆名稱") or seed.get("名稱"),
        seed.get("description") or seed.get("desc") or seed.get("內容") or seed.get("描述"),
        seed.get("payoff_hint") or seed.get("payoff") or seed.get("reveal") or seed.get("resolution")
        or seed.get("callback") or seed.get("回收章節") or seed.get("回收位置"),
    )
    keywords = []
    for value in fields:
        text = re.sub(r"\s+", "", str(value or "")).lower()
        if not text:
            continue
        keywords.extend(re.findall(r"[a-z0-9]{2,}", text))
        for run in re.findall(r"[\u4e00-\u9fff]+", text):
            if 2 <= len(run) <= 8:
                keywords.append(run)
            for size in (4, 3, 2):
                keywords.extend(run[i:i + size] for i in range(len(run) - size + 1))
    return list(dict.fromkeys(k for k in keywords if len(k) >= 2))


def verify_foreshadowing_payoff(seed, content) -> Optional[bool]:
    """Return whether payoff evidence exists in正文, or ``None`` for legacy seeds."""
    keywords = foreshadowing_payoff_keywords(seed)
    if not keywords:
        return None
    text = re.sub(r"\s+", "", str(content or "")).lower()
    if not text:
        return False
    # A named seed or an explicit payoff term is sufficient; descriptions
    # need two hits to avoid accepting incidental common words.
    values = seed if isinstance(seed, dict) else {}
    strong = (
        values.get("name") or values.get("title") or values.get("seed_name") or values.get("伏筆名稱") or values.get("名稱"),
        values.get("payoff_hint") or values.get("payoff") or values.get("reveal") or values.get("resolution")
        or values.get("callback") or values.get("回收章節") or values.get("回收位置"),
    )
    for value in strong:
        phrase = re.sub(r"\s+", "", str(value or "")).lower()
        if len(phrase) >= 2 and phrase in text:
            return True
    return sum(1 for keyword in keywords if keyword in text) >= 2


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


# =====================================================================
# 伏筆生命週期狀態機
# =====================================================================

LIFECYCLE_STATES = ("PENDING", "PLANTED", "PAID", "OVERDUE")


def get_foreshadowing_lifecycle(novel_id: str) -> List[Dict[str, Any]]:
    """取得所有伏筆種子的生命週期狀態。

    回傳每個 seed 的 { seed_id, state, plant_chapter, payoff_chapter, actual_planted, actual_paid }。
    """
    from backend import persistence as db

    blueprint = get_global_foreshadowing_blueprint(novel_id)
    if not blueprint:
        return []

    allocations = blueprint.get("foreshadowing_allocations", [])

    # 取得已寫章節集合
    chapters_written = set()
    try:
        all_ch = db.get_all_chapters_latest(novel_id)
        chapters_written = {
            int(c.get("chapter_index", 0)) for c in all_ch
            if (c.get("content") or "").strip()
        }
    except Exception:
        pass

    max_written = max(chapters_written) if chapters_written else 0
    lifecycle = []

    for idx, pair in enumerate(allocations):
        normalized = normalize_allocation_pair(pair, blueprint.get("T", 9999))
        if not normalized:
            continue
        plant_ch, payoff_ch = normalized
        seed_id = canonical_seed_id(idx)

        if plant_ch in chapters_written and payoff_ch in chapters_written:
            state = "PAID"
        elif plant_ch in chapters_written and payoff_ch not in chapters_written:
            if payoff_ch <= max_written:
                state = "OVERDUE"
            else:
                state = "PLANTED"
        else:
            state = "PENDING"

        lifecycle.append({
            "seed_id": seed_id,
            "state": state,
            "plant_chapter": plant_ch,
            "payoff_chapter": payoff_ch,
        })

    return lifecycle


def get_overdue_foreshadowing(novel_id: str) -> List[Dict[str, Any]]:
    """快速取得所有逾期未收的伏筆列表。"""
    return [s for s in get_foreshadowing_lifecycle(novel_id) if s["state"] == "OVERDUE"]


# =====================================================================
# 總監派發接口 (Director Dispatch)
# =====================================================================

def dispatch_foreshadowing_allocation(
    novel_id: str,
    allocations: List[Tuple[int, int]],
    turning_allocations: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """由總監主動派發伏筆與轉折落點，取代隨機 precompute。

    Parameters:
        novel_id: 作品 ID
        allocations: [(plant_chapter, payoff_chapter), ...] 總監指定的埋設/回收對照表
        turning_allocations: [chapter_index, ...] 總監指定的轉折點章節

    Returns:
        持久化後的 blueprint 物件

    Raises:
        ValueError: 若任何 allocation 不通過夾具驗證
    """
    from backend import persistence as db

    volumes = db.get_volumes(novel_id)
    total_chapters = get_total_chapter_count(volumes) if volumes else 0
    if total_chapters <= 0:
        raise ValueError("分卷結構尚未確立，無法派發伏筆配額。請先完成分卷規劃。")

    # 夾具驗證：每對 (plant, payoff) 必須滿足 1 <= plant < payoff <= T
    validated_alloc = []
    for i, pair in enumerate(allocations):
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            raise ValueError(f"第 {i+1} 條伏筆格式錯誤：需要 (plant_chapter, payoff_chapter) 二元組")
        plant_ch, payoff_ch = coerce_int(pair[0]), coerce_int(pair[1])
        if plant_ch < 1 or payoff_ch < 1:
            raise ValueError(f"第 {i+1} 條伏筆章號必須 >= 1，得到 plant={plant_ch}, payoff={payoff_ch}")
        if plant_ch > total_chapters or payoff_ch > total_chapters:
            raise ValueError(
                f"第 {i+1} 條伏筆章號越界：plant={plant_ch}, payoff={payoff_ch}，全書共 {total_chapters} 章"
            )
        if plant_ch >= payoff_ch:
            raise ValueError(
                f"第 {i+1} 條伏筆時序錯誤：plant ({plant_ch}) 必須在 payoff ({payoff_ch}) 之前"
            )
        validated_alloc.append((plant_ch, payoff_ch))

    # 驗證轉折點
    validated_turns = []
    for i, turn_ch in enumerate(turning_allocations or []):
        turn_ch = coerce_int(turn_ch)
        if turn_ch < 1 or turn_ch > total_chapters:
            raise ValueError(f"第 {i+1} 個轉折點章號越界：{turn_ch}，全書共 {total_chapters} 章")
        validated_turns.append(turn_ch)

    blueprint = {
        "T": total_chapters,
        "foreshadowing_allocations": validated_alloc,
        "turning_allocations": validated_turns,
        "source": "director_dispatch",
    }

    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO foreshadowing_blueprints (novel_id, blueprint_json) VALUES (?, ?)",
            (novel_id, json.dumps(blueprint, ensure_ascii=False)),
        )

    print(f"[Blueprint] Director dispatch: {len(validated_alloc)} foreshadowing + {len(validated_turns)} turns for {novel_id}")
    return blueprint


# =====================================================================
# 向後相容：build_canonical_foreshadowing_task_map
# =====================================================================

def build_canonical_foreshadowing_task_map(novel_id):
    """Return chapter_index -> canonical allocated_tasks from the blueprint.

    無論藍圖來源（總監派發或幾何圖譜），統一回傳各章的伏筆/轉折指派。
    """
    from backend import persistence as db

    volumes = db.get_volumes(novel_id)
    if not volumes and not db.has_geometry(novel_id):
        return {}
    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    seeds = worldview.get("foreshadowing_seeds", []) or []
    turns = worldview.get("key_turning_points", []) or []
    blueprint = get_global_foreshadowing_blueprint(novel_id)
    total_chapters = coerce_int(blueprint.get("T"), get_total_chapter_count(volumes) if volumes else 800)

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
    """Merge foreshadowing/turn allocations into each chapter's allocated_tasks.

    注意：改為合併 (merge) 而非覆寫 (overwrite)。
    若章節已有 LLM/總監設定的 allocated_tasks，保留其非伏筆欄位，
    只更新 foreshadowing_plants / foreshadowing_payoffs / turning_points 三個欄位。
    """
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
    """Rewrite existing volume skeletons and stitched plot with blueprint allocations."""
    from backend import persistence as db

    conn = db.get_db_connection()
    with conn:
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

    return touched


# =====================================================================
# 預設藍圖生成 (Fallback：保留向後相容，但不再使用隨機數)
# =====================================================================

def precompute_global_foreshadowing(novel_id):
    """為尚無總監派發或幾何圖譜的作品生成初始骨架藍圖。

    新版改為均勻分佈而非隨機撒網：以卷為單位，每卷按比例分配伏筆埋設/回收對。
    此函數僅作為 fallback，建議優先由總監透過 dispatch_foreshadowing_allocation 派發。
    """
    from backend import persistence as db

    volumes = db.get_volumes(novel_id)
    if not volumes:
        from backend.common.config import MIN_CHAPTERS_PER_VOLUME, MIN_VOLUME_COUNT

        return {
            "T": MIN_VOLUME_COUNT * MIN_CHAPTERS_PER_VOLUME,
            "foreshadowing_allocations": [],
            "turning_allocations": [],
            "source": "fallback_empty",
        }

    sorted_volumes = sorted(volumes, key=lambda item: int(item.get("volume_index", 0)))
    _, total_chapters = get_volume_chapter_range(volumes, sorted_volumes[-1]["volume_index"])

    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview.get("foreshadowing_seeds", [])
    all_turns = worldview.get("key_turning_points", [])

    volume_count = len(sorted_volumes)
    min_payoff_distance = max(20, int(total_chapters * 0.05))

    # 均勻分配伏筆：每個 seed 依序分配到卷，plant 在前半卷、payoff 在後半卷
    foreshadowing_allocations = []
    for idx, _seed in enumerate(all_seeds):
        if volume_count <= 1:
            start_p, end_p = get_volume_chapter_range(volumes, sorted_volumes[0]["volume_index"])
            mid = (start_p + end_p) // 2
            if end_p - start_p >= 1:
                plant_chapter = start_p + (idx % max(1, mid - start_p))
                payoff_chapter = mid + 1 + (idx % max(1, end_p - mid))
            else:
                plant_chapter = start_p
                payoff_chapter = end_p
        else:
            # 均勻分配到卷：前半書卷埋設，後半書卷回收
            plant_volume_index = (idx % volume_count) + 1
            if plant_volume_index < volume_count:
                payoff_volume_index = min(volume_count, plant_volume_index + max(1, volume_count // 3))
            else:
                plant_volume_index = max(1, volume_count - 1)
                payoff_volume_index = volume_count

            start_p, end_p = get_volume_chapter_range(volumes, plant_volume_index)
            start_r, end_r = get_volume_chapter_range(volumes, payoff_volume_index)

            # 均勻分散在卷內，而非隨機
            vol_span_p = max(1, end_p - start_p + 1)
            plant_chapter = start_p + (idx % vol_span_p)

            vol_span_r = max(1, end_r - start_r + 1)
            low = max(start_r, plant_chapter + min_payoff_distance)
            if low > end_r:
                low = start_r
            payoff_chapter = low + (idx % max(1, end_r - low + 1))

        normalized_pair = normalize_allocation_pair((plant_chapter, payoff_chapter), total_chapters)
        if normalized_pair:
            foreshadowing_allocations.append(normalized_pair)

    # 均勻分配轉折點
    turning_allocations = []
    for idx, _turn in enumerate(all_turns):
        if volume_count > 0:
            turn_volume_index = (idx % volume_count) + 1
            start_k, end_k = get_volume_chapter_range(volumes, turn_volume_index)
            vol_span = max(1, end_k - start_k + 1)
            turn_chapter = start_k + (idx % vol_span)
        else:
            turn_chapter = 1 + (idx % max(1, total_chapters))
        turning_allocations.append(turn_chapter)

    blueprint = {
        "T": total_chapters,
        "foreshadowing_allocations": foreshadowing_allocations,
        "turning_allocations": turning_allocations,
        "source": "fallback_uniform",
    }

    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO foreshadowing_blueprints (novel_id, blueprint_json) VALUES (?, ?)",
            (novel_id, json.dumps(blueprint, ensure_ascii=False)),
        )

    print(f"[DB] Global foreshadowing blueprint (uniform fallback) for novel {novel_id} (T={total_chapters})")
    return blueprint


# =====================================================================
# 幾何圖譜導出藍圖（確定性，無隨機數）
# =====================================================================

def build_blueprint_from_geometry(novel_id):
    """從 Geometry Graph 的 SETS_UP / PAYS_OFF 與 CONVERGE/PAYOFF 節點提取確定性伏筆與轉折分配。"""
    from backend import persistence as db

    graph = db.load_geometry_graph(novel_id)
    if not graph or not graph.nodes:
        return None

    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview.get("foreshadowing_seeds", []) or []
    all_turns = worldview.get("key_turning_points", []) or []

    total_chapters = graph.params.target_chapters if hasattr(graph, "params") and graph.params else 800

    # 1. 提取所有 SETS_UP 和 PAYS_OFF 關聯邊
    payoff_edges = [e for e in graph.edges if getattr(e.edge_type, "value", e.edge_type) == "PAYS_OFF"]
    sets_up_edges = [e for e in graph.edges if getattr(e.edge_type, "value", e.edge_type) == "SETS_UP"]

    allocations = []
    # 優先由 PAYS_OFF 邊決定 plant -> payoff
    for e in payoff_edges:
        src = graph.get_node(e.source)
        tgt = graph.get_node(e.target)
        if src and tgt:
            p_ch = src.chapter_window[0]
            r_ch = tgt.chapter_window[1]
            pair = normalize_allocation_pair((p_ch, r_ch), total_chapters)
            if pair:
                allocations.append(pair)

    # 若不足，補入 SETS_UP 邊
    if len(allocations) < len(all_seeds):
        for e in sets_up_edges:
            src = graph.get_node(e.source)
            tgt = graph.get_node(e.target)
            if src and tgt:
                p_ch = src.chapter_window[0]
                r_ch = tgt.chapter_window[1]
                pair = normalize_allocation_pair((p_ch, r_ch), total_chapters)
                if pair and pair not in allocations:
                    allocations.append(pair)

    # 若仍然不足，從節點時間軸順序均勻分配
    all_nodes_sorted = sorted(graph.nodes.values(), key=lambda n: n.chapter_window[0])
    while len(allocations) < len(all_seeds) and len(all_nodes_sorted) >= 2:
        idx_p = len(allocations) % (len(all_nodes_sorted) // 2)
        idx_r = min(len(all_nodes_sorted) - 1, idx_p + len(all_nodes_sorted) // 2)
        pair = normalize_allocation_pair(
            (all_nodes_sorted[idx_p].chapter_window[0], all_nodes_sorted[idx_r].chapter_window[1]),
            total_chapters
        )
        if pair:
            allocations.append(pair)
        else:
            break

    # 2. 提取 turning points：以 CONVERGE, PAYOFF, CHARACTER_SHIFT, ESCALATE 節點為優先
    turning_nodes = [
        n for n in all_nodes_sorted
        if getattr(n.structural_role, "value", n.structural_role) in ("CONVERGE", "PAYOFF", "CHARACTER_SHIFT", "ESCALATE")
    ]
    if not turning_nodes:
        turning_nodes = all_nodes_sorted

    turns_alloc = []
    step = max(1, len(turning_nodes) // max(1, len(all_turns)))
    for i in range(len(all_turns)):
        node_idx = min(len(turning_nodes) - 1, i * step)
        turns_alloc.append(turning_nodes[node_idx].chapter_window[0])

    blueprint = {
        "T": total_chapters,
        "foreshadowing_allocations": allocations[:len(all_seeds)],
        "turning_allocations": turns_alloc[:len(all_turns)],
        "source": "geometry",
    }

    conn = db.get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO foreshadowing_blueprints (novel_id, blueprint_json) VALUES (?, ?)",
            (novel_id, json.dumps(blueprint, ensure_ascii=False)),
        )

    print(f"[DB] Geometry-derived foreshadowing blueprint built successfully for novel {novel_id} (T={total_chapters})")
    return blueprint


# =====================================================================
# 藍圖取得 (優先級: 總監派發 > 幾何導出 > 均勻 fallback)
# =====================================================================

def get_global_foreshadowing_blueprint(novel_id):
    """Fetch the persisted blueprint, recomputing when stale or missing.

    優先級：
    1. 已有幾何圖譜 -> 由圖譜導出（確定性）
    2. 已有持久化藍圖（無論來源） -> 直接讀取
    3. 都沒有 -> fallback 均勻分配（取代舊版隨機）
    """
    from backend import persistence as db

    # 若作品已具有幾何圖譜，優先由幾何圖譜導出藍圖
    if db.has_geometry(novel_id):
        geom_blueprint = build_blueprint_from_geometry(novel_id)
        if geom_blueprint:
            return geom_blueprint

    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview.get("foreshadowing_seeds", [])
    all_turns = worldview.get("key_turning_points", [])

    conn = db.get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT blueprint_json FROM foreshadowing_blueprints WHERE novel_id = ?", (novel_id,)).fetchone()

    if row:
        try:
            blueprint = json.loads(row["blueprint_json"])
            total_chapters = coerce_int(blueprint.get("T"), get_total_chapter_count(db.get_volumes(novel_id)))
            if is_valid_foreshadowing_blueprint(blueprint, len(all_seeds), len(all_turns), total_chapters):
                return blueprint
        except Exception as exc:
            print(f"[WARN] Failed to load/validate global blueprint: {exc}")

    return precompute_global_foreshadowing(novel_id)
