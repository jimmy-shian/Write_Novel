# -*- coding: utf-8 -*-
"""
剛性評估與診斷模組 (Rigid Evaluation & Diagnostics Module)
"""
import json

from backend.config import (
    MIN_FORESHADOWING_SEEDS,
    MIN_KEY_TURNING_POINTS,
    MIN_VOLUME_COUNT,
    MAX_VOLUME_COUNT,
    MIN_CHAPTERS_PER_VOLUME,
    MAX_CHAPTERS_PER_VOLUME,
)
from backend.utils import normalize_outlines
from backend.schemas.agent_json import CHARACTER_BASIC_FIELDS


WORLDVIEW_SEED_REFERENCE_KEYS = {
    "act",
    "stage",
    "wave",
    "phase",
    "suggested_act",
    "suggested_stage",
    "chapter",
    "chapter_index",
    "volume",
    "volume_index",
}


def _format_worldview_seed_for_report(seed):
    """Keep seed meaning, but strip draft placement metadata from validation text."""
    if isinstance(seed, dict):
        filtered = {k: v for k, v in seed.items() if k not in WORLDVIEW_SEED_REFERENCE_KEYS}
        stripped = {k: seed.get(k) for k in seed.keys() if k in WORLDVIEW_SEED_REFERENCE_KEYS}
        text = json.dumps(filtered or seed, ensure_ascii=False)
        if stripped:
            return f"{text}（已忽略草稿定位欄位：{', '.join(str(k) for k in stripped.keys())}）"
        return text
    return str(seed)


def _is_primary_protagonist(character, index):
    if index == 0:
        return True
    role = str(character.get("role", "")).lower()
    tags = character.get("tags", []) or character.get("labels", [])
    if isinstance(tags, str):
        tags = [tags]
    tag_text = " ".join(str(tag).lower() for tag in tags)
    return any(mark in role or mark in tag_text for mark in ("主角", "protagonist", "男主", "女主"))


def _character_missing_fields(character):
    core_check_fields = [f for f in CHARACTER_BASIC_FIELDS if f not in ("name", "role", "entry_phase", "relationships")]
    return [field for field in core_check_fields if not character.get(field)]


def _append_active_chapter_task_report(report_lines, novel_id, active_chapter_index):
    if not active_chapter_index:
        return

    try:
        from backend import db
        target_idx = int(active_chapter_index)
        plot_data = db.get_stitched_plot(novel_id)
        outlines = normalize_outlines(plot_data or {})
        current_outline = next((ch for ch in outlines if ch["chapter_index"] == target_idx), None)
        allocated = current_outline.get("allocated_tasks", {}) if isinstance(current_outline, dict) else {}
        if not isinstance(allocated, dict):
            allocated = {}

        plants = allocated.get("foreshadowing_plants") or []
        payoffs = allocated.get("foreshadowing_payoffs") or []
        turns = allocated.get("turning_points") or []
        has_tasks = bool(plants or payoffs or turns)

        report_lines.append("")
        report_lines.append("【6. 當前章節伏筆任務來源判定】")
        report_lines.append(f"  - 當前審查章節：第 {target_idx} 章")
        report_lines.append("  - 判定規則：章節是否需要埋設/回收伏筆，以卷生成後演算法寫入章節大綱的 allocated_tasks 為準。")
        report_lines.append("  - 注意：世界觀 foreshadowing_seeds 內的 act/stage/chapter/volume 等欄位，只是 LLM 初稿定位參考，不是本章硬性任務。")
        if not has_tasks:
            report_lines.append(f"  - 第 {target_idx} 章演算法指定伏筆/轉折任務：無。總監不得因世界觀 seed 的 act/stage metadata 要求本章補埋伏筆。")
            return

        report_lines.append(f"  - 第 {target_idx} 章演算法指定任務：有")
        report_lines.append(f"    * foreshadowing_plants：{json.dumps(plants, ensure_ascii=False)}")
        report_lines.append(f"    * foreshadowing_payoffs：{json.dumps(payoffs, ensure_ascii=False)}")
        report_lines.append(f"    * turning_points：{json.dumps(turns, ensure_ascii=False)}")
    except Exception as exc:
        report_lines.append("")
        report_lines.append(f"【6. 當前章節伏筆任務來源判定】⚠️ 無法解析：{exc}")


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
            from backend.db import parse_worldview_to_json
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

    protagonist_missing = []
    for idx, c in enumerate(chars_list):
        if not isinstance(c, dict):
            continue
        if not _is_primary_protagonist(c, idx):
            continue
        missing_fields = _character_missing_fields(c)
        if missing_fields:
            protagonist_missing.append(f"{c.get('name', '未命名')} 缺少 {', '.join(missing_fields)}")

    if protagonist_missing:
        return f"角色有{len(chars_list)}個；主角欄位可補：{'; '.join(protagonist_missing)}；配角欄位缺失不列為阻斷"
    return f"角色有{len(chars_list)}個；主角核心欄位足夠，配角欄位缺失不列為阻斷"


def diagnose_volumes_and_skeletons(volumes):
    """
    對篇卷骨架進行結構與進度診斷。
    """
    if not volumes:
        return "第1卷缺漏"
    if len(volumes) < MIN_VOLUME_COUNT or len(volumes) > MAX_VOLUME_COUNT:
        return f"篇卷數量不合規，共{len(volumes)}卷；需為{MIN_VOLUME_COUNT}-{MAX_VOLUME_COUNT}卷"

    bad_chapter_counts = []
    for v in volumes:
        try:
            ch_count = int(v.get("chapter_count", 0))
        except Exception:
            ch_count = 0
        if ch_count < MIN_CHAPTERS_PER_VOLUME or ch_count > MAX_CHAPTERS_PER_VOLUME:
            bad_chapter_counts.append(f"卷{v.get('volume_index')}={ch_count}章")
    if bad_chapter_counts:
        return f"篇卷章節數不合規；每卷需{MIN_CHAPTERS_PER_VOLUME}-{MAX_CHAPTERS_PER_VOLUME}章；{', '.join(bad_chapter_counts[:10])}"

    incomplete_skeleton_vols = []
    for v in volumes:
        vol_idx = v.get("volume_index")
        skeleton_list = v.get("chapters_outline")
        try:
            start_ch, end_ch = db.get_volume_chapter_range(volumes, int(vol_idx))
        except Exception:
            start_ch, end_ch = 1, int(v.get("chapter_count") or 50)
        if not skeleton_list:
            incomplete_skeleton_vols.append(f"卷{vol_idx}全卷未生成")
        else:
            if isinstance(skeleton_list, str):
                try:
                    skeleton_list = json.loads(skeleton_list)
                except:
                    skeleton_list = []
            if isinstance(skeleton_list, list):
                empty_titles = 0
                for c in skeleton_list:
                    title = c.get("chapter_title") or c.get("title") or ""
                    if not title or title.strip() == "" or title == "待設定標題":
                        empty_titles += 1
                if empty_titles > len(skeleton_list) * 0.5:
                    incomplete_skeleton_vols.append(f"卷{vol_idx}骨架品質不足")
                else:
                    expected = set(range(start_ch, end_ch + 1))
                    actual = {
                        int(c.get("chapter_index"))
                        for c in skeleton_list
                        if isinstance(c, dict) and c.get("chapter_index") is not None
                    }
                    missing = sorted(expected - actual)
                    if missing:
                        incomplete_skeleton_vols.append(f"卷{vol_idx}缺{len(missing)}章")
            else:
                incomplete_skeleton_vols.append(f"卷{vol_idx}骨架格式錯誤")

    if incomplete_skeleton_vols:
        return "篇卷骨架待補：" + "；".join(incomplete_skeleton_vols[:12])
    
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

    from backend.db import _get_clean_chapter_count
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

    from backend.db import _get_clean_chapter_count
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
    from backend import db
    
    wb = db.get_latest_worldbuilding(novel_id)
    wb_content = wb["content"] if wb else ""
    
    char_data = db.get_latest_characters(novel_id)
    characters_json = char_data["json_data"] if char_data else ""
    
    current_stage = detect_current_stage(novel_id)
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


def detect_current_stage(novel_id):
    """
    根據資料庫進度動態偵測當前創作階段 (worldview -> foreshadowing -> characters -> volumes -> volume_skeleton -> writer -> editor)
    """
    from backend import db
    wb = db.get_latest_worldbuilding(novel_id)
    if not wb or not wb["content"].strip():
        return "worldview"
        
    # 剛性檢查世界觀完整性
    worldview_diag = diagnose_worldview(wb["content"])
    if "世界觀不完整" in worldview_diag:
        return "worldview"
        
    # 偵測是否已生成伏筆與轉折
    try:
        parsed_wb = db.parse_worldview_to_json(wb["content"])
        seeds = parsed_wb.get("foreshadowing_seeds", [])
        turns = parsed_wb.get("key_turning_points", [])
        if (not seeds or not turns or
            len(seeds) < MIN_FORESHADOWING_SEEDS or
            len(turns) < MIN_KEY_TURNING_POINTS):
            return "foreshadowing"
    except Exception as e:
        print(f"[STAGE DETECT ERROR] Failed to parse worldview JSON: {e}")
        return "foreshadowing"

    char = db.get_latest_characters(novel_id)
    if not char or not char["json_data"] or char["json_data"] == "{'characters': []}":
        return "characters"
        
    # 剛性檢查角色聖經完整性
    characters_diag = diagnose_characters(char["json_data"])
    if "角色聖經為空" in characters_diag or "角色有0個" in characters_diag:
        return "characters"

    vols = db.get_volumes(novel_id)
    if not vols:
        return "volumes"
        
    # 如果有任何一卷尚未規劃簡易骨架大綱，則為 volume_skeleton 階段
    has_all_skeletons = True
    for v in vols:
        skeleton_list = v.get("chapters_outline")
        if not skeleton_list:
            has_all_skeletons = False
            break
        # 檢查是否超過50%為 "待設定標題" 佔位符
        empty_titles = 0
        for c in skeleton_list:
            title = c.get("chapter_title") or c.get("title") or ""
            if not title or title.strip() == "" or title == "待設定標題":
                empty_titles += 1
        if empty_titles > len(skeleton_list) * 0.5:
            has_all_skeletons = False
            break
            
    if not has_all_skeletons:
        return "volume_skeleton"
        
    total_planned = sum(db._get_clean_chapter_count(v) for v in vols)
    if total_planned <= 0:
        total_planned = 1
        
    chapters = db.get_all_chapters_latest(novel_id)
    if len(chapters) < total_planned:
        return "writer"
        
    return "editor"


def generate_validation_report(novel_id, current_stage=None, active_volume_index=None, active_chapter_index=None):
    """
    用 Python 硬碼（Hardcoded）計算的客觀指標報告，避免 AI 通靈。
    進行嚴格的資料完整性與邏輯一致性檢查，並產出易於被 AI 總監解析的剛性指標報告。
    """
    from backend import db
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("🤖 系統底層剛性資料結構與進度校驗報告 (VALIDATION REPORT)")
    report_lines.append("=" * 60)
    
    # 讀取小說基本資料
    novel = db.get_novel(novel_id)
    if not novel:
        return "❌ 錯誤：找不到該小說資料。"
        
    title = novel.get("title", "未命名")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設")
    
    # 1. 創作需求與世界觀
    wb = db.get_latest_worldbuilding(novel_id)
    wb_exists = wb is not None and len(wb.get("content", "").strip()) > 0
    
    report_lines.append("【1. 世界觀與核心設定層】")
    if not wb_exists:
        report_lines.append("  - 狀態：❌ 未完成 (世界觀為空)")
    else:
        report_lines.append("  - 狀態：✅ 已建立")
        try:
            parsed_wb = db.parse_worldview_to_json(wb["content"])
            report_lines.append(f"  - 核心主題 (theme)：{parsed_wb.get('theme', '未設定')[:100]}...")
            report_lines.append(f"  - 核心衝突 (main_conflict)：{parsed_wb.get('main_conflict', '未設定')[:100]}...")
            multi_act = parsed_wb.get('multi_act_structure', [])
            char_plan = parsed_wb.get('progressive_character_plan', [])
            report_lines.append(f"  - 多幕結構 (multi_act_structure)：共 {len(multi_act)} 幕")
            report_lines.append(f"  - 角色漸進規劃 (progressive_character_plan)：共 {len(char_plan)} 波")
        except Exception as e:
            report_lines.append(f"  - 狀態：⚠️ 世界觀非標準 JSON 格式：{e}")
    report_lines.append("")

    # 1.5. 伏筆與轉折編織層
    report_lines.append("【1.5. 伏筆與轉折編織層】")
    if not wb_exists:
        report_lines.append("  - 狀態：❌ 未完成 (世界觀為空，無法編織伏筆)")
    else:
        try:
            parsed_wb = db.parse_worldview_to_json(wb["content"])
            seeds = parsed_wb.get("foreshadowing_seeds", [])
            turns = parsed_wb.get("key_turning_points", [])
            seeds_count = len(seeds) if isinstance(seeds, list) else 0
            turns_count = len(turns) if isinstance(turns, list) else 0
            seeds_ok = seeds_count >= MIN_FORESHADOWING_SEEDS
            turns_ok = turns_count >= MIN_KEY_TURNING_POINTS
            
            if seeds_ok and turns_ok:
                report_lines.append("  - 狀態：✅ 已建立")
            else:
                report_lines.append(f"  - 狀態：❌ 未完成 (伏筆種子數量：{seeds_count}/{MIN_FORESHADOWING_SEEDS}，關鍵轉折點數量：{turns_count}/{MIN_KEY_TURNING_POINTS})")
                
            report_lines.append(f"  - 伏筆種子 (foreshadowing_seeds)：共 {seeds_count} 個")
            if current_stage in ("worldview", "foreshadowing", None):
                for i, s in enumerate(seeds):
                    report_lines.append(f"    * [Seed-{i+1}] {_format_worldview_seed_for_report(s)}")
            else:
                report_lines.append("    * （明細已省略，僅 worldview/foreshadowing 階段展開逐條）")
                
            report_lines.append(f"  - 關鍵轉折點 (key_turning_points)：共 {turns_count} 個")
            if current_stage in ("worldview", "foreshadowing", None):
                for j, t in enumerate(turns):
                    if isinstance(t, dict):
                        tp_name = t.get("turning_point_name") or t.get("name") or "未命名轉折"
                        report_lines.append(f"    * [Turn-{j+1}] {tp_name}")
                    else:
                        report_lines.append(f"    * [Turn-{j+1}] {t}")
            else:
                report_lines.append("    * （明細已省略，僅 worldview/foreshadowing 階段展開逐條）")
        except Exception as e:
            report_lines.append(f"  - 狀態：⚠️ 無法解析伏筆與轉折：{e}")
    report_lines.append("")
    
    # 2. 角色聖經
    char = db.get_latest_characters(novel_id)
    char_exists = char is not None and char.get("json_data") and char["json_data"] != "{'characters': []}"
    
    report_lines.append("【2. 角色聖經層】")
    if not char_exists:
        report_lines.append("  - 狀態：❌ 未完成 (角色聖經為空)")
    else:
        try:
            parsed_char = char.get("parsed_data") or json.loads(char["json_data"])
            chars_list = parsed_char.get("characters", [])
            report_lines.append(f"  - 登記角色總數：共 {len(chars_list)} 位")
            report_lines.append("  - 檢查規則：只標示主角/第一主角的欄位缺失；配角或臨時角色欄位缺失不作為流程阻斷。")
            if current_stage in ("writer", "editor"):
                report_lines.append("  - 當前為正文/編輯階段：角色可補欄位不得觸發 INCREMENTAL_MODIFY_CHARACTER；若正文品質通過，應繼續 editor 或下一章 writer。")
            ignored_count = 0
            for idx, c in enumerate(chars_list):
                name = c.get("name", "未命名")
                role = c.get("role", "未設定")
                if not _is_primary_protagonist(c, idx):
                    ignored_count += 1
                    # check minor fields
                    missing_minor = [f for f in ["name", "role", "entry_phase"] if not c.get(f)]
                    if missing_minor:
                        report_lines.append(f"    * 配角 [{name}] ({role}) ⚠️ [欄位缺失，非阻斷]：缺少 {', '.join(missing_minor)}")
                    continue
                missing_fields = _character_missing_fields(c)
                if missing_fields:
                    report_lines.append(f"    * 主角 [{name}] ({role}) ⚠️ [可補欄位，非阻斷]：缺少 {', '.join(missing_fields)}")
                else:
                    report_lines.append(f"    * 主角 [{name}] ({role}) ✅ 核心欄位足夠")
            if ignored_count:
                report_lines.append(f"    * 其餘 {ignored_count} 位配角/支線角色：不檢查非必要欄位，不作為流程阻斷。")

            # 世界觀勢力與登場計畫比對
            try:
                wb = db.get_latest_worldbuilding(novel_id)
                if wb:
                    parsed_wb = db.parse_worldview_to_json(wb["content"])
                    w_factions = parsed_wb.get("factions", [])
                    if isinstance(w_factions, list) and w_factions:
                        char_factions = set()
                        for char_item in chars_list:
                            for key in ("faction", "affiliation"):
                                val = char_item.get(key)
                                if val:
                                    char_factions.add(str(val).strip().lower())
                        
                        missing_wf = []
                        for wf in w_factions:
                            wf_name = wf.get("name") if isinstance(wf, dict) else str(wf)
                            if wf_name:
                                wf_clean = wf_name.strip().lower()
                                if not any(wf_clean in cf or cf in wf_clean for cf in char_factions):
                                    missing_wf.append(wf_name)
                        if missing_wf:
                            report_lines.append(f"    * ⚠️ 勢力覆蓋警示：世界觀勢力 {', '.join(missing_wf)} 尚無對應設定之角色歸屬。")
            except Exception as e:
                pass
        except Exception as e:
            report_lines.append("  - 狀態：⚠️ 角色聖經非標準 JSON 格式，無法解析。")
    report_lines.append("")
    
    # 3. 篇卷規劃與骨架大綱
    vols = db.get_volumes(novel_id)
    report_lines.append("【3. 篇卷規劃與骨架大綱層】")
    missing_skeleton_vols = []  # 完全缺失或骨架不可用的卷索引
    incomplete_skeleton_items = []  # 所有未完整卷，包含部分缺章
    if not vols:
        report_lines.append("  - 狀態：❌ 未完成 (尚未規劃篇卷)")
    else:
        report_lines.append(f"  - 篇卷規劃總數：共 {len(vols)} 卷")
        if len(vols) < MIN_VOLUME_COUNT or len(vols) > MAX_VOLUME_COUNT:
            report_lines.append(f"  - 🚫 [篇卷數量不合規] 需要 {MIN_VOLUME_COUNT}-{MAX_VOLUME_COUNT} 卷，目前 {len(vols)} 卷。")
        total_planned_chapters = sum(db._get_clean_chapter_count(v) for v in vols)
        report_lines.append(f"  - 章節骨架總規劃數：共 {total_planned_chapters} 章")
        
        # 檢查每卷的骨架大綱
        for v in vols:
            vol_idx = v["volume_index"]
            vol_title = v["title"]
            ch_count = db._get_clean_chapter_count(v)
            if ch_count < MIN_CHAPTERS_PER_VOLUME or ch_count > MAX_CHAPTERS_PER_VOLUME:
                report_lines.append(f"    * 卷 {vol_idx}《{vol_title}》：🚫 [每卷章節數不合規] 需要 {MIN_CHAPTERS_PER_VOLUME}-{MAX_CHAPTERS_PER_VOLUME} 章，目前 {ch_count} 章")
            start_ch, end_ch = db.get_volume_chapter_range(vols, vol_idx)
            
            skeleton_list = v.get("chapters_outline")
            if not skeleton_list:
                report_lines.append(f"    * 卷 {vol_idx}《{vol_title}》：❌ [骨架缺失] (尚未規劃簡易章節骨架大綱)")
                missing_skeleton_vols.append(vol_idx)
                incomplete_skeleton_items.append({
                    "volume_index": vol_idx,
                    "title": vol_title,
                    "status": "全卷未生成",
                    "missing_count": ch_count,
                    "missing_sample": [start_ch, end_ch] if start_ch != end_ch else [start_ch],
                })
            else:
                if isinstance(skeleton_list, str):
                    try:
                        skeleton_list = json.loads(skeleton_list)
                    except:
                        skeleton_list = []
                # 檢查是否含有有效的骨架標題
                empty_titles = 0
                for c in skeleton_list:
                    title = c.get("chapter_title") or c.get("title") or ""
                    if not title or title.strip() == "" or title == "待設定標題":
                        empty_titles += 1
                
                if empty_titles > len(skeleton_list) * 0.5:
                    report_lines.append(f"    * 卷 {vol_idx}《{vol_title}》：❌ [骨架未生成] (超過50%章節標題為待設定)")
                    missing_skeleton_vols.append(vol_idx)
                    incomplete_skeleton_items.append({
                        "volume_index": vol_idx,
                        "title": vol_title,
                        "status": "骨架品質不足",
                        "missing_count": ch_count,
                        "missing_sample": [start_ch, end_ch] if start_ch != end_ch else [start_ch],
                    })
                else:
                    report_lines.append(f"    * 卷 {vol_idx}《{vol_title}》：✅ 骨架已建立 (第 {start_ch} 章至第 {end_ch} 章，共 {len(skeleton_list)} 章)")
                # 剛性檢查章節序號覆蓋度
                expected_indexes = set(range(start_ch, end_ch + 1))
                actual_indexes = set()
                for c in skeleton_list:
                    c_idx = c.get("chapter_index")
                    if c_idx is not None:
                        actual_indexes.add(int(c_idx))
                        
                missing_indexes = expected_indexes - actual_indexes
                duplicate_indexes = [x for x in actual_indexes if list(map(lambda y: int(y.get("chapter_index", 0)), skeleton_list)).count(x) > 1]
                
                if missing_indexes:
                    missing_sorted = sorted(list(missing_indexes))
                    report_lines.append(f"      - ⚠️ [大綱骨架待補] 缺少 {len(missing_sorted)} 章；樣本：{missing_sorted[:20]}{'...' if len(missing_sorted) > 20 else ''}")
                    incomplete_skeleton_items.append({
                        "volume_index": vol_idx,
                        "title": vol_title,
                        "status": "部分缺章",
                        "missing_count": len(missing_sorted),
                        "missing_sample": missing_sorted[:20],
                    })
                if duplicate_indexes:
                    report_lines.append(f"      - ⚠️ [大綱骨架重複] 重複章節：{duplicate_indexes}")

        # 檢查篇卷骨架中是否有未建卡命名角色
        try:
            char_data = db.get_latest_characters(novel_id)
            if char_data:
                from backend.generation.agent_runners import _character_alias_set, _active_character_names_from_outline, _is_generic_active_character_name
                bible_aliases = _character_alias_set(char_data["json_data"])
                missing_chars_in_skeleton = []
                for v in vols:
                    vol_idx = v["volume_index"]
                    skeleton_list = v.get("chapters_outline") or []
                    if isinstance(skeleton_list, str):
                        try:
                            skeleton_list = json.loads(skeleton_list)
                        except:
                            skeleton_list = []
                    if isinstance(skeleton_list, list):
                        for ch in skeleton_list:
                            ch_idx = ch.get("chapter_index") or ch.get("chapter") or ch.get("id") or 1
                            for name in _active_character_names_from_outline(ch):
                                if not _is_generic_active_character_name(name) and name not in bible_aliases:
                                    if not any(alias and (alias in name or name in alias) for alias in bible_aliases):
                                        missing_chars_in_skeleton.append((vol_idx, ch_idx, name))
                if missing_chars_in_skeleton:
                    report_lines.append("  - ⚠️ 偵測到篇卷骨架中使用了角色 Bible 中不存在的命名角色：")
                    from collections import defaultdict
                    missing_by_name = defaultdict(list)
                    for vol_idx, ch_idx, name in missing_chars_in_skeleton:
                        missing_by_name[name].append(f"卷 {vol_idx} 第 {ch_idx} 章")
                    for name, refs in missing_by_name.items():
                        report_lines.append(f"    * 角色 [{name}] 於 {', '.join(refs[:5])} 出現，但未建卡")
        except Exception as e:
            print(f"[REPORT ERROR] Failed to check missing characters in skeletons: {e}")
        
        if incomplete_skeleton_items:
            incomplete_skeleton_items.sort(key=lambda item: int(item["volume_index"]))
            next_item = incomplete_skeleton_items[0]
            compact_queue = [
                f"卷{item['volume_index']}({item['status']}，缺{item['missing_count']}章)"
                for item in incomplete_skeleton_items[:12]
            ]
            report_lines.append(f"  - ⚠️ [骨架待生成佇列] {'；'.join(compact_queue)}")
            report_lines.append(
                "  - [下一步建議] 這是流程進度提示，不是上一輪內容品質不合格。"
                f"請優先處理最早未完整卷：卷 {next_item['volume_index']}《{next_item['title']}》。"
                "若系統規則要求整卷生成，請一次生成該卷完整章節骨架；不要因後續卷缺失而跳過較早未完整卷。"
            )
        else:
            report_lines.append(f"  - ✅ [全卷骨架完整性檢查] 所有 {len(vols)} 卷骨架均已建立，允許進入後續階段。")
    report_lines.append("")
    
    # 4. 詳細章節大綱 (Stitched Plot)
    plot_data = db.get_stitched_plot(novel_id)
    chapters_outlines = plot_data.get("chapters", []) if plot_data else []
    
    # 收集所有章節大綱
    detailed_count = 0
    if chapters_outlines:
        for ch in chapters_outlines:
            evs = ch.get("events") or ch.get("scenes")
            if evs and isinstance(evs, list) and len(evs) > 0:
                detailed_count += 1
                
    max_expected_ch = sum(db._get_clean_chapter_count(v) for v in vols) if vols else 0
    if max_expected_ch <= 0:
        max_expected_ch = 1
        
    report_lines.append("【4. 章節大綱層】")
    if chapters_outlines:
        report_lines.append(f"  - 狀態：✅ 已完成 (共 {len(chapters_outlines)} 章)")
        if vols:
            expected_set = set(range(1, max_expected_ch + 1))
            actual_set = set()
            for ch in chapters_outlines:
                idx = ch.get("chapter_index")
                if idx is not None:
                    actual_set.add(int(idx))
            missing_plot_chapters = sorted(list(expected_set - actual_set))
            if missing_plot_chapters:
                report_lines.append(f"  - ⚠️ 章節序號不連續：缺少 {len(missing_plot_chapters)} 章")
            else:
                report_lines.append(f"  - 章節序號連續性檢查：✅ 連續無缺漏")
    else:
        report_lines.append("  - 狀態：⚠️ 尚未生成章節大綱")
    report_lines.append("")
    
    # 5. 正文寫作 (Prose Chapters)
    written_ch = db.get_all_chapters_latest(novel_id)
    report_lines.append("【5. 正文寫作與完稿層】")
    if vols:
        expected_chapters_count = sum(db._get_clean_chapter_count(v) for v in vols)
    else:
        all_indexes = [int(ch["chapter_index"]) for ch in written_ch if ch.get("chapter_index") is not None]
        expected_chapters_count = max(all_indexes) if all_indexes else 1
 
    # 剛性篩選已完成且非髒資料/保底/占位符，且在當前篇卷規劃章節範圍內的章節
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
        report_lines.append("  - 狀態：❌ 未完成 (尚未寫作任何有效正文章節)")
 
    else:
        report_lines.append(f"  - 正文已寫作有效章節數：共 {len(valid_written_ch)} 章 (總紀錄數: {len(written_ch)} 章)")
        
        # 連續性檢查與缺漏檢測
        written_indexes = sorted([int(ch["chapter_index"]) for ch in valid_written_ch])
        
        # 找出所有未寫的章節（在總規劃範圍內）
        unwritten_chapters = []
        for i in range(1, expected_chapters_count + 1):
            if i not in written_indexes:
                unwritten_chapters.append(i)
                
        # 計算進度百分比
        progress_pct = (len(valid_written_ch) / expected_chapters_count) * 100 if expected_chapters_count > 0 else 0
        report_lines.append(f"  - 全書專案正文完成進度：{progress_pct:.2f}% ({len(valid_written_ch)}/{expected_chapters_count} 章)")
        
        if unwritten_chapters:
            earliest_missing_chapter = min(unwritten_chapters)
            report_lines.append(f"  - 🚫 [進度缺漏 / 斷檔] 檢測到最早缺漏/未寫作的章節為：第 {earliest_missing_chapter} 章")
            report_lines.append(f"    * 以下章節已被跳過/尚未寫作：{unwritten_chapters}")
        else:
            report_lines.append(f"  - 正文章節序號連續性檢查 (1 至 {expected_chapters_count} 章，由系統 Python 邏輯外部計算)：✅ 正文順序推進，無中斷斷檔且已全部完工。")
            
    if current_stage in ("writer", "editor") or active_chapter_index is not None:
        _append_active_chapter_task_report(report_lines, novel_id, active_chapter_index)

    report_lines.append("=" * 60)
    return "\n".join(report_lines)

