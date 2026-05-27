# -*- coding: utf-8 -*-
"""
擴增與總監邏輯控制器 (Agent Extension & Director Controller)
負責所有「半路攔截與修補」行為。
包含：對話框引導的增量修改（Patch/Append）、JIT 篇卷對齊、主編正文精修（Editor Agent），以及總監的決策流控。
完全與 Prompt 提示詞字串解耦，透過 agent_assembler.py 進行參數組合與 Prompt 注入。
"""

import json
import re
from datetime import datetime
import db
from llm import call_llm_stream

# 匯入參數組裝器以調用 LLM 任務
import agent_assembler
from agent_assembler import (
    compile_context,
    run_agent_stream,
    parse_json_safely,
    clean_json_text
)

from agent_main import (
    _looks_like_placeholder_chapter,
    _normalize_chapter_outlines,
    _sse_error_done,
    _sse_content,
    _sse_error
)

# ============================================================
# INCREMENTAL & REPAIR WIZARDS (細粒度增量修改與編輯姬呼叫入口)
# ============================================================

def run_incremental_architect(novel_id, target_section, user_hint):
    """
    增量生成/修改世界觀的特定部分
    """
    return agent_assembler.assemble_and_run_incremental_architect(novel_id, target_section, user_hint)

def run_incremental_character_designer(novel_id, target_char_index, field_name, user_hint):
    """
    增量生成/修改角色特定欄位或整體
    """
    return agent_assembler.assemble_and_run_incremental_character_designer(novel_id, target_char_index, field_name, user_hint)

def run_incremental_character_append(novel_id, new_character_names, user_hint=None):
    """
    精準增量追加新角色到角色聖經末尾
    """
    return agent_assembler.assemble_and_run_incremental_character_append(novel_id, new_character_names, user_hint)

def run_incremental_plot_planner(novel_id, insert_after_index, user_hint):
    """
    增量生成大綱章節並在指定位置插入
    """
    return agent_assembler.assemble_and_run_incremental_plot_planner(novel_id, insert_after_index, user_hint)

def run_volume_alignment(novel_id, volume_index):
    """
    延遲對齊 (Lazy Realignment) - 針對特定篇卷
    """
    return agent_assembler.assemble_and_run_volume_alignment(novel_id, volume_index)

def run_editor_agent(novel_id, chapter_index, edit_instructions=None):
    """
    調用編輯姬精修潤色特定章節正文
    """
    return agent_assembler.assemble_and_run_editor_agent(novel_id, chapter_index, edit_instructions)

def run_copilot_chat(novel_id, user_message):
    """
    與 Co-pilot Orchestrator 的常規對話與創意引導
    """
    return agent_assembler.assemble_and_run_copilot_chat(novel_id, user_message)

def run_director_decision(novel_id, current_stage, user_prompt):
    """
    創意總監決策把關核心
    """
    return agent_assembler.assemble_and_run_director_decision(novel_id, current_stage, user_prompt)

def run_director_decision_help(novel_id, current_stage, help_action, help_reason):
    """
    總監深度調閱後端輔助數據的二次決策
    """
    return agent_assembler.assemble_and_run_director_decision_help(novel_id, current_stage, help_action, help_reason)

# ============================================================
# JIT REALIGNMENT ENGINE (非同步 JIT 篇卷大綱對齊與安全重試救援)
# ============================================================

def run_volume_jit_alignment(novel_id, volume_index):
    """
    非同步 JIT 篇卷大綱對齊機制 (包含雙軌安全重試與診斷)
    """
    return agent_assembler.assemble_and_run_volume_jit_alignment(novel_id, volume_index)

# ============================================================
# DIRECTOR FLOW LOGIC (總監決策支撐演算法)
# ============================================================

def infer_review_scope(novel_id, current_stage, user_prompt):
    """
    分析使用者 Prompt、當前階段及資料庫中的髒卷(is_dirty)標記。
    """
    if user_prompt:
        user_prompt_str = str(user_prompt)
        vol_match = re.search(r'(?:第|Vol\.?\s*)(\d+)\s*(?:卷|volume)', user_prompt_str, re.IGNORECASE)
        if vol_match:
            try:
                return int(vol_match.group(1)), None
            except ValueError:
                pass
                
        vol_cn_match = re.search(r'第\s*([一二三四五六七八九十]+)\s*卷', user_prompt_str)
        if vol_cn_match:
            cn_to_num = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
            try:
                val = cn_to_num.get(vol_cn_match.group(1))
                if val:
                    return val, None
            except:
                pass
                
        ch_match = re.search(r'(?:第|Ch\.?\s*)(\d+)\s*(?:章|chapter)', user_prompt_str, re.IGNORECASE)
        if ch_match:
            try:
                ch_idx = int(ch_match.group(1))
                vols = db.get_volumes(novel_id)
                v_idx = db.get_chapter_volume_index(vols, ch_idx)
                return v_idx, ch_idx
            except ValueError:
                pass

    if current_stage == "writer":
        from db import get_all_chapters_latest
        try:
            written_chaps = db.get_all_chapters_latest(novel_id)
            if written_chaps:
                latest_idx = max(int(c.get("chapter_index", 0)) for c in written_chaps)
                if latest_idx > 0:
                    vols = db.get_volumes(novel_id)
                    v_idx = db.get_chapter_volume_index(vols, latest_idx)
                    return v_idx, latest_idx
        except Exception:
            pass

    vols = db.get_volumes(novel_id)
    for v in vols:
        if v.get("is_dirty") == 1 or v.get("is_dirty") == "1":
            return int(v["volume_index"]), None
            
    return None, None

def verify_novel_integrity(novel_id, context, current_stage=None, scope_volume_index=None, scope_chapter_index=None):
    """
    底層結構與情節邏輯全域/局部範圍感知校驗
    """
    is_early_stage = (current_stage in ["init", "worldview", "worldview_review", "worldview_go_back", "characters", "characters_review", "characters_go_back", "volumes", "volumes_review", "volumes_go_back"])
    
    if is_early_stage:
        return """【底層結構完整性與情節邏輯校驗報告（當前階段不適用）】
1. 📂 設定結構完整性：
   - 多幕式結構 是否有合法內容：[設定階段，待大綱完成後校驗]
   - 角色登場規劃 是否有合法內容：[設定階段，待大綱完成後校驗]
2. 📊 卷數與章節數量檢驗：
   - 篇卷規劃數：[設定階段，不阻斷]
3. 🌍 世界觀設定使用率檢驗：
   - 陣營/勢力設定全域使用率：[設定階段，不阻斷]
💡 總監提示：目前處於初始或設定規劃階段，尚未開始大綱拆解。請直接放行 CONTINUE。"""
    
    is_macro_skeleton_stage = (current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align", "volume_skeleton", "foreshadowing_orchestration"])
    
    if is_macro_skeleton_stage:
        vols = db.get_volumes(novel_id)
        volumes_count = len(vols)
        total_chapters = sum(int(v.get("chapter_count", 0)) for v in vols)
        
        plot_json_for_scan = parse_json_safely(context.get("plot", ""), default={})
        plot_chapters_for_scan = plot_json_for_scan.get("chapters", []) if isinstance(plot_json_for_scan, dict) else []
        skeleton_chapter_count = len(plot_chapters_for_scan)
        
        missing_skeleton_volumes = []
        for vol in vols:
            vol_idx = int(vol.get("volume_index", 0))
            chapters_outline = vol.get("chapters_outline") or vol.get("chapters_skeleton") or []
            if not chapters_outline or chapters_outline == "[]" or chapters_outline == "{}":
                missing_skeleton_volumes.append(vol_idx)
        
        if scope_volume_index is not None:
            skeleton_missing_warning = f"\n🔴【篇卷骨架缺失警告】：當前審查的第 {scope_volume_index} 卷章節骨架為空，請先生成該卷骨架！" if scope_volume_index in missing_skeleton_volumes else ""
            return f"""【底層結構完整性校驗報告 — 🌍 宏觀骨架局部審查模式 (第 {scope_volume_index} 卷)】
1. 📊 當前卷骨架規模：
   - 全書已規劃篇卷：{volumes_count} 卷
   - 全書當前骨架章節：{skeleton_chapter_count} 章 / 規劃總章節：{total_chapters} 章
   - 指標評定：{"🟢 骨架狀態合格" if scope_volume_index not in missing_skeleton_volumes else "🔴 當前卷骨架缺失"}{skeleton_missing_warning}
2. 🎯 局部審查放行指引：
   - 若當前第 {scope_volume_index} 卷骨架正常，必須做出 CONTINUE 正常放行！"""
        else:
            skeleton_missing_warning = f"\n🔴【篇卷骨架缺失警告】：以下篇卷的章節骨架為空：第 {missing_skeleton_volumes} 卷" if missing_skeleton_volumes else ""
            return f"""【底層結構完整性校驗報告 — 🌍 宏觀骨架全域審查模式】
1. 📊 全書宏觀規模覆蓋率：
   - 目前已規劃篇卷數：{volumes_count} 卷 | 骨架總章節數：{skeleton_chapter_count} 章
   - 指標評定：{"🟢 骨架規模已達到長篇標準" if skeleton_chapter_count >= 500 else "🟡 骨架規模尚未覆蓋全書，待後續滾動生成"}{skeleton_missing_warning}
⚠️ 宏觀放行紅線：若有缺失，必須下達 volume_skeleton 進行骨架生成。"""

    wb_str = context.get("worldbuilding", "")
    if not wb_str or "No worldview defined yet." in wb_str:
        wb_data = db.get_latest_worldbuilding(novel_id)
        wb_str = wb_data["content"] if wb_data else ""
        
    wb_json = parse_json_safely(wb_str) if wb_str else {}
    if not isinstance(wb_json, dict):
        wb_json = {}
        
    three_act = wb_json.get("multi_act_structure", [])
    has_three_act = isinstance(three_act, list) and any(isinstance(item, dict) and item.get("content", "").strip() != "" for item in three_act)
    progressive_plan = wb_json.get("progressive_character_plan", [])
    has_progressive_plan = isinstance(progressive_plan, list) and any(isinstance(item, dict) and item.get("content", "").strip() != "" for item in progressive_plan)
    
    vols = db.get_volumes(novel_id)
    volumes_count = len(vols)
    
    plot_json_all = parse_json_safely(context.get("plot", ""), default={})
    plot_chapters_all = plot_json_all.get("chapters", []) if isinstance(plot_json_all, dict) else []
    
    plot_chapters_for_scan = []
    if scope_volume_index is not None:
        for ch in plot_chapters_all:
            if isinstance(ch, dict) and db.get_chapter_volume_index(vols, int(ch.get("chapter_index", 0))) == int(scope_volume_index):
                plot_chapters_for_scan.append(ch)
    else:
        plot_chapters_for_scan = plot_chapters_all

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
    expected_vols_by_outline = db.get_chapter_volume_index(vols, max_chapter_idx) if max_chapter_idx > 0 else 0
    
    gaps = []
    if scope_volume_index is not None:
        start_ch, end_ch = db.get_volume_chapter_range(vols, scope_volume_index)
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
    
    used_factions = [f for f in all_factions if any(f in json.dumps(ch, ensure_ascii=False) for ch in plot_chapters_for_scan)]
    unused_factions = [f for f in all_factions if f not in used_factions]
    
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
    
    if scope_volume_index is not None:
        faction_status = f"陣營/勢力登場數：{len(used_factions)} 個"
        seed_status = f"世界觀伏筆登場數：{len(used_seeds)} 個"
        tp_status = f"世界觀轉折點登場數：{len(used_tps)} 個"
    else:
        faction_status = f"陣營/勢力設定全域使用率：{len(used_factions)}/{len(all_factions)} ({faction_usage_rate:.1f}%)"
        if unused_factions:
            faction_status += f" — ⚠️ 未使用的勢力：{unused_factions}"
        seed_status = f"世界觀伏筆種子使用率：{len(used_seeds)}/{len(seeds)} ({seed_usage_rate:.1f}%)"
        if unused_seeds:
            seed_status += f" — ⚠️ 未使用伏筆種子前五：{[s[:15] + '...' for s in unused_seeds[:5]]}"
        tp_status = f"世界觀關鍵轉折點使用率：{len(used_tps)}/{len(tps)} ({tp_usage_rate:.1f}%)"
        if unused_tps:
            tp_status += f" — ⚠️ 未使用轉折點前五：{[t[:15] + '...' for t in unused_tps[:5]]}"

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
        if isinstance(plants, str): plants = [plants]
        if isinstance(payoffs, str): payoffs = [payoffs]
        for p in plants:
            if isinstance(p, str):
                for m in re.findall(r'(?:[Ss]eed|伏筆)\s*[-\s]?\s*(\d+)', p):
                    plants_map.setdefault(int(m), []).append(ch_idx)
        for py in payoffs:
            if isinstance(py, str):
                for m in re.findall(r'(?:[Ss]eed|伏筆)\s*[-\s]?\s*(\d+)', py):
                    payoffs_map.setdefault(int(m), []).append(ch_idx)

    plants_map_all = {}
    for ch in plot_chapters_all:
        try:
            ch_idx = int(ch.get("chapter_index", 0))
        except:
            continue
        plants = ch.get("foreshadowing_plant", []) or []
        if isinstance(plants, str): plants = [plants]
        for p in plants:
            if isinstance(p, str):
                for m in re.findall(r'(?:[Ss]eed|伏筆)\s*[-\s]?\s*(\d+)', p):
                    plants_map_all.setdefault(int(m), []).append(ch_idx)
                
    dangling_plants = []
    deep_foreshadowings = []
    baseless_payoffs = []
    out_of_order_seeds = []
    
    total_chapters = db.get_total_chapter_count(vols)
    is_all_chapters_completed = (max_chapter_idx >= total_chapters) if total_chapters > 0 else False
    
    for s_id, p_chaps in plants_map.items():
        if s_id not in payoffs_map:
            if scope_volume_index is not None or not is_all_chapters_completed:
                deep_foreshadowings.append(f"[Seed-{s_id}] (埋設於第 {p_chaps} 章，將於後續篇卷回收)")
            else:
                dangling_plants.append(f"[Seed-{s_id}] (埋設於第 {p_chaps} 章)")
        else:
            earliest_plant = min(p_chaps)
            earliest_payoff = min(payoffs_map[s_id])
            if earliest_payoff <= earliest_plant:
                out_of_order_seeds.append(f"[Seed-{s_id}] (第 {earliest_payoff} 章回收，卻在第 {earliest_plant} 章才埋設)")
                
    for s_id, py_chaps in payoffs_map.items():
        has_plant = s_id in plants_map
        if not has_plant:
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
        foreshadowing_violations.append(f"  🔴【伏筆未回收】：{dangling_plants} (全書大綱已完結，但有伏筆被遺忘)")
    if baseless_payoffs:
        foreshadowing_violations.append(f"  🔴【伏筆憑空回收】：{baseless_payoffs} (未在前文進行 any Seed 埋設)")
    if out_of_order_seeds:
        foreshadowing_violations.append(f"  🔴【伏筆時序顛倒】：{out_of_order_seeds}")
    if deep_foreshadowings:
        foreshadowing_violations.append(f"  🟡【跨卷/長線伏筆暫未收束】：{deep_foreshadowings}")
        
    fores_alignment_str = "章節伏筆時序與收束銜接度：局部伏筆完全符合時序且無遺漏" if not foreshadowing_violations else "\n".join(foreshadowing_violations)
    placeholder_chapter_warning = f"⚠️【🔴 偵測到佔位/空殼章節】：第 {placeholder_outline_indices} 章" if placeholder_outline_indices else "無"

    coherence_report_str = ""
    N = scope_chapter_index if scope_chapter_index is not None else 0
    if N == 0:
        try:
            written_chaps = db.get_all_chapters_latest(novel_id)
            if written_chaps:
                N = max(int(c.get("chapter_index", 0)) for c in written_chaps)
        except:
            pass

    if current_stage in ["writer", "writer_review"] and N > 0:
        prev_prose = "（無前一章正文，本章為第一章）"
        if N > 1:
            prev_chap = db.get_latest_chapter(novel_id, N - 1)
            if prev_chap: prev_prose = prev_chap.get("content", "")
        curr_prose = ""
        curr_chap = db.get_latest_chapter(novel_id, N)
        if curr_chap: curr_prose = curr_chap.get("content", "")
            
        outlines_in_range = []
        for c_outline in plot_chapters_all:
            try:
                c_idx = int(c_outline.get("chapter_index", 0))
                if N - 3 <= c_idx <= N + 3:
                    outline_str = f"第 {c_idx} 章 【{c_outline.get('title')}】\n  • 章節大綱：{c_outline.get('summary') or c_outline.get('description')}\n"
                    outlines_in_range.append(outline_str)
            except:
                pass
                
        history = db.get_chat_memory(novel_id, limit=30, message_type='director')
        has_add_bridge = any(h.get("content") and "ADD_BRIDGE_CONTENT" in h["content"] and str(N) in h["content"] for h in history)
        has_modify_current = any(h.get("content") and "MODIFY_CURRENT_CHAPTER" in h["content"] and str(N) in h["content"] for h in history)
        
        if not has_add_bridge:
            recommended_hint = "【第一級修補建議】建議總監做出 ADD_BRIDGE_CONTENT 決策。"
        elif not has_modify_current:
            recommended_hint = "【第二級修補建議】建議總監做出 MODIFY_CURRENT_CHAPTER 決策。"
        else:
            recommended_hint = "【第三級修補建議】建議總監做出 GO_BACK_TO_PREVIOUS_STEP 決策。"

        coherence_report_str = f"""
5. ✍️ 【當前已生成之第 {N} 章寫作連貫性深度校驗資料】：
   - 【第 {N-1} 章已寫正文完整內容】：
{prev_prose[:800]}... (略)
   
   - 【第 {N-3} 章至第 {N+3} 章之詳細大綱】：
{"".join(outlines_in_range)}
   
   - 【當前第 {N} 章待校驗正文完整內容】：
{curr_prose[:800]}... (略)
   
   - 【修補指引】：{recommended_hint}"""

    return f"""【底層結構完整性與情節邏輯校驗報告】
1. 📂 設定結構完整性：
   - 多幕式結構 是否有合法內容：{ "是" if has_three_act else "否" }
   - 角色登場規劃 是否有合法內容：{ "是" if has_progressive_plan else "否" }
2. 📊 卷數與章節數量檢驗：
   - {vol_status_str}
   - {gap_status_str}
   - 偵測到的佔位/保底大綱章節：{placeholder_chapter_warning}
3. 🌍 世界觀設定使用率檢驗：
   - {faction_status}
   - {seed_status}
   - {tp_status}
4. 🔑 章節內容 - 伏筆時序與收束銜接度檢驗：
   - {fores_status_str}
   - {fores_alignment_str}
{coherence_report_str}
"""

def pre_check_next_agent(novel_id, current_stage):
    """
    在總監決定前，程式進行基本健康度判斷與推薦 action
    """
    wb = db.get_latest_worldbuilding(novel_id)
    has_wb = wb and len(wb.get("content", "").strip()) > 100
    char = db.get_latest_characters(novel_id)
    has_char = char and len(char.get("json_data", "").strip()) > 100
    vols = db.get_volumes(novel_id)
    has_volumes = len(vols) > 0
    
    from db import get_all_volume_skeletons
    skeletons = db.get_all_volume_skeletons(novel_id)
    has_skeletons = skeletons and len(skeletons) > 0
    
    plot_data = db.get_stitched_plot(novel_id)
    has_plot = plot_data and len(plot_data) > 0
    has_foreshadowing_alloc = any(ch.get("allocated_tasks") for ch in plot_data.get("chapters", [])) if has_plot else False
    
    suggested_agent = ""
    status_summary = ""
    suggestion = ""
    
    if current_stage == "init":
        if not has_wb:
            suggested_agent = "Story Architect"
            status_summary = "世界觀為空。"
            suggestion = "請 CONTINUE 到 worldview 以規劃世界觀。"
        elif not has_char:
            suggested_agent = "Character Designer"
            status_summary = "角色聖經為空。"
            suggestion = "請 CONTINUE 到 characters 以生成角色。"
        elif not has_volumes:
            suggested_agent = "Volumes Planner"
            status_summary = "尚未進行分卷規劃。"
            suggestion = "請 CONTINUE 到 volumes 以劃分篇卷。"
        elif not has_skeletons:
            suggested_agent = "Volume Skeleton Planner"
            status_summary = "篇卷骨架尚未拆解。"
            suggestion = "請 CONTINUE 到 volume_skeleton 拆解骨架。"
        elif not has_foreshadowing_alloc:
            suggested_agent = "Foreshadowing Orchestrator"
            status_summary = "尚未編織伏筆。"
            suggestion = "請 CONTINUE 到 foreshadowing_orchestration 對齊伏筆。"
        else:
            suggested_agent = "Plot Planner"
            status_summary = "骨架與對齊已完成。"
            suggestion = "請 CONTINUE 到 plot 生成詳細章節大綱。"
            
    elif current_stage in ["worldview", "worldview_review", "worldview_go_back"]:
        suggested_agent = "Character Designer"
        if has_wb:
            status_summary = "世界觀已就緒。"
            suggestion = "請 CONTINUE 正常前進到 characters。"
        else:
            status_summary = "⚠️ 世界觀為空！"
            suggestion = "必須決策 AUTO_REGENERATE worldview 重新生成！"
            
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        suggested_agent = "Volumes Planner"
        if not has_char:
            status_summary = "⚠️ 角色聖經為空！"
            suggestion = "必須決策 AUTO_REGENERATE characters 重新生成！"
        else:
            status_summary = "角色聖經已就緒。"
            suggestion = "請 CONTINUE 正常前進到 volumes。"
            
    elif current_stage in ["volumes", "volumes_review", "volumes_go_back"]:
        suggested_agent = "Volume Skeleton Planner"
        if not has_volumes:
            status_summary = "⚠️ 分卷規劃為空！"
            suggestion = "必須決策 AUTO_REGENERATE volumes 重新生成！"
        else:
            status_summary = f"已劃分 {len(vols)} 卷。"
            suggestion = "請 CONTINUE 前進到 volume_skeleton 拆解骨架。"
            
    elif current_stage in ["volume_skeleton", "skeleton_review"]:
        suggested_agent = "Foreshadowing Orchestrator"
        if not has_skeletons:
            status_summary = "⚠️ 篇卷骨架為空！"
            suggestion = "必須決策 AUTO_REGENERATE volume_skeleton 重新生成！"
        else:
            status_summary = f"骨架已就緒，共 {len(skeletons)} 章。"
            suggestion = "請 CONTINUE 前進到 foreshadowing_orchestration 分配伏筆。"
            
    elif current_stage in ["foreshadowing_orchestration", "foreshadowing_review", "foreshadowing_align"]:
        suggested_agent = "Plot Planner"
        if not has_foreshadowing_alloc:
            status_summary = "⚠️ 尚未進行伏筆分配！"
            suggestion = "必須決策 AUTO_REGENERATE foreshadowing_orchestration 重新對齊！"
        else:
            status_summary = "伏筆分配已就緒。"
            suggestion = "請 CONTINUE 正常前進到 plot 展開詳細大綱。"
            
    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        suggested_agent = "Novel Writer"
        if not has_plot:
            status_summary = "⚠️ 尚未生成詳細大綱！"
            suggestion = "必須決策 AUTO_REGENERATE plot 重新規劃！"
        else:
            status_summary = "詳細大綱已就緒。"
            suggestion = "請決策 WRITE_ALL_CHAPTERS 或 CONTINUE 正常推進寫作！"
            
    elif current_stage in ["writer", "writer_review"]:
        suggested_agent = "Novel Writer / FINISH"
        status_summary = f"已寫作 {len(db.get_all_chapters_latest(novel_id))} 章節。"
        suggestion = "可決策 CONTINUE 或 FINISH。若有不連貫，可依據三級修補機制進行決策。"

    return f"""【程式基本判斷結果（總監決策前預檢）】：
- 🎯 當前階段：{current_stage}
- 準備呼叫的下一個 Agent：{suggested_agent}
- 📊 資料庫當前設定狀態：{status_summary}
- 💡 程式建議總監動作：{suggestion}"""

def get_simplified_director_prompt(current_stage, has_wb_and_char_at_init=False):
    """
    動態生成各階段的特化 system prompt。
    """
    return agent_assembler.get_simplified_director_prompt(current_stage, has_wb_and_char_at_init)

def parse_incremental_command(command_text, current_context):
    """
    解析總監的增量操作指令類型與參數
    """
    result = {"operation_type": "full", "target": None, "params": {}}
    cmd_lower = command_text.lower()
    
    if any(k in command_text for k in ["新增", "插入", "增加"]):
        result["operation_type"] = "incremental_add"
    elif any(k in command_text for k in ["修改", "更新", "調整"]):
        result["operation_type"] = "incremental_update"
    elif any(k in command_text for k in ["局部", "部分"]):
        result["operation_type"] = "partial"
        
    if "角色" in command_text:
        result["target"] = "character"
        idx_match = re.search(r'第?\s*(\d+)\s*個?角色', command_text)
        if idx_match: result["params"]["char_index"] = int(idx_match.group(1)) - 1
    elif any(k in command_text for k in ["大綱", "章節"]):
        result["target"] = "plot"
        idx_match = re.search(r'第?\s*(\d+)\s*章', command_text)
        if idx_match: result["params"]["insert_after_index"] = int(idx_match.group(1)) - 1
    elif any(k in command_text for k in ["世界觀", "伏筆", "轉折", "篇卷", "時間軸", "時間線"]) or "volumes" in cmd_lower:
        result["target"] = "worldbuilding"
        
    if any(k in cmd_lower for k in ["personality", "性格"]):
        result["params"]["field_name"] = "personality"
    elif any(k in cmd_lower for k in ["motivation", "動機"]):
        result["params"]["field_name"] = "motivation"
    elif any(k in cmd_lower for k in ["arc", "弧線", "成長"]):
        result["params"]["field_name"] = "arc"
    elif any(k in cmd_lower for k in ["foreshadowing", "伏筆"]):
        result["params"]["field_name"] = "foreshadowing_seeds"
        result["target"] = "worldbuilding"
    elif any(k in cmd_lower for k in ["turning", "轉折"]):
        result["params"]["field_name"] = "key_turning_points"
        result["target"] = "worldbuilding"
    elif any(k in cmd_lower for k in ["篇卷", "時間軸", "時間線"]) or "volumes" in cmd_lower:
        result["params"]["field_name"] = "volumes"
        result["target"] = "worldbuilding"
        
    return result
