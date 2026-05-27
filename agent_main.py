# -*- coding: utf-8 -*-
"""
主要創作流程控制器 (Story Core Creation Flow Controller)
唯獨負責「全新創作」的黃金主軸（世界觀 ➔ 角色 ➔ 卷 ➔ 骨架 ➔ 大綱 ➔ 寫作）。
只管開新局、依序生成、存入 DB。完全與 Prompt 提示詞字串解耦。
"""

import json
import re
import random
import hashlib
import db

# 匯入參數注入與組合器中的核心工具與 LLM 調用介面
from agent_assembler import (
    clean_json_text,
    parse_json_safely,
    compile_context,
    run_agent_stream
)

# ============================================================
# UTILITIES & VALIDATORS (大綱解析與底層欄位檢驗邏輯)
# ============================================================

def _looks_like_placeholder_chapter(ch):
    if not isinstance(ch, dict):
        return True
    title = ch.get("title", "") or ch.get("brief_title", "")
    summary = ch.get("summary", "") or ch.get("brief_summary", "") or ch.get("event", "")
    
    placeholders = ["保底", "修復", "待填寫", "請填入", "推進核心衝突", "面臨新考驗", "無", "placeholder"]
    if any(p in title for p in placeholders) or any(p in summary for p in placeholders):
        return True
    if len(summary.strip()) < 10:
        return True
    return False

def _normalize_chapter_outlines(chapters, start_chapter, expected_count=50):
    normalized = []
    if isinstance(chapters, dict) and "chapters_skeleton" in chapters:
        chapters = chapters["chapters_skeleton"]
    elif isinstance(chapters, dict) and "chapters" in chapters:
        chapters = chapters["chapters"]
    elif isinstance(chapters, dict) and "allocations" in chapters:
        chapters = chapters["allocations"]
        
    if not isinstance(chapters, list) or len(chapters) == 0:
        return []
        
    for idx in range(expected_count):
        if idx < len(chapters):
            ch = chapters[idx]
        else:
            ch = {"title": f"第 {start_chapter + idx} 章保底大綱", "summary": "推進核心衝突且面臨新考驗。"}
            
        if not isinstance(ch, dict):
            ch = {"title": f"第 {start_chapter + idx} 章修復大綱", "summary": str(ch)}
            
        ch["chapter_index"] = start_chapter + idx
        ch.setdefault("time_setting", "承接前章")
        ch.setdefault("time_span", "承接前章")
        ch.setdefault("purpose", "承接前章因果並推進本卷核心矛盾")
        ch.setdefault("foreshadowing_plant", [])
        ch.setdefault("foreshadowing_payoff", [])
        ch.setdefault("characters_active", [])
        ch.setdefault("characters_introduced", [])
        ch.setdefault("emotional_tone", "緊張與沉思交錯")
        ch.setdefault("cliffhanger", "新的因果鉤子浮現")
        normalized.append(ch)
    return normalized

def validate_worldview(worldbuilding_text: str):
    if (not worldbuilding_text) or worldbuilding_text.strip() == "" or "No worldview defined yet." in worldbuilding_text:
        return False, ["尚無世界觀設定"]
    return True, []

def validate_characters(characters_text: str):
    if (not characters_text) or characters_text.strip() == "" or "No characters designed yet." in characters_text:
        return False, ["尚無角色設定（Character Bible）"]
    parsed = parse_json_safely(characters_text, default={})
    chars = parsed.get("characters") if isinstance(parsed, dict) else None
    if isinstance(chars, list) and len(chars) > 0:
        return True, []
    return False, ["角色設定 JSON 結構不完整（缺少 characters 陣列）"]

def validate_plot(plot_text: str):
    if (not plot_text) or plot_text.strip() == "" or "No plot chapters designed yet." in plot_text:
        return False, ["尚無章節大綱（plot）"]
    parsed = parse_json_safely(plot_text, default={})
    chapters = parsed.get("chapters") if isinstance(parsed, dict) else None
    if isinstance(chapters, list) and len(chapters) > 0:
        return True, []
    return False, ["章節大綱 JSON 結構不完整（缺少 chapters 陣列）"]

def validate_plot_has_chapter(plot_text: str, chapter_index: int):
    ok, errors = validate_plot(plot_text)
    if not ok:
        return False, errors
    parsed = parse_json_safely(plot_text, default={})
    chapters = parsed.get("chapters", []) if isinstance(parsed, dict) else []
    for ch in chapters:
        if isinstance(ch, dict) and ch.get("chapter_index") is not None:
            try:
                if int(ch.get("chapter_index")) == int(chapter_index):
                    return True, []
            except (ValueError, TypeError):
                pass
    return False, [f"章節大綱中未規劃第 {chapter_index} 章"]

def _sse_error_done(msg):
    yield "data: " + json.dumps({"type": "error", "message": msg}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}) + "\n\n"

def _sse_content(delta):
    return "data: " + json.dumps({"type": "content", "delta": delta}, ensure_ascii=False) + "\n\n"

def _sse_error(msg):
    return "data: " + json.dumps({"type": "error", "message": msg}, ensure_ascii=False) + "\n\n"

def generate_chapter_synopsis(content):
    """
    資深文學主編對已產出的正文，自動非同步收縮為 100 字極簡梗概
    """
    if not content:
        return ""
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    synopsis = "。".join(lines[:3])
    if len(synopsis) > 100:
        synopsis = synopsis[:97] + "..."
    return synopsis

# ============================================================
# PRIMARY CREATION ACTIONS (主線主流程創建入口 - 委託 Assembler)
# ============================================================

def run_story_architect(novel_id, user_prompt):
    """
    呼叫 Story Architect Agent 開始建構底層世界觀設定
    """
    from agent_assembler import assemble_and_run_story_architect
    return assemble_and_run_story_architect(novel_id, user_prompt)

def run_volumes_planner(novel_id, user_prompt=None):
    """
    呼叫 Volumes Planner Agent 規劃小說的宏觀大篇卷設定
    """
    from agent_assembler import assemble_and_run_volumes_planner
    return assemble_and_run_volumes_planner(novel_id, user_prompt)

def run_character_designer(novel_id, user_prompt=None):
    """
    呼叫 Character Designer Agent 設計角色聖經設定
    """
    from agent_assembler import assemble_and_run_character_designer
    return assemble_and_run_character_designer(novel_id, user_prompt)

def run_volume_skeleton_planner(novel_id, volume_index, user_prompt=None):
    """
    呼叫 Volume Skeleton Planner 為特定篇卷拆解簡易大綱骨架
    """
    from agent_assembler import assemble_and_run_volume_skeleton_planner
    return assemble_and_run_volume_skeleton_planner(novel_id, volume_index, user_prompt)

def run_foreshadowing_orchestrator(novel_id, user_prompt=None):
    """
    全局伏筆與轉折編織對齊階段 (Stage 3) - 混合演算法與 LLM 對齊
    """
    context = compile_context(novel_id)
    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    foreshadowing_seeds = worldview_json.get("foreshadowing_seeds", [])
    key_turning_points = worldview_json.get("key_turning_points", [])
    
    if not foreshadowing_seeds and not key_turning_points:
        return _sse_error_done("無法執行伏筆編織：世界觀中尚無伏筆種子或轉折點設定。請先在世界觀設定中添加伏筆與轉折點。")
    
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id)
    
    if not skeletons:
        return _sse_error_done("無法執行伏筆編織：尚無簡易章大綱骨架。請先完成各卷的簡易章大綱生成（volume_skeleton）。")
        
    def main_orchestrate_gen():
        yield "data: " + json.dumps({"type": "content", "delta": "=== [全局伏筆編織對齊] ===\n正在啟動高維度 [演算法+LLM雙軌對齊] 進行伏筆與轉折全局調度...\n\n"}, ensure_ascii=False) + "\n\n"
        
        N = len(skeletons)
        S = len(foreshadowing_seeds)
        T = len(key_turning_points)
        
        skeletons.sort(key=lambda x: int(x.get("chapter_index", 0)))
        chapter_indices = [int(x.get("chapter_index", 0)) for x in skeletons]
        
        if N >= 50:
            min_span = max(15, N // 5)
        elif N >= 20:
            min_span = max(8, N // 4)
        elif N >= 10:
            min_span = max(4, N // 3)
        else:
            min_span = max(1, N // 2)
            
        prog_allocations = {
            ch_idx: {
                "chapter_index": ch_idx,
                "title": skeletons[idx].get("brief_title") or skeletons[idx].get("title") or "未命名",
                "summary": skeletons[idx].get("brief_summary") or skeletons[idx].get("summary") or "無",
                "foreshadowing_plants": [],
                "foreshadowing_payoffs": [],
                "turning_points": []
            }
            for idx, ch_idx in enumerate(chapter_indices)
        }
        
        h_seed = int(hashlib.md5(novel_id.encode('utf-8')).hexdigest(), 16) % (2**32)
        r = random.Random(h_seed)
        
        for i in range(S):
            max_plant_idx = N - min_span - 1
            if max_plant_idx <= 0:
                plant_idx = 0
            else:
                seg_size = float(max_plant_idx + 1) / S
                start_seg = int(i * seg_size)
                end_seg = int((i + 1) * seg_size)
                start_seg = max(0, min(start_seg, max_plant_idx))
                end_seg = max(start_seg + 1, min(end_seg, max_plant_idx + 1))
                plant_idx = r.randint(start_seg, end_seg - 1)
                
            plant_ch = chapter_indices[plant_idx]
            payoff_start = plant_idx + min_span
            if payoff_start >= N:
                payoff_start = N - 1
            payoff_idx = r.randint(payoff_start, N - 1)
            payoff_ch = chapter_indices[payoff_idx]
            
            seed_desc = foreshadowing_seeds[i]
            prog_allocations[plant_ch]["foreshadowing_plants"].append(f"[Seed-{i+1}] {seed_desc}")
            prog_allocations[payoff_ch]["foreshadowing_payoffs"].append(f"[Seed-{i+1}] {seed_desc}")
            
        for j in range(T):
            seg_size = float(N) / T
            start_seg = int(j * seg_size)
            end_seg = int((j + 1) * seg_size)
            start_seg = max(0, min(start_seg, N - 1))
            end_seg = max(start_seg + 1, min(end_seg, N))
            tp_idx = r.randint(start_seg, end_seg - 1)
            tp_ch = chapter_indices[tp_idx]
            
            tp_desc = key_turning_points[j]
            prog_allocations[tp_ch]["turning_points"].append(f"[TurningPoint-{j+1}] {tp_desc}")
            
        tasked_chapters = []
        for ch_idx in chapter_indices:
            alloc = prog_allocations[ch_idx]
            if alloc["foreshadowing_plants"] or alloc["foreshadowing_payoffs"] or alloc["turning_points"]:
                tasked_chapters.append(alloc)
                
        def merge_and_save_allocations(nid, llm_allocations):
            merged_list = []
            llm_map = {}
            if isinstance(llm_allocations, list):
                for item in llm_allocations:
                    idx = item.get("chapter_index")
                    if idx is not None:
                        llm_map[int(idx)] = item
                        
            for ch_idx in chapter_indices:
                prog = prog_allocations[ch_idx]
                llm_item = llm_map.get(ch_idx, {})
                
                merged_plants = []
                merged_payoffs = []
                merged_tps = []
                
                for plant_str in prog["foreshadowing_plants"]:
                    seed_tag = plant_str.split("]")[0] + "]"
                    found = False
                    llm_plants_list = llm_item.get("foreshadowing_plants", []) or []
                    if isinstance(llm_plants_list, str):
                        llm_plants_list = [llm_plants_list]
                    for lp in llm_plants_list:
                        if lp and seed_tag in lp:
                            merged_plants.append(lp)
                            found = True
                            break
                    if not found:
                        merged_plants.append(f"在此處自然埋下伏筆線索：{plant_str}")
                        
                for payoff_str in prog["foreshadowing_payoffs"]:
                    seed_tag = payoff_str.split("]")[0] + "]"
                    found = False
                    llm_payoffs_list = llm_item.get("foreshadowing_payoffs", []) or []
                    if isinstance(llm_payoffs_list, str):
                        llm_payoffs_list = [llm_payoffs_list]
                    for lpy in llm_payoffs_list:
                        if lpy and seed_tag in lpy:
                            merged_payoffs.append(lpy)
                            found = True
                            break
                    if not found:
                        merged_payoffs.append(f"在此處自然回收並引爆前期鋪墊：{payoff_str}")
                        
                for tp_str in prog["turning_points"]:
                    tp_tag = tp_str.split("]")[0] + "]"
                    found = False
                    llm_tps_list = llm_item.get("turning_points", []) or []
                    if isinstance(llm_tps_list, str):
                        llm_tps_list = [llm_tps_list]
                    for ltp in llm_tps_list:
                        if ltp and tp_tag in ltp:
                            merged_tps.append(ltp)
                            found = True
                            break
                    if not found:
                        merged_tps.append(f"在此處觸發關鍵轉折事件：{tp_str}")
                        
                if merged_plants or merged_payoffs or merged_tps:
                    merged_list.append({
                        "chapter_index": ch_idx,
                        "foreshadowing_plants": merged_plants,
                        "foreshadowing_payoffs": merged_payoffs,
                        "turning_points": merged_tps
                    })
                    
            from db import save_foreshadowing_allocations
            save_foreshadowing_allocations(nid, merged_list)
            print(f"[DOUBLE TRACK MERGE SUCCESS] allocations merged and safely locked into DB for {nid}.")
            
        BATCH_SIZE = 10
        all_llm_allocations = []
        is_fast_mode = True
        if user_prompt and any(k in user_prompt.lower() for k in ["真實", "慢速", "完整", "llm", "slow", "full"]):
            is_fast_mode = False
            
        if is_fast_mode:
            yield "data: " + json.dumps({"type": "content", "delta": f"  ⚡ 已自動啟用【極速演算法對齊機制】...\n  🧭 正在以電腦級 100% 精準度、均勻且安全地在 {N} 章中調度 {S} 個伏筆與 {T} 個轉折點...\n  💡 (LLM 情節拋光已跳過，伏筆已以文字代碼格式直接縫合至微觀章節中以防止 HTTP 超時)\n"}, ensure_ascii=False) + "\n\n"
            merge_and_save_allocations(novel_id, [])
            yield "data: " + json.dumps({"type": "content", "delta": "\n=== [全局伏筆編織對齊完成] ===\n演算法已成功將所有伏筆與轉折精準、無遺漏地對齊分配到各章節！\n"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
            return

        from llm import call_llm_stream
        for batch_start in range(0, len(tasked_chapters), BATCH_SIZE):
            batch = tasked_chapters[batch_start: batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(tasked_chapters) + BATCH_SIZE - 1) // BATCH_SIZE
            
            yield "data: " + json.dumps({"type": "content", "delta": f"  🔀 LLM 編織批次 {batch_num}/{total_batches}（共 {len(batch)} 個章節）...\n"}, ensure_ascii=False) + "\n\n"

            from agent_assembler import run_foreshadowing_batch
            messages = run_foreshadowing_batch(batch)
            
            batch_text = ""
            for sse_line in call_llm_stream("plot", messages):
                yield sse_line
                if sse_line.startswith("data:"):
                    try:
                        data_str = sse_line[5:].strip()
                        if data_str != "[DONE]":
                            data = json.loads(data_str)
                            if data.get("type") == "content":
                                batch_text += data.get("delta", "")
                    except:
                        pass
            
            parsed_batch = parse_json_safely(batch_text)
            if isinstance(parsed_batch, dict) and "error" in parsed_batch:
                parsed_batch = parse_json_safely(clean_json_text(batch_text))
                
            if isinstance(parsed_batch, dict) and "allocations" in parsed_batch:
                all_llm_allocations.extend(parsed_batch["allocations"])
            elif isinstance(parsed_batch, list):
                all_llm_allocations.extend(parsed_batch)
                
        merge_and_save_allocations(novel_id, all_llm_allocations)
        yield "data: " + json.dumps({"type": "content", "delta": "\n=== [全局伏筆編織對齊完成] ===\n已順利將全量伏筆與關鍵轉折均勻編織分配到大綱骨架中！\n"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return main_orchestrate_gen()

def run_plot_planner(novel_id, user_prompt=None, planner_directive=None):
    """
    呼叫 Plot Planner Agent 開始微觀滾動式大綱規劃 (委託 Assembler)
    """
    from agent_assembler import assemble_and_run_plot_planner
    return assemble_and_run_plot_planner(novel_id, user_prompt, planner_directive)

def run_chapter_writer(novel_id, chapter_index, custom_style="Classic Modernism"):
    """
    呼叫 Chapter Writer Agent 開始撰寫特定章節之繁體中文小說正文 (委託 Assembler)
    """
    from agent_assembler import assemble_and_run_chapter_writer
    return assemble_and_run_chapter_writer(novel_id, chapter_index, custom_style)
