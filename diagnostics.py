# -*- coding: utf-8 -*-
"""
剛性評估與診斷模組 (Rigid Evaluation & Diagnostics Module)
"""
import json

def diagnose_worldview(worldview_text):
    """
    對世界觀內容進行剛性診斷。
    """
    if not worldview_text or not worldview_text.strip() or worldview_text in ("尚無世界觀設定", "（空）", "（尚無世界觀設定）"):
        return "世界觀為空"
    
    try:
        if isinstance(worldview_text, dict):
            parsed = worldview_text
        else:
            parsed = json.loads(worldview_text)
    except Exception:
        try:
            from db import parse_worldview_to_json
            parsed = parse_worldview_to_json(worldview_text)
        except Exception:
            parsed = {}

    if not parsed:
        return "世界觀不完整"

    theme = parsed.get("theme", "")
    main_conflict = parsed.get("main_conflict", "")
    worldview_desc = parsed.get("worldview", "")
    macro_outline = parsed.get("macro_outline", "")
    seeds = parsed.get("foreshadowing_seeds", [])
    turns = parsed.get("key_turning_points", [])

    is_complete = bool(theme and main_conflict and worldview_desc and macro_outline)
    status_str = "世界觀完整" if is_complete else "世界觀不完整"
    return f"{status_str}、伏筆數量{len(seeds)}個、轉折{len(turns)}個"


def diagnose_characters(characters_data):
    """
    對角色聖經進行剛性診斷。
    """
    if not characters_data or not characters_data.strip() or characters_data in ("尚無角色設定", "（空）"):
        return "角色聖經為空"

    try:
        if isinstance(characters_data, dict):
            parsed = characters_data
        else:
            parsed = json.loads(characters_data)
    except Exception:
        return "角色聖經為空"

    chars_list = parsed.get("characters", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
    if not chars_list:
        return "角色有0個，欄位不完整"

    missing_info = []
    for c in chars_list:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "未命名")
        missing_fields = []
        for f in ["personality", "want", "need", "fatal_flaw"]:
            if not c.get(f):
                missing_fields.append(f)
        if missing_fields:
            missing_info.append(name)

    if missing_info:
        return f"角色有{len(chars_list)}個，欄位不完整(缺少：{', '.join(missing_info)} 的關鍵設定)"
    else:
        return f"角色有{len(chars_list)}個，欄位完整"


def diagnose_volumes_and_skeletons(volumes):
    """
    對篇卷骨架進行剛性診斷。
    """
    if not volumes:
        return "第1卷缺漏"

    missing_skeleton_vols = []
    for v in volumes:
        vol_idx = v.get("volume_index")
        skeleton_list = v.get("chapters_outline")
        if not skeleton_list:
            missing_skeleton_vols.append(vol_idx)
        else:
            if isinstance(skeleton_list, str):
                try:
                    skeleton_list = json.loads(skeleton_list)
                except:
                    skeleton_list = []
            if isinstance(skeleton_list, list):
                empty_titles = 0
                for c in skeleton_list:
                    title = c.get("chapter_title") or c.get("brief_title") or c.get("title") or ""
                    if not title or title.strip() == "" or title == "待設定標題":
                        empty_titles += 1
                if empty_titles > len(skeleton_list) * 0.5:
                    missing_skeleton_vols.append(vol_idx)
            else:
                missing_skeleton_vols.append(vol_idx)

    if missing_skeleton_vols:
        return f"第{','.join(map(str, sorted(missing_skeleton_vols)))}卷缺漏"
    
    return f"篇卷骨架完整，共{len(volumes)}卷"


def diagnose_detailed_plot(plot_data, volumes):
    """
    對詳細章節大綱進行剛性診斷。
    """
    if not plot_data:
        return "詳細大綱為空"

    if isinstance(plot_data, str):
        try:
            plot_data = json.loads(plot_data)
        except Exception:
            return "詳細大綱格式錯誤"

    chapters_outlines = plot_data.get("chapters", []) if isinstance(plot_data, dict) else plot_data
    if not chapters_outlines or not isinstance(chapters_outlines, list):
        return "詳細大綱為空"

    normalized_outlines = []
    for idx, ch in enumerate(chapters_outlines):
        if not isinstance(ch, dict):
            continue
        item = dict(ch)
        try:
            raw_idx = item.get("chapter_index") or item.get("chapter") or item.get("chapter_number") or item.get("index") or (idx + 1)
            item["chapter_index"] = int(raw_idx)
        except Exception:
            item["chapter_index"] = idx + 1
        normalized_outlines.append(item)
    normalized_outlines.sort(key=lambda x: x["chapter_index"])

    if not normalized_outlines:
        return "詳細大綱為空"

    from db import _get_clean_chapter_count
    max_expected_ch = sum(_get_clean_chapter_count(v) for v in volumes) if volumes else 0
    if max_expected_ch <= 0:
        max_expected_ch = max(ch["chapter_index"] for ch in normalized_outlines)

    expected_set = set(range(1, max_expected_ch + 1))
    actual_set = set(ch["chapter_index"] for ch in normalized_outlines)
    missing_plot_chapters = sorted(list(expected_set - actual_set))

    if missing_plot_chapters:
        return f"大綱規劃共{len(normalized_outlines)}章，缺漏章節：{missing_plot_chapters[:20]}"
    return f"大綱規劃共{len(normalized_outlines)}章，連續無缺漏"


def diagnose_written_chapters(written_ch, volumes):
    """
    對正文寫作進度進行剛性診斷。
    """
    if not written_ch:
        return "完成0章"

    from db import _get_clean_chapter_count
    expected_chapters_count = sum(_get_clean_chapter_count(v) for v in volumes) if volumes else 0
    if expected_chapters_count <= 0:
        all_indexes = [int(ch["chapter_index"]) for ch in written_ch if ch.get("chapter_index") is not None]
        expected_chapters_count = max(all_indexes) if all_indexes else 1

    valid_written_ch = []
    for ch in written_ch:
        ch_idx = ch.get("chapter_index")
        if ch_idx is not None:
            try:
                ch_idx_int = int(ch_idx)
                if ch_idx_int > expected_chapters_count or ch_idx_int < 1:
                    continue
            except:
                continue
        content = ch.get("content") or ""
        is_placeholder = "保底" in content or "占位" in content or len(content.strip()) < 100
        is_dirty = ch.get("is_dirty") == 1 or ch.get("is_dirty") is True
        if not is_placeholder and not is_dirty:
            valid_written_ch.append(ch)

    if not valid_written_ch:
        return "完成0章"

    written_indexes = sorted([int(ch["chapter_index"]) for ch in valid_written_ch])
    unwritten_chapters = []
    for i in range(1, expected_chapters_count + 1):
        if i not in written_indexes:
            unwritten_chapters.append(i)

    if unwritten_chapters:
        return f"正文已完成{len(valid_written_ch)}章，缺漏章節為第{unwritten_chapters[0]}章"
    else:
        return f"完成{len(valid_written_ch)}章"


def diagnose_all_phases(novel_id):
    """
    一鍵獲取該小說所有階段的剛性診斷。
    """
    import db
    
    wb = db.get_latest_worldbuilding(novel_id)
    wb_content = wb["content"] if wb else ""
    
    char_data = db.get_latest_characters(novel_id)
    characters_json = char_data["json_data"] if char_data else ""
    
    current_stage = db.detect_current_stage(novel_id)
    vols = db.get_volumes(novel_id)
    
    if current_stage == "volumes":
        plot_text = json.dumps({"volumes": vols}, ensure_ascii=False) if vols else ""
    else:
        plot_data = db.get_stitched_plot(novel_id)
        plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else ""
        
    written_ch = db.get_all_chapters_latest(novel_id)
    
    worldview_diag = diagnose_worldview(wb_content)
    characters_diag = diagnose_characters(characters_json)
    
    if not vols:
        plot_diag = "第1卷缺漏"
    elif current_stage in ("volume_skeleton", "volumes"):
        plot_diag = diagnose_volumes_and_skeletons(vols)
    else:
        plot_diag = diagnose_detailed_plot(plot_text, vols)
        
    written_diag = diagnose_written_chapters(written_ch, vols)
    
    return {
        "worldview": worldview_diag,
        "characters": characters_diag,
        "plot": plot_diag,
        "written_chapters": written_diag
    }
