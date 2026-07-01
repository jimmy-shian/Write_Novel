# -*- coding: utf-8 -*-
"""
Validation Module (校驗與結構計算數量層)
負責所有結構性校驗、數量檢查、章節索引計算，以及伏筆/轉折的格式驗證。
agents.py 不應包含任何此類邏輯，一律委由此模組處理。
"""

import json
import re

import db
from config import (
    MIN_FORESHADOWING_SEEDS,
    MIN_KEY_TURNING_POINTS,
    MIN_VOLUME_COUNT,
    MAX_VOLUME_COUNT,
    MIN_CHAPTERS_PER_VOLUME,
    MAX_CHAPTERS_PER_VOLUME,
    VOLUME_SKELETON_BATCH_SIZE,
)


# =============================================================================
# Foreshadowing Text Helpers (伏筆文字輔助工具)
# =============================================================================

def clean_foreshadowing_text(value) -> str:
    """將任意值強制轉換為乾淨的字串，以利欄位內容比較與驗證。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    try:
        return json.dumps(value, ensure_ascii=False).strip()
    except Exception:
        return str(value).strip()


def first_foreshadowing_text(item: dict, keys: tuple) -> str:
    """依序從 item dict 中找出第一個非空欄位的文字值。"""
    if not isinstance(item, dict):
        return ""
    for key in keys:
        text = clean_foreshadowing_text(item.get(key))
        if text:
            return text
    return ""


def foreshadowing_text_list(value) -> list:
    """將任意值轉換為非空字串的列表，用於 related_characters 等陣列欄位。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [text for text in (clean_foreshadowing_text(v) for v in value) if text]
    text = clean_foreshadowing_text(value)
    return [text] if text else []


# =============================================================================
# Foreshadowing Normalization (伏筆/轉折正規化)
# =============================================================================

def normalize_seed_item(item, index: int) -> dict:
    """將 LLM 回傳的伏筆種子物件正規化為標準合約格式。"""
    if not isinstance(item, dict):
        item = {"description": clean_foreshadowing_text(item)}
    return {
        "id": index + 1,
        "name": first_foreshadowing_text(item, ("name", "title", "seed_name")),
        "description": first_foreshadowing_text(item, ("description", "detail", "content", "summary", "seed", "foreshadowing")),
        "setup_hint": first_foreshadowing_text(item, ("setup_hint", "setup", "plant", "plant_hint", "setup_timing")),
        "payoff_hint": first_foreshadowing_text(item, ("payoff_hint", "payoff", "reveal", "resolution", "callback")),
        "related_characters": foreshadowing_text_list(item.get("related_characters") or item.get("characters") or item.get("related_roles")),
        "thematic_link": first_foreshadowing_text(item, ("thematic_link", "theme", "theme_link", "symbolic_meaning")),
    }


def normalize_turning_point_item(item, index: int) -> dict:
    """將 LLM 回傳的轉折點物件正規化為標準合約格式。"""
    if not isinstance(item, dict):
        item = {"description": clean_foreshadowing_text(item)}
    return {
        "id": index + 1,
        "turning_point_name": first_foreshadowing_text(item, ("turning_point_name", "name", "title", "turning_point", "twist")),
        "description": first_foreshadowing_text(item, ("description", "detail", "content", "summary", "event")),
        "trigger_condition": first_foreshadowing_text(item, ("trigger_condition", "trigger", "condition", "cause", "inciting_event")),
        "structural_impact": first_foreshadowing_text(item, ("structural_impact", "global_impact", "impact", "consequence", "plot_impact")),
        "emotional_stakes": first_foreshadowing_text(item, ("emotional_stakes", "stakes", "cost", "emotional_cost")),
        "related_characters": foreshadowing_text_list(item.get("related_characters") or item.get("characters") or item.get("related_roles")),
    }


def normalize_foreshadowing_output(parsed: dict) -> dict:
    """
    將 LLM 回傳的伏筆/轉折 JSON 輸出正規化為嚴格合約格式。
    包含對各種常見 LLM 輸出變體的 salvage 救援邏輯。
    """
    if not isinstance(parsed, dict):
        return {"foreshadowing_seeds": [], "key_turning_points": []}

    seeds = parsed.get("foreshadowing_seeds") or parsed.get("seeds") or parsed.get("foreshadowings") or []
    turns = parsed.get("key_turning_points") or parsed.get("turning_points") or parsed.get("twists") or []

    # Salvage common director-misguided shapes like {"volume_1": [{"seed": ...}]}.
    if not seeds or not turns:
        salvaged_seeds = []
        salvaged_turns = []
        for key, value in parsed.items():
            if key in ("foreshadowing_seeds", "key_turning_points", "seeds", "turning_points", "twists"):
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, dict):
                    continue
                seed_value = item.get("seed") or item.get("foreshadowing") or item.get("setup")
                turn_value = item.get("turning_point") or item.get("twist") or item.get("reveal")
                if seed_value:
                    salvaged_seeds.append(item)
                if turn_value:
                    salvaged_turns.append(item)
        if not seeds:
            seeds = salvaged_seeds
        if not turns:
            turns = salvaged_turns

    if isinstance(seeds, dict):
        seeds = [seeds]
    if isinstance(turns, dict):
        turns = [turns]
    if not isinstance(seeds, list):
        seeds = []
    if not isinstance(turns, list):
        turns = []

    return {
        "foreshadowing_seeds": [normalize_seed_item(item, idx) for idx, item in enumerate(seeds)],
        "key_turning_points": [normalize_turning_point_item(item, idx) for idx, item in enumerate(turns)],
    }


# =============================================================================
# Foreshadowing Validation (伏筆數量與 Schema 校驗)
# =============================================================================

def foreshadowing_quantity_error(seeds, turns) -> str:
    """
    校驗伏筆種子與轉折點的數量是否滿足最低要求。
    回傳非空字串表示有錯誤，空字串表示通過。
    """
    seed_count = len(seeds) if isinstance(seeds, list) else 0
    turn_count = len(turns) if isinstance(turns, list) else 0
    problems = []
    if seed_count < MIN_FORESHADOWING_SEEDS:
        problems.append(f"foreshadowing_seeds 數量不足：需要至少 {MIN_FORESHADOWING_SEEDS} 個，實際 {seed_count} 個")
    if turn_count < MIN_KEY_TURNING_POINTS:
        problems.append(f"key_turning_points 數量不足：需要至少 {MIN_KEY_TURNING_POINTS} 個，實際 {turn_count} 個")
    return "；".join(problems)


def foreshadowing_schema_error(seeds, turns) -> str:
    """
    校驗伏筆種子與轉折點的每個物件是否符合必填欄位 Schema。
    回傳非空字串表示有欄位錯誤（最多回報 12 個），空字串表示通過。
    """
    problems = []
    seed_required = ("name", "description", "setup_hint", "payoff_hint", "thematic_link")
    turn_required = ("turning_point_name", "description", "trigger_condition", "structural_impact", "emotional_stakes")

    for idx, seed in enumerate(seeds if isinstance(seeds, list) else []):
        if not isinstance(seed, dict):
            problems.append(f"foreshadowing_seeds[{idx}] 必須是物件")
            continue
        if seed.get("id") != idx + 1 or not isinstance(seed.get("id"), int):
            problems.append(f"foreshadowing_seeds[{idx}].id 必須是整數 {idx + 1}")
        for field in seed_required:
            if not clean_foreshadowing_text(seed.get(field)):
                problems.append(f"foreshadowing_seeds[{idx}].{field} 不可為空，文字內容不可放錯欄位")
        if not isinstance(seed.get("related_characters"), list):
            problems.append(f"foreshadowing_seeds[{idx}].related_characters 必須是文字陣列")

    for idx, turn in enumerate(turns if isinstance(turns, list) else []):
        if not isinstance(turn, dict):
            problems.append(f"key_turning_points[{idx}] 必須是物件")
            continue
        if turn.get("id") != idx + 1 or not isinstance(turn.get("id"), int):
            problems.append(f"key_turning_points[{idx}].id 必須是整數 {idx + 1}")
        for field in turn_required:
            if not clean_foreshadowing_text(turn.get(field)):
                problems.append(f"key_turning_points[{idx}].{field} 不可為空，文字內容不可放錯欄位")
        if not isinstance(turn.get("related_characters"), list):
            problems.append(f"key_turning_points[{idx}].related_characters 必須是文字陣列")

    if problems:
        shown = "；".join(problems[:12])
        if len(problems) > 12:
            shown += f"；另有 {len(problems) - 12} 個欄位錯誤"
        return shown
    return ""


# =============================================================================
# Volume Plan Validation (篇卷規劃校驗)
# =============================================================================

def volume_plan_validation_error(volumes, mode: str = "generate") -> str:
    """
    校驗篇卷規劃結果的卷數與每卷章節數是否符合限制規範。
    回傳非空字串表示有錯誤，空字串表示通過。
    """
    if not isinstance(volumes, list) or not volumes:
        return "未輸出 volumes 陣列"
    if mode != "patch" and not (MIN_VOLUME_COUNT <= len(volumes) <= MAX_VOLUME_COUNT):
        return f"篇卷數量不合規：需要 {MIN_VOLUME_COUNT}-{MAX_VOLUME_COUNT} 卷，實際 {len(volumes)} 卷"
    bad_counts = []
    for i, vol in enumerate(volumes):
        try:
            ch_count = int(vol.get("chapter_count", 0))
        except Exception:
            ch_count = 0
        if ch_count < MIN_CHAPTERS_PER_VOLUME or ch_count > MAX_CHAPTERS_PER_VOLUME:
            bad_counts.append(f"第 {vol.get('volume_index', i + 1)} 卷 chapter_count={ch_count}")
    if bad_counts:
        return (
            f"每卷章節數不合規：每卷必須 {MIN_CHAPTERS_PER_VOLUME}-{MAX_CHAPTERS_PER_VOLUME} 章；"
            + "、".join(bad_counts[:10])
        )
    return ""


# =============================================================================
# Chapter Index Utilities (章節索引計算工具)
# =============================================================================

def chapter_index_or_none(chapter) -> int | None:
    """從章節物件中安全提取 chapter_index 整數，若無法解析則回傳 None。"""
    if not isinstance(chapter, dict):
        return None
    raw = chapter.get("chapter_index") or chapter.get("chapter") or chapter.get("index")
    try:
        return int(raw)
    except Exception:
        return None


def volume_existing_chapter_indexes(volume: dict, start_ch: int, end_ch: int) -> set:
    """
    回傳指定卷中已存在的章節 index 集合（限定在 start_ch ~ end_ch 範圍內）。
    """
    existing = set()
    chapters = volume.get("chapters_outline") if isinstance(volume, dict) else []
    if isinstance(chapters, str):
        try:
            chapters = json.loads(chapters)
        except Exception:
            chapters = []
    if isinstance(chapters, list):
        for ch in chapters:
            idx = chapter_index_or_none(ch)
            if idx is not None and start_ch <= idx <= end_ch:
                existing.add(idx)
    return existing


def volume_missing_chapter_indexes(volumes: list, volume_index: int) -> list:
    """
    計算指定卷中尚未生成骨架的缺失章節 index 列表（已排序）。
    """
    volume = next((v for v in volumes if int(v.get("volume_index", 0)) == int(volume_index)), None)
    if not volume:
        return []
    start_ch, end_ch = db.get_volume_chapter_range(volumes, volume_index)
    expected = set(range(start_ch, end_ch + 1))
    existing = volume_existing_chapter_indexes(volume, start_ch, end_ch)
    return sorted(expected - existing)


def parse_requested_chapter_indexes(text: str, start_ch: int, end_ch: int) -> list:
    """
    從使用者提示文字中解析出指定的章節 index 列表（限定在 start_ch ~ end_ch 範圍內）。
    支援「第 X 至第 Y 章」、「chapters X-Y」等格式，以及單章「第 X 章」。
    """
    if not text:
        return []
    content = str(text)
    ranges = []
    patterns = [
        r"(?:第\s*)?(\d+)\s*(?:至|到|[-~～—–])\s*(?:第\s*)?(\d+)\s*章?",
        r"chapters?\s*(\d+)\s*(?:to|-)\s*(\d+)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, content, flags=re.IGNORECASE):
            a, b = int(m.group(1)), int(m.group(2))
            lo, hi = sorted((a, b))
            ranges.extend(range(max(start_ch, lo), min(end_ch, hi) + 1))
    singles = []
    for m in re.finditer(r"第\s*(\d+)\s*章", content):
        value = int(m.group(1))
        if start_ch <= value <= end_ch:
            singles.append(value)
    return sorted(set(ranges + singles))


def split_consecutive_batches(indexes: list, batch_size: int = VOLUME_SKELETON_BATCH_SIZE) -> list:
    """
    將章節 index 列表依連續性切分為批次（每批最多 batch_size 個）。
    用於骨架批次補全邏輯，避免單次生成過多章節。
    """
    if not indexes:
        return []
    batches = []
    current = []
    previous = None
    for idx in sorted(indexes):
        if previous is None or (idx == previous + 1 and len(current) < batch_size):
            current.append(idx)
        else:
            batches.append(current)
            current = [idx]
        previous = idx
    if current:
        batches.append(current)
    return batches


def extract_chapters_in_range(parsed_skeleton, expected_indexes: list) -> list:
    """
    從 LLM 回傳的骨架解析結果中提取符合預期章節 index 的章節物件列表，
    去除重複，並確保 chapter_index 欄位被正確賦值。
    """
    if isinstance(parsed_skeleton, dict):
        chapters = parsed_skeleton.get("chapters_skeleton", []) or parsed_skeleton.get("chapters", [])
    elif isinstance(parsed_skeleton, list):
        chapters = parsed_skeleton
    else:
        chapters = []
    expected = set(expected_indexes)
    cleaned = []
    seen = set()
    for ch in chapters if isinstance(chapters, list) else []:
        idx = chapter_index_or_none(ch)
        if idx in expected and idx not in seen:
            ch["chapter_index"] = idx
            cleaned.append(ch)
            seen.add(idx)
    return cleaned


# =============================================================================
# Worldview JSON Extraction (世界觀 JSON 安全提取)
# =============================================================================

def extract_worldview_dict_preserving(content) -> dict | None:
    """
    從世界觀內容（字串或已解析的 dict）中安全地提取 JSON dict。
    若內容本身就是 dict 則直接複製回傳；若是字串則嘗試各種解析策略。
    回傳 None 表示無法安全提取（不應覆蓋既有資料）。
    """
    if isinstance(content, dict):
        return dict(content)
    if not isinstance(content, str) or not content.strip():
        return {}

    import re as _re
    text = _re.sub(r"<think>[\s\S]*?</think>", "", content, flags=_re.IGNORECASE).strip()
    candidates = []
    candidates.extend(match.group(1) for match in _re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=_re.IGNORECASE))
    candidates.append(text)
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and first < last:
        candidates.append(text[first:last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None
