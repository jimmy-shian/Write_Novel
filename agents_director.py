# -*- coding: utf-8 -*-
import json
import re
import os
import sys
import db
from db import (
    get_latest_worldbuilding,
    get_latest_characters,
    get_stitched_plot,
    get_all_chapters_latest,
    get_volumes,
    get_total_chapter_count,
    get_chapter_volume_index,
    get_volume_chapter_range,
    save_chat_message
)

def parse_json_safely(text, default=None):
    """
    安全解析 JSON。支援剝除 markdown code blocks。
    """
    if not text:
        return default
    if isinstance(text, (dict, list)):
        return text
    try:
        text_str = str(text).strip()
        if "```" in text_str:
            blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text_str, re.DOTALL | re.IGNORECASE)
            if blocks:
                text_str = blocks[0].strip()
        return json.loads(text_str)
    except:
        return default

def _looks_like_placeholder_chapter(chapter):
    """
    檢查章節大綱是否像是由硬編碼保底/佔位符生成的空殼內容。
    """
    if not isinstance(chapter, dict):
        return True

    text_parts = [
        chapter.get("title", ""),
        chapter.get("summary", ""),
        chapter.get("purpose", ""),
        chapter.get("cliffhanger", ""),
        chapter.get("scene", ""),
    ]
    for event in chapter.get("events", []) or []:
        if isinstance(event, dict):
            text_parts.extend([event.get("scene", ""), event.get("action", ""), event.get("consequence", "")])
        else:
            text_parts.append(str(event))

    combined = "\n".join(str(part) for part in text_parts if part is not None)
    banned_fragments = [
        "保底",
        "占位",
        "佔位",
        "placeholder",
        "命運波折之章",
        "推進核心衝突",
        "推動大綱情節發展",
        "主角面臨新考驗",
        "留下懸念引發期待",
    ]
    return any(fragment.lower() in combined.lower() for fragment in banned_fragments)

def infer_review_scope(novel_id, current_stage, user_prompt):
    """
    智慧判定當前審查的範圍（Volume Index 或 Chapter Index）。
    分析使用者 Prompt、當前階段及資料庫中的髒卷(is_dirty)標記。
    """
    scope_volume_index = None
    scope_chapter_index = None
    
    # 1. 從 prompt 中提取特定的卷/章
    if user_prompt:
        user_prompt_str = str(user_prompt)
        vol_match = re.search(r'(?:第|Vol\.?\s*)(\d+)\s*(?:卷|volume)', user_prompt_str, re.IGNORECASE)
        if vol_match:
            scope_volume_index = int(vol_match.group(1))
        else:
            # 中文數字匹配
            cn_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            vol_cn_match = re.search(r'第\s*([一二三四五六七八九十]+)\s*卷', user_prompt_str)
            if vol_cn_match:
                cn_val = vol_cn_match.group(1).strip()
                if cn_val in cn_nums:
                    scope_volume_index = cn_nums[cn_val]
                    
        ch_match = re.search(r'(?:第|Ch\.?\s*)(\d+)\s*(?:章|chapter)', user_prompt_str, re.IGNORECASE)
        if ch_match:
            scope_chapter_index = int(ch_match.group(1))
            
    # 2. 如果沒匹配到，但目前是局部階段，且資料庫中有髒卷(is_dirty=1)，則鎖定髒卷
    if scope_volume_index is None:
        try:
            vols = get_volumes(novel_id)
            dirty_vols = [int(vol.get("volume_index", 0)) for vol in vols if int(vol.get("is_dirty", 0)) == 1]
            if dirty_vols:
                scope_volume_index = dirty_vols[0]
        except Exception:
            pass
            
    return scope_volume_index, scope_chapter_index

def verify_novel_integrity(novel_id, context, current_stage=None, scope_volume_index=None, scope_chapter_index=None):
    """
    重構版：支援 Scope-Aware 局部範圍感知校驗。
    - 支援 scope_volume_index: 若指定，僅校驗此卷內部的結構與時序，不要求全域勢力或種子 100% 被使用。
    - 支援階梯式校驗結果：致命阻斷級 (Blockers) 與 改善優化級 (🟡 Warnings)。
    """
    # 💡 判斷是否為大綱生成之前的早期設定階段
    is_early_stage = (current_stage in ["init", "worldview", "worldview_review", "worldview_go_back", "characters", "characters_review", "characters_go_back"])
    
    if is_early_stage:
        validation_report_str = """【底層結構完整性與情節邏輯校驗報告（當前階段不適用）】
1. 📂 設定結構完整性：
   - 多幕式結構 (multi_act_structure) 是否有合法內容：[設定階段，待大綱完成後校驗]
   - 角色漸進登場規劃策略 (progressive_character_plan) 是否有合法內容：[設定階段，待大綱完成後校驗]
   
2. 📊 卷數與章節數量檢驗：
   - 篇卷規劃數 (volumes)：[設定階段，不阻斷]
   - 章節序號連續性：[設定階段，不阻斷]
   
3. 🌍 世界觀設定使用率檢驗：
   - 陣營/勢力設定使用率：[設定階段，不阻斷]
   - 世界觀伏筆種子使用率：[設定階段，不阻斷]
   - 世界觀關鍵轉折點使用率：[設定階段，不阻斷]
   
4. 🔑 章節內容 - 伏筆時序與收束銜接度檢驗：
   - 大綱伏筆統計：[設定階段，不阻斷]
 
💡 總監提示：目前處於初始或設定規劃階段，尚未開始大綱拆解。校驗報告所有品質紅線「不適用」於此階段。請做出 CONTINUE 正常向下個階段推進。
"""
        return validation_report_str
    
    # 💡 判斷是否為宏觀骨架階段（Stage 2 & Stage 3）
    is_macro_skeleton_stage = (current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align", "volume_skeleton", "foreshadowing_orchestration"])
    
    if is_macro_skeleton_stage:
        vols = get_volumes(novel_id)
        volumes_count = len(vols)
        
        # 計算全書總章節數
        total_chapters = 0
        for vol in vols:
            try:
                vol_chapters = int(vol.get("chapter_count", 0))
                total_chapters += vol_chapters
            except:
                pass
        
        # 獲取已生成的骨架章節
        plot_json_for_scan = parse_json_safely(context.get("plot", ""), default={})
        plot_chapters_for_scan = plot_json_for_scan.get("chapters", []) if isinstance(plot_json_for_scan, dict) else []
        skeleton_chapter_count = len(plot_chapters_for_scan)
        
        missing_skeleton_volumes = []
        for vol in vols:
            vol_idx = int(vol.get("volume_index", 0))
            chapters_outline = vol.get("chapters_outline") or vol.get("chapters_skeleton") or []
            if not chapters_outline or chapters_outline == "[]" or chapters_outline == "{}":
                missing_skeleton_volumes.append(vol_idx)
        
        # 局部骨架審查：如果只關注特定卷，我們只看該卷骨架是否缺失
        if scope_volume_index is not None:
            skeleton_missing_warning = ""
            if scope_volume_index in missing_skeleton_volumes:
                skeleton_missing_warning = f"\n🔴【篇卷骨架缺失警告】：當前審查的第 {scope_volume_index} 卷章節骨架為空，請先生成該卷骨架！"
            
            validation_report_str = f"""【底層結構完整性校驗報告 — 🌍 宏觀骨架局部審查模式 (第 {scope_volume_index} 卷)】
1. 📊 當前卷骨架規模：
   - 審查範圍：第 {scope_volume_index} 卷
   - 全書已規劃篇卷：{volumes_count} 卷
   - 全書當前骨架章節：{skeleton_chapter_count} 章 / 規劃總章節：{total_chapters} 章
   - 指標評定：{"🟢 骨架狀態合格" if scope_volume_index not in missing_skeleton_volumes else "🔴 當前卷骨架缺失"}{skeleton_missing_warning}
   
2. 🎯 局部審查放行指引：
   - 忽略其他非審查卷的骨架缺失警告（因為當前為局部增量開發）。
   - 若當前第 {scope_volume_index} 卷骨架正常，必須做出 CONTINUE 正常放行！
"""
            return validation_report_str
        else:
            skeleton_missing_warning = ""
            if missing_skeleton_volumes:
                skeleton_missing_warning = f"\n🔴【篇卷骨架缺失警告】：以下篇卷的章節骨架為空：第 {missing_skeleton_volumes} 卷"
            
            validation_report_str = f"""【底層結構完整性校驗報告 — 🌍 宏觀骨架全域審查模式】
1. 📊 全書宏觀規模覆蓋率：
   - 目前已規劃篇卷數：{volumes_count} 卷
   - 目前骨架總章節數：{skeleton_chapter_count} 章
   - 全書規劃總章節數：{total_chapters} 章
   - 指標評定：{"🟢 骨架規模已達到長篇標準" if skeleton_chapter_count >= 500 else "🟡 骨架規模尚未覆蓋全書，待後續滚動生成"}{skeleton_missing_warning}
 
⚠️ 宏觀放行紅線：
- 若存在🔴【篇卷骨架缺失警告】，總監必須下達 `CONTINUE` 並指定 `volume_skeleton` 進行缺失篇卷的骨架生成。
- 忽略微觀的「伏筆憑空回收」警告（因此時尚未展開微觀內容）。
"""
            return validation_report_str

    # ----------------------------------------------------
    # 微觀校驗流程 (微觀大綱/正文寫作階段)
    # ----------------------------------------------------
    # 讀取世界觀
    wb_data = get_latest_worldbuilding(novel_id)
    wb_json = parse_json_safely(wb_data["content"]) if wb_data else {}
    if not isinstance(wb_json, dict):
        wb_json = {}
        
    three_act = wb_json.get("multi_act_structure", [])
    has_three_act = False
    if isinstance(three_act, list):
        has_three_act = any(isinstance(item, dict) and item.get("content", "").strip() != "" for item in three_act)
        
    progressive_plan = wb_json.get("progressive_character_plan", [])
    has_progressive_plan = False
    if isinstance(progressive_plan, list):
        has_progressive_plan = any(isinstance(item, dict) and item.get("content", "").strip() != "" for item in progressive_plan)
        
    vols = get_volumes(novel_id)
    volumes_count = len(vols)
    
    # 讀取當前大綱章節
    plot_json_all = parse_json_safely(context.get("plot", ""), default={})
    plot_chapters_all = plot_json_all.get("chapters", []) if isinstance(plot_json_all, dict) else []
    
    # 如果指定了 scope_volume_index，則將掃描的章節過濾為僅限當前卷
    plot_chapters_for_scan = []
    if scope_volume_index is not None:
        for ch in plot_chapters_all:
            try:
                ch_idx = int(ch.get("chapter_index", 0))
                if ch_idx > 0:
                    c_vol = get_chapter_volume_index(vols, ch_idx)
                    if c_vol == scope_volume_index:
                        plot_chapters_for_scan.append(ch)
            except:
                pass
    else:
        plot_chapters_for_scan = plot_chapters_all

    # 1. 📂 卷數量與章節數量檢驗
    chapter_indices = []
    placeholder_outline_indices = []
    for ch in plot_chapters_for_scan:
        if isinstance(ch, dict):
            try:
                ch_idx = int(ch.get("chapter_index", 0))
                if ch_idx > 0:
                    chapter_indices.append(ch_idx)
                    if _looks_like_placeholder_chapter(ch):
                        placeholder_outline_indices.append(ch_idx)
            except:
                pass
                
    max_chapter_idx = max(chapter_indices) if chapter_indices else 0
    min_chapter_idx = min(chapter_indices) if chapter_indices else 0
    expected_vols_by_outline = get_chapter_volume_index(vols, max_chapter_idx) if max_chapter_idx > 0 else 0
    
    # Gaps check (局部範圍感知)
    gaps = []
    if scope_volume_index is not None:
        start_ch, end_ch = get_volume_chapter_range(vols, scope_volume_index)
        # 僅校驗此卷內部的已生成區段是否有空隙
        if chapter_indices:
            actual_min = min(chapter_indices)
            actual_max = max(chapter_indices)
            for i in range(actual_min, actual_max + 1):
                if i not in chapter_indices:
                    gaps.append(i)
    else:
        for i in range(1, max_chapter_idx + 1):
            if i not in chapter_indices:
                gaps.append(i)
                
    vol_status_str = f"篇卷規劃數 (volumes)：共 {volumes_count} 卷"
    if expected_vols_by_outline > volumes_count:
        vol_status_str += f" ⚠️【🔴 卷數不足警告】：目前大綱已規劃到第 {max_chapter_idx} 章，對應至第 {expected_vols_by_outline} 卷，但當前資料庫中僅有 {volumes_count} 卷規劃設定！"
    elif expected_vols_by_outline > 0 and volumes_count > expected_vols_by_outline:
        vol_status_str += f" (大綱目前規劃到第 {expected_vols_by_outline} 卷，餘 {volumes_count - expected_vols_by_outline} 卷待後續滾動生成)"
        
    if scope_volume_index is not None:
        vol_status_str += f" | 當前局部審查：第 {scope_volume_index} 卷 (第 {start_ch}~{end_ch} 章)"
        
    gap_status_str = "章節序號連續性：完整連續"
    if gaps:
        gap_status_str = f"⚠️【🔴 章節序號不連續】：缺失的章節序號為 {gaps}"
        
    # 2. 🌍 世界觀設定使用率檢驗
    # Factions check
    all_factions = []
    for vol in vols:
        factions_field = vol.get("factions") or []
        if isinstance(factions_field, str):
            try:
                f_list = json.loads(factions_field)
            except:
                f_list = [factions_field]
        else:
            f_list = factions_field
            
        if isinstance(f_list, list):
            for f in f_list:
                if isinstance(f, str) and f.strip() and f.strip() != "全域陣列":
                    all_factions.append(f.strip())
    all_factions = list(set(all_factions))
    
    used_factions = []
    unused_factions = []
    for faction in all_factions:
        found = False
        for ch in plot_chapters_for_scan:
            ch_str = json.dumps(ch, ensure_ascii=False)
            if faction in ch_str:
                found = True
                break
        if found:
            used_factions.append(faction)
        else:
            unused_factions.append(faction)
            
    # Seeds check
    seeds = wb_json.get("foreshadowing_seeds", []) or []
    used_seeds = []
    unused_seeds = []
    for idx, seed in enumerate(seeds):
        seed_id_variants = [f"Seed-{idx+1}", f"Seed {idx+1}", f"seed-{idx+1}", f"seed {idx+1}"]
        found = False
        for ch in plot_chapters_for_scan:
            ch_str = json.dumps(ch, ensure_ascii=False).lower()
            if any(var.lower() in ch_str for var in seed_id_variants):
                found = True
                break
            
            clean_seed = seed
            for prefix in [f"Seed-{idx+1}:", f"Seed-{idx+1}", f"Seed {idx+1}:", f"Seed {idx+1}"]:
                if clean_seed.startswith(prefix):
                    clean_seed = clean_seed[len(prefix):].strip()
            
            if len(clean_seed) > 6:
                phrases = [p.strip() for p in re.split(r'[，。：；！？\s\[\]]', clean_seed) if len(p.strip()) >= 4]
                for phrase in phrases:
                    if phrase.lower() in ch_str:
                        found = True
                        break
            if found:
                break
        if found:
            used_seeds.append(seed)
        else:
            unused_seeds.append(seed)
            
    # Key Turning Points check
    tps = wb_json.get("key_turning_points", []) or []
    used_tps = []
    unused_tps = []
    for idx, tp in enumerate(tps):
        tp_variants = [f"TurningPoint-{idx+1}", f"TurningPoint {idx+1}", f"turningpoint-{idx+1}", f"turningpoint {idx+1}", f"轉折點-{idx+1}", f"轉折點 {idx+1}"]
        found = False
        for ch in plot_chapters_for_scan:
            ch_str = json.dumps(ch, ensure_ascii=False).lower()
            if any(var.lower() in ch_str for var in tp_variants):
                found = True
                break
                
            clean_tp = tp
            for prefix in [f"TurningPoint-{idx+1}:", f"TurningPoint-{idx+1}", f"轉折點-{idx+1}:", f"轉折點-{idx+1}"]:
                if clean_tp.startswith(prefix):
                    clean_tp = clean_tp[len(prefix):].strip()
            
            if len(clean_tp) > 6:
                phrases = [p.strip() for p in re.split(r'[，。：；！？\s\[\]]', clean_tp) if len(p.strip()) >= 4]
                for phrase in phrases:
                    if phrase.lower() in ch_str:
                        found = True
                        break
            if found:
                break
        if found:
            used_tps.append(tp)
        else:
            unused_tps.append(tp)
            
    faction_usage_rate = (len(used_factions) / len(all_factions) * 100) if all_factions else 0.0
    seed_usage_rate = (len(used_seeds) / len(seeds) * 100) if seeds else 100.0
    tp_usage_rate = (len(used_tps) / len(tps) * 100) if tps else 100.0
    
    # 💡 局部模式下，不強求全域設定使用率為 100%，將未使用警告降級為資訊，防範紅色警告 🔴 誤報
    if scope_volume_index is not None:
        faction_status = f"陣營/勢力登場數：{len(used_factions)} 個 (此卷局部登場率不要求 100%)"
        seed_status = f"世界觀伏筆登場數：{len(used_seeds)} 個 (此卷局部登場率不要求 100%)"
        tp_status = f"世界觀轉折點登場數：{len(used_tps)} 個 (此卷局部登場率不要求 100%)"
    else:
        faction_status = f"陣營/勢力設定全域使用率：{len(used_factions)}/{len(all_factions)} ({faction_usage_rate:.1f}%)"
        if unused_factions:
            faction_status += f" — ⚠️ 未在此大綱登場的勢力：{unused_factions}"
            
        seed_status = f"世界觀伏筆種子使用率：{len(used_seeds)}/{len(seeds)} ({seed_usage_rate:.1f}%)"
        if unused_seeds:
            unused_show = [s[:15] + "..." if len(s) > 15 else s for s in unused_seeds[:5]]
            seed_status += f" — ⚠️ 未使用的伏筆種子前五項：{unused_show}"
            
        tp_status = f"世界觀關鍵轉折點使用率：{len(used_tps)}/{len(tps)} ({tp_usage_rate:.1f}%)"
        if unused_tps:
            unused_tp_show = [t[:15] + "..." if len(t) > 15 else t for t in unused_tps[:5]]
            tp_status += f" — ⚠️ 未使用的轉折點前五項：{unused_tp_show}"

    # 3. 🔑 章節內容伏筆收束銜接檢驗 (含跨卷感知優化)
    plants_map = {}
    payoffs_map = {}
    
    for ch in plot_chapters_for_scan:
        try:
            ch_idx = int(ch.get("chapter_index", 0))
        except:
            continue
        if ch_idx <= 0:
            continue
            
        plants = ch.get("foreshadowing_plant", []) or []
        payoffs = ch.get("foreshadowing_payoff", []) or []
        if isinstance(plants, str):
            plants = [plants]
        if isinstance(payoffs, str):
            payoffs = [payoffs]
            
        for p in plants:
            if not isinstance(p, str):
                continue
            matches = re.findall(r'(?:[Ss]eed|伏筆)\s*[-\s]?\s*(\d+)', p)
            for m in matches:
                plants_map.setdefault(int(m), []).append(ch_idx)
                
        for py in payoffs:
            if not isinstance(py, str):
                continue
            matches = re.findall(r'(?:[Ss]eed|伏筆)\s*[-\s]?\s*(\d+)', py)
            for m in matches:
                payoffs_map.setdefault(int(m), []).append(ch_idx)

    # 💡 建立全書的埋設對照表，用於局部模式判定「是否為真正的 baseless payoff」
    plants_map_all = {}
    for ch in plot_chapters_all:
        try:
            ch_idx = int(ch.get("chapter_index", 0))
        except:
            continue
        plants = ch.get("foreshadowing_plant", []) or []
        if isinstance(plants, str):
            plants = [plants]
        for p in plants:
            if not isinstance(p, str):
                continue
            matches = re.findall(r'(?:[Ss]eed|伏筆)\s*[-\s]?\s*(\d+)', p)
            for m in matches:
                plants_map_all.setdefault(int(m), []).append(ch_idx)
                
    dangling_plants = []
    deep_foreshadowings = []
    baseless_payoffs = []
    out_of_order_seeds = []
    
    total_chapters = get_total_chapter_count(vols)
    is_all_chapters_completed = (max_chapter_idx >= total_chapters) if total_chapters > 0 else False
    
    # 伏筆未回收判定
    for s_id, p_chaps in plants_map.items():
        if s_id not in payoffs_map:
            # 局部模式下，這只代表「跨卷伏筆（深遠鋪陳）」，絕非 🔴 dangling plant 致命阻斷
            if scope_volume_index is not None or not is_all_chapters_completed:
                deep_foreshadowings.append(f"[Seed-{s_id}] (埋設於第 {p_chaps} 章，將於後續篇卷回收)")
            else:
                dangling_plants.append(f"[Seed-{s_id}] (埋設於第 {p_chaps} 章)")
        else:
            earliest_plant = min(p_chaps)
            earliest_payoff = min(payoffs_map[s_id])
            if earliest_payoff <= earliest_plant:
                out_of_order_seeds.append(f"[Seed-{s_id}] (第 {earliest_payoff} 章回收，卻在第 {earliest_plant} 章才埋設)")
                
    # 伏筆憑空回收判定
    for s_id, py_chaps in payoffs_map.items():
        has_plant = False
        if s_id in plants_map:
            has_plant = True
        else:
            # 💡 [智慧跨卷查找]：若當前卷沒埋，但全書 master 大綱的前面章節有埋，則為合法回收，不視為 Baseless Payoff!
            earliest_payoff = min(py_chaps)
            global_plants = plants_map_all.get(s_id, [])
            if any(p_idx < earliest_payoff for p_idx in global_plants):
                has_plant = True
                
        if not has_plant:
            baseless_payoffs.append(f"[Seed-{s_id}] (第 {py_chaps} 章回收)")
            
    fores_plant_total = len(plants_map)
    fores_payoff_total = len(payoffs_map)
    
    fores_status_str = f"本期大綱伏筆統計：共埋設了 {fores_plant_total} 組伏筆種子，已回收 {fores_payoff_total} 組伏筆"
    
    foreshadowing_violations = []
    if dangling_plants:
        foreshadowing_violations.append(f"  🔴【伏筆未回收 (Dangling Plants)】：{dangling_plants} (全書大綱已完結，但有伏筆被遺忘)")
    if baseless_payoffs:
        foreshadowing_violations.append(f"  🔴【伏筆憑空回收 (Baseless Payoffs)】：{baseless_payoffs} (未在前文進行任何 Seed 埋設，卻突然回收)")
    if out_of_order_seeds:
        foreshadowing_violations.append(f"  🔴【伏筆時序顛倒 (Out of Order)】：{out_of_order_seeds} (回收章節序號小於/等於埋設章節序號)")
    if deep_foreshadowings:
        foreshadowing_violations.append(f"  🟡【跨卷/長線伏筆暫未收束（正常大長篇現象）】：{deep_foreshadowings}")
        
    fores_alignment_str = "章節伏筆時序與收束銜接度：局部伏筆完全符合時序且無遺漏" if not foreshadowing_violations else "\n".join(foreshadowing_violations)
    
    # 彙總判定是否存在 🔴 致命阻斷標記
    has_blocker_warnings = ("🔴" in gap_status_str or "🔴" in fores_alignment_str or len(placeholder_outline_indices) > 0)
    
    placeholder_chapter_warning = "無"
    if placeholder_outline_indices:
        placeholder_chapter_warning = f"⚠️【🔴 偵測到佔位/空殼章節】：第 {placeholder_outline_indices} 章 (這些章節描述為空，或包含硬編碼保底標題)。你【必須】決策 `GO_BACK_TO_SKELETON_EXPANSION` 退回補齊骨架！"
        has_blocker_warnings = True

    # --- ✍️ 當前已生成之第 N 章寫作連貫性深度校驗資料與階梯修補 ---
    coherence_report_str = ""
    # 智慧獲取當前寫作章節 N
    N = 0
    if scope_chapter_index is not None:
        N = scope_chapter_index
    else:
        from db import get_all_chapters_latest
        try:
            written_chaps = get_all_chapters_latest(novel_id)
            if written_chaps:
                N = max(int(c.get("chapter_index", 0)) for c in written_chaps)
        except Exception:
            pass

    if current_stage in ["writer", "writer_review"] and N > 0:
        from db import get_chat_memory, get_latest_chapter
        
        prev_prose = "（無前一章正文，本章為第一章）"
        if N > 1:
            prev_chap = get_latest_chapter(novel_id, N - 1)
            if prev_chap:
                prev_prose = prev_chap.get("content", "")
                
        curr_prose = ""
        curr_chap = get_latest_chapter(novel_id, N)
        if curr_chap:
            curr_prose = curr_chap.get("content", "")
            
        outlines_in_range = []
        for c_outline in plot_chapters_all:
            try:
                c_idx = int(c_outline.get("chapter_index", 0))
                if N - 3 <= c_idx <= N + 3:
                    title = c_outline.get("title", "")
                    desc = c_outline.get("description", "")
                    plant = c_outline.get("foreshadowing_plant", [])
                    payoff = c_outline.get("foreshadowing_payoff", [])
                    tasks = c_outline.get("allocated_tasks", {})
                    
                    outline_str = f"第 {c_idx} 章 【{title}】\n  • 章節大綱：{desc}\n"
                    if plant:
                        outline_str += f"  • 埋設伏筆：{plant}\n"
                    if payoff:
                        outline_str += f"  • 回收伏筆：{payoff}\n"
                    if tasks:
                        outline_str += f"  • 分配任務：{tasks}\n"
                    outlines_in_range.append(outline_str)
            except:
                pass
                
        # 載入歷史評估記錄判定修補階梯
        history = get_chat_memory(novel_id, limit=30, message_type='director')
        has_add_bridge = False
        has_modify_current = False
        for msg in reversed(history):
            content = msg.get("content", "")
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    action_data = json.loads(json_match.group(0))
                    act = action_data.get("action")
                    ch_idx = action_data.get("chapter_index")
                    if int(ch_idx) == N:
                        if act == "ADD_BRIDGE_CONTENT":
                            has_add_bridge = True
                        elif act == "MODIFY_CURRENT_CHAPTER":
                            has_modify_current = True
                except:
                    pass
                    
        if not has_add_bridge:
            recommended_hint = "【第一級修補建議】檢測到第 N 章與前文不連貫或大綱有偏差。請總監做出 `ADD_BRIDGE_CONTENT` 決策（在當前章前後插入橋接大綱骨架，並生成大綱與正文，然後才行推進）。"
        elif not has_modify_current:
            recommended_hint = "【第二級修補建議】檢測到已進行過一次橋接，但仍有不協調。請總監做出 `MODIFY_CURRENT_CHAPTER` 決策（精修微調當前第 N 章正文內容）。"
        else:
            recommended_hint = "【第三級修補建議】多次修補仍不符。請總監做出 `GO_BACK_TO_PREVIOUS_STEP` 決策（徹底刪除 N-3 至 N+3 大綱與正文，回退重新編寫）。"

        coherence_report_str = f"""
5. ✍️ 【當前已生成之第 {N} 章寫作連貫性深度校驗資料】：
   - 【第 {N-1} 章已寫正文完整內容 (N-1 Chapter Prose)】：
{prev_prose[:1200]}... (略以節省 Token)
   
   - 【第 {N-3} 章至第 {N+3} 章之詳細大綱 (Chapter Outlines N-3 to N+3)】：
{"".join(outlines_in_range)}
   
   - 【當前第 {N} 章待校驗正文完整內容 (Current Chapter {N} Prose)】：
{curr_prose[:1500]}... (略)

   - 【階梯修補引導與歷史審核判定】：
     • 曾嘗試 ADD_BRIDGE_CONTENT: {"是" if has_add_bridge else "否"}
     • 曾嘗試 MODIFY_CURRENT_CHAPTER: {"是" if has_modify_current else "否"}
     • 🔴 目前品質判定：若寫作內容與大綱、世界觀設定不符，或人物性格突變、情節不連貫，你【必須】依序執行漸進式階梯修補：
       👉 {recommended_hint}
"""

    validation_report_str = f"""【底層結構完整性與情節邏輯校驗報告】
1. 📂 設定結構完整性：
   - 多幕式結構 (multi_act_structure) 是否有合法內容：{ "是" if has_three_act else "否 (異常！此欄位目前為空，前端無法渲染)" }
   - 角色漸進登場規劃策略 (progressive_character_plan) 是否有合法內容：{ "是" if has_progressive_plan else "否 (異常！此欄位目前為空，前端無法渲染)" }
   
2. 📊 卷數與章節數量檢驗：
   - {vol_status_str}
   - {gap_status_str}
   - 偵測到的佔位/保底大綱章節：{placeholder_chapter_warning}
   
3. 🌍 世界觀設定使用率檢驗（局部自適應）：
   - {faction_status}
   - {seed_status}
   - {tp_status}
   
4. 🔑 章節內容 - 伏筆時序與收束銜接度檢驗：
   - {fores_status_str}
   - {fores_alignment_str}
{coherence_report_str}
⚠️ 總監審查放行红線：
- 如果出現章節序號不連續、缺失、佔位空殼，你【必須】決策 `GO_BACK_TO_SKELETON_EXPANSION` 退回骨架增生階段重新編寫！
- 如果上述報告中存在「【紅色致命阻斷級】」標記（如連續章節序號斷裂、佔位空殼章節、時序顛倒、寫作連貫性深度校驗失敗或全域完結大綱伏筆遺忘），代表大綱或正文邏輯存在嚴重缺陷，你【必須】決策對應的駁回/修補動作（如 `ADD_BRIDGE_CONTENT`、`MODIFY_CURRENT_CHAPTER` 或 `GO_BACK_TO_PREVIOUS_STEP` 等）！
- 如果上述報告中僅存在「🟡【跨卷/長線伏筆暫未收束】」或「世界觀登場率不為 100%」（因為當前是局部增量生成），這是大長篇小說正常的藝術性鋪陳，**你絕對不應該為此擋下大綱或要求退回重寫**。請直接放行 `CONTINUE` 或 `WRITE_ALL_CHAPTERS` 進度！
"""
    return validation_report_str

def pre_check_next_agent(novel_id, current_stage):
    """
    在總監決定前，透過程式對當前資料狀態進行基本健康度判斷，並識別即將準備呼叫的下一個 Agent。
    """
    from db import get_latest_worldbuilding, get_latest_characters, get_stitched_plot, get_all_chapters_latest
    
    wb = get_latest_worldbuilding(novel_id)
    has_wb = wb and len(wb.get("content", "").strip()) > 100
    
    char = get_latest_characters(novel_id)
    has_char = char and len(char.get("json_data", "").strip()) > 100
    
    plot_data = get_stitched_plot(novel_id)
    has_plot = plot_data and len(plot_data) > 0
    
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id) if hasattr(db, "get_all_volume_skeletons") else []
    has_skeletons = skeletons and len(skeletons) > 0
    
    has_foreshadowing_alloc = False
    if has_plot:
        for ch in plot_data.get("chapters", []):
            alloc = ch.get("allocated_tasks", {}) or {}
            if (alloc.get("foreshadowing_plants") or alloc.get("foreshadowing_payoffs") or alloc.get("turning_points")):
                has_foreshadowing_alloc = True
                break
                
    chapters = get_all_chapters_latest(novel_id)
    written_count = len(chapters)
    
    suggested_agent = ""
    status_summary = ""
    suggestion = ""
    
    if current_stage == "init":
        if not has_wb:
            suggested_agent = "世界觀架構師 (Story Architect Agent)"
            status_summary = "世界觀目前為空白。"
            suggestion = "請做出 CONTINUE 正常流向 worldview 的決策，以便開始規劃底層世界觀。"
        elif not has_char:
            suggested_agent = "角色設計師 (Character Designer Agent)"
            status_summary = "世界觀已就緒，但尚未生成角色聖經。"
            suggestion = "請做出 CONTINUE 進度到 characters 的決策，以便生成角色設計。"
        elif not has_skeletons:
            suggested_agent = "篇卷骨架規劃師 (Volume Skeleton Planner)"
            status_summary = "世界觀與角色已就緒，但尚未拆解篇卷章節骨架。"
            suggestion = "請做出 CONTINUE 進度到 volume_skeleton 的決策，以便為各卷章生成簡易大綱骨架。"
        elif not has_foreshadowing_alloc:
            suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
            status_summary = "簡易大綱已生成，但尚未進行全局伏筆編織與對齊。"
            suggestion = "請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策，將世界觀伏筆與轉折均勻分配到各章。"
        else:
            suggested_agent = "大綱規劃師 (Plot Planner Agent)"
            status_summary = "全書骨架與伏筆分配皆已就緒。"
            suggestion = "🚨 【當前重點】：請審查當前骨架與伏筆分佈演進。若無誤請 CONTINUE 進度到 plot 進行微觀大綱詳細展開。"
            
    elif current_stage in ["worldview", "worldview_review", "worldview_go_back"]:
        suggested_agent = "角色設計師 (Character Designer Agent)"
        if has_wb:
            status_summary = f"世界觀設定已就緒（字數：{len(wb.get('content', ''))} 字）。"
            suggestion = "若評估世界觀架構完整，請做出 CONTINUE 進度到 characters 的決策。"
        else:
            status_summary = "⚠️ 警報！資料庫中未檢測到有效世界觀設定！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='worldview' 重新規劃世界觀！"
            
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        suggested_agent = "篇卷骨架規劃師 (Volume Skeleton Planner)"
        if not has_wb:
            status_summary = "⚠️ 警報！缺失上游世界觀資料！"
            suggestion = "必須決策 GO_BACK_TO_WORLDVIEW 退回補全世界觀。"
        elif not has_char:
            status_summary = "⚠️ 警報！資料庫中角色聖經資料為空！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='characters' 重新生成角色聖經！"
        else:
            status_summary = f"角色聖經已就緒（資料長度：{len(char.get('json_data', ''))} 字符）。"
            suggestion = "若角色設計滿意，請做出 CONTINUE 進度到 volume_skeleton 的決策。"
            
    elif current_stage in ["volume_skeleton", "skeleton_review"]:
        suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
        if not has_skeletons:
            status_summary = "⚠️ 警報！尚未生成 any 篇卷大綱骨架！"
            suggestion = "必須決策 AUTO_REGENERATE target='volume_skeleton' 重新生成各卷簡易章大綱。"
        else:
            status_summary = f"簡易大綱骨架已生成，共 {len(skeletons)} 章。"
            suggestion = "若簡易大綱骨架結構完整，請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策。"
            
    elif current_stage in ["foreshadowing_orchestration", "foreshadowing_review", "foreshadowing_align"]:
        suggested_agent = "大綱規劃師 (Plot Planner Agent)"
        if not has_foreshadowing_alloc:
            status_summary = "⚠️ 警告：資料庫尚未包含任何伏筆或轉折的分配描述！"
            suggestion = "不可進行下一步！請決策 AUTO_REGENERATE target='foreshadowing_orchestration' 重新進行伏筆編織對齊。"
        else:
            status_summary = "全局伏筆與關鍵轉折分配任務已完成並順利儲存。"
            suggestion = "若伏筆分配佈局滿意，請做出 CONTINUE 進度到 plot 的決策，以啟動 Stage 4：微觀大綱詳細展開。"
            
    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent)"
        if not has_wb or not has_char:
            status_summary = "⚠️ 警報！上游世界觀或角色資料不完整！"
            suggestion = "請做出 GO_BACK_TO_WORLDVIEW 或 GO_BACK_TO_CHARACTERS 決策退回修正。"
        elif not has_plot:
            status_summary = "⚠️ 警報！資料庫中尚未生成章節大綱！"
            suggestion = "不可寫作！必須決策 AUTO_REGENERATE target='plot' 重新生成大綱。"
        else:
            try:
                vol_count = len(set(c.get("volume_index", 1) for c in plot_data))
                status_summary = f"大綱已生成，共 {vol_count} 卷，{len(plot_data)} 章。"
            except Exception:
                status_summary = "大綱已生成但解析異常。"
            suggestion = "請仔細審核下方的情節完整性校驗報告。若無致命紅線 [紅色] 警告，請決策 WRITE_ALL_CHAPTERS 開始寫作或 CONTINUE 正常往下推進！"
            
    elif current_stage in ["writer", "writer_review"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent) / 全書完成"
        status_summary = f"正文已撰寫 {written_count} 章節。"
        suggestion = "若已寫正文無明顯漏洞且完成度高，可決策 CONTINUE 或 FINISH；若個別章節存在嚴重問題，可決策 AUTO_REGENERATE target='writer' 並指定卷章號重寫該章。"
        
    else:
        suggested_agent = "系統流程控制"
        status_summary = "未知或自訂階段。"
        suggestion = "請根據專案現狀做出最優下一步決策。"
        
    return f"""【程式基本判斷結果（總監決策前預檢）】：
- 🎯 當前階段：{current_stage}
- 準備呼叫的下一個 Agent：{suggested_agent}
- 📊 資料庫當前設定狀態：{status_summary}
- 💡 程式建議總監動作：{suggestion}"""

def get_simplified_director_prompt(current_stage, has_wb_and_char_at_init=False):
    """
    根據總監評估的當前階段，動態生成極簡特化的 system prompt。
    重構版：引入「階梯式審查指引」與「跨卷伏筆放行紅線」，確保局部生成流暢。
    """
    common_header = """你是 AI 小說創作系統的【創意總監】，負責把控整個小說創作管道的品質與流程。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含評估回應和JSON指令區塊）。

## 重要：你的回應將被系統自動解析並執行
- 你的回應末尾必須包含一個 JSON 格式的【執行指令區塊】
- 系統會解析你的 JSON 指令來決定下一步動作
- 你必須做出【果斷決策】，不可含糊

## 當前任務評估
你目前正在評估「{current_stage}」階段完成後的成果，判斷下一步動作。

## 當前已完成的工作成果（精簡 Context 視圖）
【世界觀】：{worldbuilding}
【角色 Bible】：{characters}
【章節大綱】：{plot}
【已寫作章節】：{written_chapters}
"""

    common_footer = """
## 可點擊可用的 ACTION 指令（嚴格選擇一個）

| ACTION | 用途 | 必要欄位 |
|--------|------|----------|
| `CONTINUE` | 當前階段品質合格，繼續下一階段 | `target`（下一階段名稱） |
| `AUTO_REGENERATE` | 當前階段品質不足，需要重新生成 | `target`（要重跑的階段）, `hint` (要修改的細項描述), `volume_index`（若與特定卷相關，填入整數；否則填 null）, `chapter_index`（若與特定章相關，填入整數；否則填 null） |
| `GO_BACK_TO_WORLDVIEW` | 發現世界觀需要調整（角色/大綱/正文暴露的問題） | `hint`（具體要修改的世界觀內容）, `volume_index`（若與特定卷相關，填入整數；否則填 null） |
| `GO_BACK_TO_CHARACTERS` | 發現角色設定需要調整 | `hint`（具體要修改的角色內容） |
| `GO_BACK_TO_PLOT` | 發現大綱需要調整 | `hint`（具體要修改大綱內容）, `volume_index`（若有，填入整數；否則填 null）, `chapter_index`（若有，填入整數；否則填 null） |
| `WRITE_ALL_CHAPTERS` | 大綱已就緒，開始自動撰寫所有章節正文 | 無 |
| `GO_BACK_TO_SKELETON_EXPANSION` | 發現章節缺漏、序號中斷或空殼章節，退回至骨架增生 (volume_skeleton) 重新生成大綱骨架 | 無 |
| `ADD_BRIDGE_CONTENT` | 【第一級修補】在當前第 N 章前後插入橋接大綱，補足連貫性與邏輯漏洞 | `chapter_index`（目前正文有問題的當前章 index $N$） |
| `MODIFY_CURRENT_CHAPTER` | 【第二級修補】調用編輯姬對當前第 N 章正文正篇進行局部微調與精修拋光 | `chapter_index`（欲精修的當前章 index $N$）, `hint`（具體微調精修的方向引導） |
| `GO_BACK_TO_PREVIOUS_STEP` | 【第三級修補】多次修補仍不符，徹底刪除前後 +-3 章大綱與正文，回退大綱重新編寫 | `chapter_index`（受損中心章 index $N$） |
| `help_worldview` | 請求調閱完整的世界觀詳細設定與結構 | `reason`（為什麼需要調閱此細項，請在此詳細寫下你摘要的問題） |
| `help_characters` | 請求調閱角色 Bible 完整的詳細 JSON 數據 | `reason`（為什麼需要調閱此細項，請在此詳細寫下你摘要的問題） |
| `help_plot` | 請求調閱完整的劇情大綱細部 JSON 數據 | `reason`（為什麼需要調閱此細項，請在此詳細寫下你摘要的問題） |
| `WAIT_USER` | 遇到重大歧義或需要用戶確認的決策 | `reason`（原因） |
| `FINISH` | 全部任務已完成 | 無 |

## 回應格式（嚴格遵守，否則解析出錯）
請用繁體中文提供簡潔的評估分析，然後在末尾輸出 JSON 指令區塊：

```
【總監評估】
- 當前階段：「{current_stage}」
- 完成品質：[優秀/良好/需要修改]
- 主要發現：[1-3 句具體評估]

【決策理由】
[簡要說明為什麼選擇這個 ACTION]
```

然後必須在回應最後輸出以下 JSON 區塊（系統靠此解析）：

```json
{{
  "action": "CONTINUE",
  "target": "characters",
  "hint": "",
  "reason": "決策原因說明。若你呼叫了 help_* 調閱，請在 reason 中詳細摘要你在此模組中發現的疑點與想調閱的原因",
  "volume_index": null,
  "chapter_index": null
}}
```

## 重要提醒
- ⚠️ 重要：所有輸出內容（包含評估回應）必須使用 zh-TW 繁體中文
- 🚨 審查規則放行紅線：只有當出現「【紅色致命阻斷級】」缺陷時，才可以使用 `AUTO_REGENERATE` 或 `GO_BACK_*` 動作駁回；如果報告中只包含「🟡 跨卷/長線伏筆暫未收束」或「世界觀登場率不為 100%」（因為當前是局部增量生成），這是正常現象，你「必須」做出 `CONTINUE` 或 `WRITE_ALL_CHAPTERS` 的決策予以放行！嚴禁因為跨卷伏筆或局部設定使用率而惡意阻斷開發管線。
"""

    if current_stage in ["init", "worldview", "worldview_review", "worldview_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【世界觀設定與底層架構】
1. 評估世界觀核心設定、魔法系統/法則、世界衝突是否豐富合理。
2. 檢查多幕式結構是否規劃妥善。
3. **動態數據調閱**：為了防範 Context 膨脹，我們對下游的大綱與正文做了精簡隱藏。若你發現需要審查世界觀的所有子項細節以決定是否放行，**你必須發出 `help_worldview` 行動指令**，後端將會為你動態加載並回傳完整世界觀說明重新做決策！
"""
        if has_wb_and_char_at_init:
            stage_focus += """
🔥【創意總監緊急指令 - 強調當前事項重點】：
當前系統中「世界觀設定」與「角色聖經」均已存在！請你深度並重新閱讀完整世界觀設定，查看是否有正確且精細地完成各個世界觀設定細項（如多幕式起承轉合、關鍵轉折、伏筆種子等）。
- 如果發現任何設定細項存在邏輯不符、漏洞或需要拋光，你必須立刻決策 `GO_BACK_TO_WORLDVIEW` 或 `GO_BACK_TO_CHARACTERS`（並在 `hint` 中詳細指明需要修改的細項描述），呼叫細項修改流程！
- 如果你審查後確認完全無誤、無任何邏輯疏漏，才可以決策 `CONTINUE` 進度到大綱（`plot`）正常流程。請嚴格執行此項評估，拒絕含糊！
"""
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【角色 Bible 與登場策略】
1. 評估核心角色的性格特點、動機、背景故事是否生動。
2. 審查角色漸進登場策略 (progressive_character_plan) 是否合理（是否避免了一開始出場太多角色）。
3. **動態數據調閱**：下游的大綱伏筆與描述已隱藏。若需要審查全套角色聖經完整 JSON，**你必須發出 `help_characters` 指令**，後端會為你動態加載並回傳完整數據重新決策！
"""
    elif current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align", "volume_skeleton", "foreshadowing_orchestration"]:
        stage_focus = """
## 💡 當前審核重點：【全書千章宏觀大綱骨架與伏筆部署】
1. **規模校驗**：檢查小說是否已經完整拆解出 10-30 卷、數百到上千章的簡易骨架（標題與里程碑宣言）。
2. **素材厚度審計**：若發現大綱情節開始陷入重複、枯竭，說明上游世界觀與角色不夠用。你必須下達決策引導系統進行【增量創意膨脹（Creative Swelling）】，催生新勢力與人物！
3. **伏筆紅線**：嚴禁優質伏筆種子在 5 章內迅速閉環。每個伏筆的埋設與回收之間必須有足夠的戲劇跨度（跨卷張力）。

## 🎯 你的核心決策導向：
- 若全書骨架規模已足夠且長線佈局合理 ➔ 決策 `CONTINUE` 進入 `plot`（微觀大綱詳細展開階段）。
- 若情節枯竭、素材不足 ➔ 決策 `GO_BACK_TO_WORLDVIEW` 並在 `hint` 中給出具體的「世界觀膨脹/催生補丁」文學指導方針。
"""
    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【篇卷規劃、章節大綱與情節邏輯】
1. 這是品質把關的最核心關卡！請依據下方的「校驗報告」判斷大綱邏輯。
2. **伏筆時序與大綱硬性紅線（局部審核）**：
   - 審核時要注意這是不是**局部卷/增量生成**。若是局部生成（如只生成了第 2 卷，其餘各卷尚未生成），全域的伏筆登場率不為 100% 或跨卷伏筆暫時未回收屬於**正常現象**！
   - 只有當大綱存在「【紅色致命阻斷級】」標記（如連續章節序號斷裂、佔位空殼章節、時序顛倒或全域完結大綱伏筆遺忘）時，才可以使用 `AUTO_REGENERATE` 或 `GO_BACK_TO_PLOT` 退回；否則，你「必須」做出 `WRITE_ALL_CHAPTERS` 或 `CONTINUE` 決策放行！
3. **動態數據調閱**：為了防止大綱 Context 膨脹，我們只提供了基本校驗報告。若你發現自己需要調閱完整的劇情大綱細部 JSON 數據來查核情節，**你必須發出 `help_plot` 行動指令**，後端會為你動態加載並回傳完整大綱數據重新決策！
"""
    elif current_stage in ["writer", "writer_review"]:
        stage_focus = """
## 💡 當前審核重點：【正文正篇寫作品質】
1. 審核正篇小說寫作風格、對話自然度與鋪陳節奏。
2. 核對已寫正文是否與大綱情節、伏筆種子對齊，有無產生情節衝突。
3. 若寫作品質合格，請決策 `CONTINUE` 或 `WRITE_ALL_CHAPTERS`；若有嚴重錯誤，請使用 `AUTO_REGENERATE` target=`writer` 指定卷章進行重寫。
"""
    else:
        stage_focus = """
## 💡 當前審核重點：【常規階段把關】
1. 檢查目前產出的資料是否合格。若無誤請決策 `CONTINUE`。
"""

    return common_header + stage_focus + "\n{pre_check}\n\n## 系統底層結構完整性與情節邏輯校驗報告\n{validation_report}\n\n## 用戶原始創作需求\n{user_prompt}\n" + common_footer

def run_director_decision(novel_id, current_stage, user_prompt):
    """
    創意總監決策核心（首輪啟動）：
    結合程式智慧 pre-check、精簡 Context 視圖、當前階段特化 Prompt 與範圍感知校驗。
    """
    # 💡 智慧判定當前審查範圍 (Volume 或 Chapter)
    scope_volume_index, scope_chapter_index = infer_review_scope(novel_id, current_stage, user_prompt)
    
    from agents import compile_context, run_agent_stream
    context = compile_context(novel_id)
    
    # 💡 呼叫範圍感知化情節邏輯校驗函數，強迫總監直面大綱在數量、世界觀及伏筆上的現實
    validation_report_str = verify_novel_integrity(
        novel_id, 
        context, 
        current_stage, 
        scope_volume_index=scope_volume_index, 
        scope_chapter_index=scope_chapter_index
    )

    # 💡 程式智慧裁切：不要將無關的下游大綱等雜亂細項放入，以防範 Context 膨脹並避免總監評估模糊焦點！
    effective_worldbuilding = context["worldbuilding"]
    effective_characters = context["characters"]
    effective_plot = context["plot"]
    effective_written_chapters = context["written_chapters"]
    
    if current_stage in ["init", "worldview", "worldview_review", "worldview_go_back"]:
        effective_plot = "（大綱尚未規劃，隱藏大綱詳細數據，防止模糊焦點）"
        effective_written_chapters = "（正文寫作未開始，隱藏正文數據）"
        if current_stage in ["worldview", "worldview_review", "worldview_go_back"]:
            effective_characters = "（角色設計前，隱藏角色 Bible，避免干擾世界觀結構把控）"
            
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        effective_plot = "（大綱尚未規劃，隱藏大綱詳細設定，避免角色評審模糊焦點）"
        effective_written_chapters = "（正文寫作未開始，隱藏正文數據）"

    # 💡 檢測是否為 init 階段且世界觀與角色皆已存在
    wb_data = get_latest_worldbuilding(novel_id)
    char_data = get_latest_characters(novel_id)
    has_wb = wb_data and len(wb_data.get("content", "").strip()) > 100
    has_char = char_data and len(char_data.get("json_data", "").strip()) > 100
    
    has_wb_and_char_at_init = (current_stage == "init" and has_wb and has_char)

    # 💡 調用程式預檢，取得當前 Agent 預判及資料就緒狀況
    pre_check_str = pre_check_next_agent(novel_id, current_stage)

    # Determine next stage label
    stage_labels = {
        "worldview": "世界觀設定",
        "characters": "角色設計",
        "plot": "章節大綱",
        "writer": "正文寫作"
    }
    current_label = stage_labels.get(current_stage, current_stage)
    
    # 💡 獲取當前階段特化精簡 Prompt
    stage_prompt_template = get_simplified_director_prompt(current_stage, has_wb_and_char_at_init)
    
    prompt_content = stage_prompt_template.format(
        current_stage=current_label,
        worldbuilding=effective_worldbuilding if effective_worldbuilding != "No worldview defined yet." else "（尚無世界觀）",
        characters=effective_characters if effective_characters != "No characters designed yet." else "（尚無角色）",
        plot=effective_plot if effective_plot != "No plot chapters designed yet." else "（尚無大綱）",
        written_chapters=effective_written_chapters,
        pre_check=pre_check_str,
        user_prompt=user_prompt,
        validation_report=validation_report_str
    )
    
    messages = [
        {"role": "system", "content": "你是一位嚴謹但富有同理心的小說創意總監，負責把控小說創作的品質與邏輯一致性。你的風格是專業、直接、建設性反饋。"},
        {"role": "user", "content": prompt_content}
    ]
    
    # Save director decision to chat memory so it persists across sessions
    def save_director_decision_callback(nid, text, thinking=""):
        content = text
        inline_thinking = ""
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        final_thinking = (thinking.strip() + "\n" + inline_thinking.strip()).strip()
        save_chat_message(nid, "assistant", content, final_thinking, message_type="director")
        
    return run_agent_stream(novel_id, "copilot", messages, save_director_decision_callback)

def run_director_decision_help(novel_id, current_stage, help_action, help_reason):
    """
    後端驅動的動態數據調閱與二次審核流：
    當總監提出 help_worldview / help_characters / help_plot 時，後端載入完整資料庫內容，
    結合總監原本的摘要問題（reason），促使 LLM 進行二次精準把關。
    """
    help_target = help_action.replace("help_", "")
    help_labels = {
        "worldview": "世界觀設定",
        "characters": "角色聖經",
        "plot": "章節大綱"
    }
    help_label = help_labels.get(help_target, help_target)
    
    # 讀取完整設定數據
    detail_data = ""
    if help_target == "worldview":
        wb = get_latest_worldbuilding(novel_id)
        detail_data = wb["content"] if wb else "（目前世界觀為空）"
    elif help_target == "characters":
        char = get_latest_characters(novel_id)
        detail_data = char["json_data"] if char else "（目前角色聖經為空）"
    elif help_target == "plot":
        plot_list = get_stitched_plot(novel_id)
        if plot_list:
            # 大綱動態脫水手術：歷史章節脫水為極簡矩陣，只有最後10章保留全量微觀 events
            dehydrated_plot = []
            total_chapters = len(plot_list)
            
            for idx, ch in enumerate(plot_list):
                ch_idx = int(ch.get("chapter_index", 0))
                if total_chapters - idx <= 10:
                    dehydrated_plot.append(ch)
                else:
                    dehydrated_plot.append({
                        "chapter_index": ch_idx,
                        "title": ch.get("title", "未命名"),
                        "purpose_summary": ch.get("purpose", "") or "推進核心主線矛盾",
                        "foreshadowing_plant": ch.get("foreshadowing_plant", []),
                        "foreshadowing_payoff": ch.get("foreshadowing_payoff", [])
                    })
            
            detail_data = json.dumps(dehydrated_plot, ensure_ascii=False, indent=2)
        else:
            detail_data = "（目前大綱為空）"
        
    from db import get_novel
    novel = get_novel(novel_id)
    user_prompt = novel.get("pipeline_prompt", "") if novel else ""
    
    help_prompt = f"""【總監數據調閱回傳 - 這是第二次啟動】
你剛才因以下原因評估「{current_stage}」階段並請求調閱「{help_label}」的完整詳細說明：
💬 你的問題摘要與調閱理由：{help_reason}

以下是系統為你從資料庫中動態讀取並加載的【{help_label} 完整詳細說明】：
=========================================
{detail_data}
=========================================

請結合你剛才引發此調閱的問題摘要與理由，對這份詳細數據進行最終評審，並重新做出正確的下一步決定（例如 CONTINUE 進入下一階段，或 GO_BACK_* / AUTO_REGENERATE 修正）。

用戶原始創作需求：
{user_prompt}
"""

    STAGE_EVALUATION_PROMPT = """你是 AI 小說創作系統的【創意總監】，負責把控整個小說創作管道的品質與流程。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含評估回應和JSON指令區塊）。

## 當前任務評估
你目前正在處理【總監數據調閱】後的二次審核決策。

## 數據調閱內容與指引
{help_prompt}

## 可用的 ACTION 指令（嚴格選擇一個，不允許再呼叫 help_*，必須做出實質下一步決定）

| ACTION | 用途 | 必要欄位 |
|--------|------|----------|
| `CONTINUE` | 當前階段品質合格，繼續下一階段 | `target`（下一階段名稱） |
| `AUTO_REGENERATE` | 當前階段品質不足，需要重新生成 | `target`（要重跑的階段）, `hint` (要修改的細項描述), `volume_index`（若與特定卷相關，填入整數；否則填 null）, `chapter_index`（若與特定章相關，填入整數；否則填 null） |
| `GO_BACK_TO_WORLDVIEW` | 發現世界觀需要調整（角色/大綱/正文暴露的問題） | `hint`（具體要修改的世界觀內容）, `volume_index`（若與特定卷相關，填入整數；否則填 null） |
| `GO_BACK_TO_CHARACTERS` | 發現角色設定需要調整 | `hint`（具體要修改的角色內容） |
| `GO_BACK_TO_PLOT` | 發現大綱需要調整 | `hint`（具體要修改大綱內容）, `volume_index`（若有，填入整數；否則填 null）, `chapter_index`（若有，填入整數；否則填 null） |
| `WRITE_ALL_CHAPTERS` | 大綱已就緒，開始自動撰寫所有章節正文 | 無 |
| `GO_BACK_TO_SKELETON_EXPANSION` | 發現章節缺漏、序號中斷或空殼章節，退回至骨架增生 (volume_skeleton) 重新生成大綱骨架 | 無 |
| `ADD_BRIDGE_CONTENT` | 【第一級修補】在當前第 N 章前後插入橋接大綱，補足連貫性與邏輯漏洞 | `chapter_index`（目前正文有問題的當前章 index $N$） |
| `MODIFY_CURRENT_CHAPTER` | 【第二級修補】調用編輯姬對當前第 N 章正文正篇進行局部微調與精修拋光 | `chapter_index`（欲精修的當前章 index $N$）, `hint`（具體微調精修的方向引導） |
| `GO_BACK_TO_PREVIOUS_STEP` | 【第三級修補】多次修補仍不符，徹底刪除前後 +-3 章大綱與正文，回退大綱重新編寫 | `chapter_index`（受損中心章 index $N$） |
| `WAIT_USER` | 遇到重大歧義或需要用戶確認的決策 | `reason`（原因） |
| `FINISH` | 全部任務已完成 | 無 |

## 回應格式（嚴格遵守）
請用繁體中文提供簡潔 Dolan 評估分析，然後在末尾輸出 JSON 指令區塊：

```
【總監評估】
- 當前階段：「{current_stage} (數據調閱二次審查)」
- 完成品質：[優秀/良好/需要修改]
- 主要發現：[1-3 句具體評估]

【決策理由】
[簡要說明為什麼選擇這個 ACTION]
```

然後必須在回應最後輸出以下 JSON 區塊（系統靠此解析）：

```json
{{
  "action": "CONTINUE",
  "target": "characters",
  "hint": "",
  "reason": "二次審查完整設定後，確認無誤放行",
  "volume_index": null,
  "chapter_index": null
}}
```
"""
    prompt_content = STAGE_EVALUATION_PROMPT.format(
        current_stage=current_stage,
        help_prompt=help_prompt
    )
    
    messages = [
        {"role": "system", "content": "你是一位嚴謹的創意總監，負責把控小說創作的品質與邏輯一致性。你的風格是專業、直接、建設性反饋。"},
        {"role": "user", "content": prompt_content}
    ]
    
    from agents import run_agent_stream
    
    def save_director_decision_callback(nid, text, thinking=""):
        content = text
        inline_thinking = ""
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        final_thinking = (thinking.strip() + "\n" + inline_thinking.strip()).strip()
        
        save_chat_message(nid, "assistant", content, final_thinking, message_type="director")
        
    return run_agent_stream(novel_id, "copilot", messages, save_director_decision_callback)
