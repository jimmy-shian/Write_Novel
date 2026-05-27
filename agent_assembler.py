# -*- coding: utf-8 -*-
"""
參數組合與 Prompt 注入器 (Agent Parameter Assembler & Prompt Injector)
全後端唯一觸碰與黏合 Prompt 的解耦核心。
負責 Context 編排、Prompt 模板注入、LLM 串流啟動、JSON 清洗解析與安全存檔。
"""

import json
import re
import random
import hashlib
import db
from llm import call_llm_stream

# 匯入所有 Prompt 設定 (3個獨立 Prompt 檔案)
from prompts.prompt_main import (
    STORY_ARCHITECT_PROMPT,
    VOLUMES_PLANNER_PROMPT,
    CHARACTER_DESIGNER_PROMPT,
    VOLUME_SKELETON_PROMPT,
    PLOT_PLANNER_PROMPT,
    CHAPTER_WRITER_PROMPT
)

from prompts.prompt_detail_modifier import (
    EDITOR_PROMPT,
    INCREMENTAL_ARCHITECT_PROMPT,
    INCREMENTAL_CHARACTER_PROMPT,
    INCREMENTAL_CHARACTER_APPEND_PROMPT,
    INCREMENTAL_PLOT_PROMPT,
    VOLUME_ALIGNMENT_PROMPT,
    VOLUME_JIT_ALIGNMENT_PROMPT
)

from prompts.prompt_instructions import (
    CO_PILOT_ORCHESTRATOR_PROMPT,
    STAGE_EVALUATION_PROMPT,
    RESCUE_PROMPT,
    RETRY_PROMPT,
    DIRECTOR_COMMON_HEADER,
    DIRECTOR_COMMON_FOOTER,
    STAGE_FOCUS_WORLDVIEW,
    STAGE_FOCUS_WORLDVIEW_AT_INIT,
    STAGE_FOCUS_CHARACTERS,
    STAGE_FOCUS_VOLUMES,
    STAGE_FOCUS_SKELETONS,
    STAGE_FOCUS_PLOT,
    STAGE_FOCUS_WRITER
)

# ============================================================
# HELPER UTILITIES (輔助工具函式)
# ============================================================

def clean_json_text(text):
    """
    清洗 Markdown 區塊與無效括號，抽取乾淨 JSON
    """
    if not text:
        return ""
    if not isinstance(text, str):
        return text
        
    text = text.strip()
    if text and not text.startswith("{") and not text.startswith("["):
        if re.match(r'^\s*"\w+"\s*:', text) or re.match(r'^\s*\'\w+\'\s*:', text):
            text = "{" + text + "}"
            
    code_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    candidate = text
    if code_blocks:
        for block in reversed(code_blocks):
            block_stripped = block.strip()
            if block_stripped and not block_stripped.startswith("{") and not block_stripped.startswith("["):
                if re.match(r'^\s*"\w+"\s*:', block_stripped) or re.match(r'^\s*\'\w+\'\s*:', block_stripped):
                    block_stripped = "{" + block_stripped + "}"
            if block_stripped.startswith("{") or block_stripped.startswith("["):
                candidate = block_stripped
                break
    else:
        all_braces = re.findall(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if all_braces:
            all_braces.sort(key=len, reverse=True)
            candidate = all_braces[0].strip()
            
    try:
        json.loads(candidate)
        return candidate
    except Exception:
        pass
        
    repaired = re.sub(r':\s*([^"\s\{\[\d\-][^"\n,]*)"(?=\s*[,\}])', r': "\1"', candidate)
    repaired = re.sub(r':\s*"([^"\n,]+)(?=\s*[,\}])', r': "\1"', repaired)
    return repaired

def parse_json_safely(text, default=None):
    """
    安全解析 JSON，防範中斷崩潰
    """
    if default is None:
        default = {"error": "JSON parse failed"}
    if not text:
        return default
    if isinstance(text, (dict, list)):
        return text
        
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
        print(f"[WARN] parse_json_safely failed: {e}")
        return default

def get_core_name(name_str):
    """
    安全提取角色核心名字，過濾掉括號、身分或頭銜
    """
    if not name_str:
        return ""
    name_str = re.sub(r'[\(（].*?[\)）]', '', name_str)
    for separator in ['-', '–', '—', '_', ':', '：', ' ', '\t']:
        if separator in name_str:
            parts = name_str.split(separator)
            if parts[0].strip():
                name_str = parts[0]
    return name_str.strip()

# ============================================================
# CONTEXT COMPILATION (上下文組裝 - 集成卷規劃與伏筆矩陣)
# ============================================================

def compile_context(novel_id):
    """
    精準組裝全域創作上下文 (世界觀 + 卷規劃 + 伏筆矩陣 + 角色聖經 + 大綱 + 正文簡介)
    """
    # 1. 讀取底層世界觀設定
    wb = db.get_latest_worldbuilding(novel_id)
    worldbuilding_str = wb["content"] if wb else "No worldview defined yet."
    
    # 2. 🚨 【核心加強】：從 volumes 表讀取真實 active 篇卷規劃，以防總監缺乏卷細節資訊 🚨
    vols = db.get_volumes(novel_id)
    vols_str = ""
    if vols:
        vols_str = "\n\n【當前篇卷規劃詳細列表】：\n"
        for v in vols:
            factions_val = v.get("parsed_factions") or v.get("factions") or []
            factions_str = ", ".join(factions_val) if isinstance(factions_val, list) else str(factions_val)
            rules_val = v.get("parsed_applicable_rules") or v.get("applicable_rules") or []
            rules_text = ", ".join(rules_val) if isinstance(rules_val, list) else str(rules_val)
            vols_str += (
                f"- 第 {v.get('volume_index')} 卷《{v.get('title')}》 (規劃 {v.get('chapter_count', 50)} 章)\n"
                f"  • 篇卷概要：{v.get('summary')}\n"
                f"  • 活躍勢力：{factions_str}\n"
                f"  • 時間定位/時間軸：{v.get('time_timeline')}\n"
                f"  • 本卷適用法則：{rules_text}\n"
            )
    else:
        vols_str = "\n\n【當前篇卷規劃詳細列表】：尚無詳細篇卷設定。"

    # 3. 讀取最新角色聖經
    char = db.get_latest_characters(novel_id)
    characters_str = char["json_data"] if char else "No characters designed yet."
    
    # 4. 讀取大綱，並建立伏筆種子/轉折點分佈矩陣
    plot_data = db.get_stitched_plot(novel_id)
    _plot_summary_chapters = []
    for _ch in plot_data.get("chapters", []):
        if isinstance(_ch, dict):
            _plot_summary_chapters.append({
                "chapter_index": _ch.get("chapter_index"),
                "title": _ch.get("title", ""),
                "cliffhanger": _ch.get("cliffhanger", ""),
                "foreshadowing_plant": _ch.get("foreshadowing_plant", []),
                "foreshadowing_payoff": _ch.get("foreshadowing_payoff", []),
            })
    _plot_summary = {"chapters": _plot_summary_chapters, "_total_chapters": len(_plot_summary_chapters)}
    plot_str = json.dumps(_plot_summary, ensure_ascii=False, indent=2)
    
    # 5. 撈取已寫正文的 synopsis
    chapters_list = db.get_all_chapters_latest(novel_id)
    written_chapters_summary = ""
    for c in chapters_list:
        ch_summary = c.get("synopsis") or (c["content"][:100] + "...")
        written_chapters_summary += f"Chapter {c['chapter_index']}: {ch_summary}\n\n"
        
    if not written_chapters_summary:
        written_chapters_summary = "No chapters written yet."
        
    # 6. 計算伏筆與轉折全局演進矩陣
    wb_json = db.parse_worldview_to_json(worldbuilding_str) if wb else {}
    seeds = wb_json.get("foreshadowing_seeds", []) or []
    tps = wb_json.get("key_turning_points", []) or []
    
    seeds_roadmap = []
    for s_idx, seed in enumerate(seeds):
        plant_ch = []
        payoff_ch = []
        seed_tag = f"Seed-{s_idx+1}"
        for ch in plot_data.get("chapters", []):
            ch_idx = ch.get("chapter_index")
            ch_str = json.dumps(ch, ensure_ascii=False)
            if seed_tag in ch_str:
                alloc = ch.get("allocated_tasks", {}) or {}
                plants = alloc.get("foreshadowing_plants", []) or []
                payoffs = alloc.get("foreshadowing_payoffs", []) or []
                if not plants:
                    plants = ch.get("foreshadowing_plant", []) or []
                if not payoffs:
                    payoffs = ch.get("foreshadowing_payoff", []) or []
                if isinstance(plants, str): plants = [plants]
                if isinstance(payoffs, str): payoffs = [payoffs]
                
                is_plant = any(seed_tag in p for p in plants) or seed_tag in ch.get("foreshadowing", "")
                is_payoff = any(seed_tag in py for py in payoffs)
                
                if is_plant:
                    plant_ch.append(ch_idx)
                if is_payoff:
                    payoff_ch.append(ch_idx)
                    
        span = "無"
        if plant_ch and payoff_ch:
            span = f"{max(payoff_ch) - min(plant_ch)} 章"
            
        seeds_roadmap.append(
            f"  - [{seed_tag}] {seed[:20] + '...' if len(seed)>20 else seed}\n"
            f"    👉 埋設章節: {plant_ch if plant_ch else '未部署'} | 回收章節: {payoff_ch if payoff_ch else '未部署'} (回收跨度: {span})"
        )
        
    tps_roadmap = []
    for t_idx, tp in enumerate(tps):
        trigger_ch = []
        tp_tag = f"TurningPoint-{t_idx+1}"
        for ch in plot_data.get("chapters", []):
            ch_idx = ch.get("chapter_index")
            ch_str = json.dumps(ch, ensure_ascii=False)
            if tp_tag in ch_str:
                trigger_ch.append(ch_idx)
        tps_roadmap.append(
            f"  - [{tp_tag}] {tp[:20] + '...' if len(tp)>20 else tp} ➔ 觸發章節: {trigger_ch if trigger_ch else '未部署'}"
        )
        
    roadmap_str = "【全域伏筆分佈與情節演進矩陣】:\n"
    roadmap_str += "\n".join(seeds_roadmap) if seeds_roadmap else "  (無伏筆種子)\n"
    roadmap_str += "\n【全域關鍵轉折點分佈矩陣】:\n"
    roadmap_str += "\n".join(tps_roadmap) if tps_roadmap else "  (無關鍵轉折點)\n"
    
    return {
        "worldbuilding": worldbuilding_str + vols_str + "\n\n" + roadmap_str,
        "characters": characters_str,
        "plot": plot_str,
        "written_chapters": written_chapters_summary
    }

# ============================================================
# LLM STREAM ENGINE (SSE 串流主引擎)
# ============================================================

def run_agent_stream(novel_id, agent_name, messages, save_callback=None):
    """
    通用 LLM SSE 串流引擎，負責收集內容並非同步存入 DB。
    """
    accumulated_text = ""
    accumulated_thinking = ""
    
    for sse_line in call_llm_stream(agent_name, messages):
        yield sse_line
        
        if sse_line.startswith("data:"):
            try:
                data_str = sse_line[5:].strip()
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                if data.get("type") == "content":
                    accumulated_text += data.get("delta", "")
                elif data.get("type") == "thinking":
                    accumulated_thinking += data.get("delta", "")
            except:
                pass
                
    if save_callback and accumulated_text.strip():
        try:
            import inspect
            sig = inspect.signature(save_callback)
            if "thinking" in sig.parameters:
                save_callback(novel_id, accumulated_text, thinking=accumulated_thinking)
            else:
                save_callback(novel_id, accumulated_text)
        except Exception as e:
            print(f"Error saving in agent callback: {e}")
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"Database save failed: {str(e)}"
            }, ensure_ascii=False) + "\n\n"

# ============================================================
# MAINFLOW ASSEMBLERS (主要創作參數組合器)
# ============================================================

def assemble_and_run_story_architect(novel_id, user_prompt):
    is_revision = user_prompt and any(k in user_prompt for k in ["修改世界觀", "指示修改世界觀", "現有世界觀", "回退修改世界觀"])
    
    if is_revision:
        wb = db.get_latest_worldbuilding(novel_id)
        current_wb_json = db.parse_worldview_to_json(wb["content"] if wb else "")
        current_wb_str = json.dumps(current_wb_json, ensure_ascii=False, indent=2)
        
        revision_directive = """
⚠️【重要注意：這是一項世界觀增量修正/退回修改任務】
你目前正在對現有的世界觀進行局部精細修正與優化，而不是從頭隨意重新生成！
請務必嚴格遵循以下「防崩塌修正」紅線條款：
1. **無損保留未要求修改的全部大架構**：必須在回傳的 JSON 中，完整保留原本已經規劃好的「多幕式結構 (multi_act_structure)」、「角色登場規劃策略 (progressive_character_plan)」、「篇卷列表 (volumes) 及其 chapter_count」以及大部分「伏筆種子 (foreshadowing_seeds)」，絕不能讓原本已有的完好設定流失或被隨意覆蓋！
2. **微創手術式修正**：僅針對總監/用戶在指示中提出的具體問題、時間軸瑕疵或設定漏洞，進行局部的精確調整。
3. **維持 JSON 標準格式**：回傳的 JSON 根結構必須完整無缺，特別是 volumes 陣列的 volume_index 從 1 開始必須連續、無遺失。
"""
        messages = [
            {"role": "system", "content": STORY_ARCHITECT_PROMPT + "\n\n" + revision_directive},
            {"role": "user", "content": f"這是目前已有的世界觀設定（JSON格式）：\n{current_wb_str}\n\n請根據以下總監指示，對現有的世界觀設定進行精細的局部增量修改，並輸出完整的修改後 JSON：\n\n{user_prompt}"}
        ]
    else:
        messages = [
            {"role": "system", "content": STORY_ARCHITECT_PROMPT},
            {"role": "user", "content": f"請根據以下靈感構想，設計一部完整的小說架構：\n\n{user_prompt}"}
        ]
    
    def save_callback(nid, text):
        from incremental_patch_engine import parse_incremental_response, safe_worldbuilding_save
        parsed = parse_incremental_response(text)
        if isinstance(parsed, dict) and ("worldview" in parsed or "theme" in parsed or "main_conflict" in parsed):
            wb_data = {
                "theme": parsed.get("theme", ""),
                "main_conflict": parsed.get("main_conflict", ""),
                "worldview": parsed.get("worldview", ""),
                "multi_act_structure": parsed.get("multi_act_structure", []),
                "progressive_character_plan": parsed.get("progressive_character_plan", []),
                "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []),
                "key_turning_points": parsed.get("key_turning_points", []),
                "macro_outline": parsed.get("macro_outline", "")
            }
            for k, v in parsed.items():
                if k not in wb_data:
                    wb_data[k] = v
            
            success, version, error_msg = safe_worldbuilding_save(nid, wb_data, source="run_story_architect")
            if not success:
                raise ValueError(f"世界觀存儲安全校驗失敗：{error_msg}")
            else:
                volumes_list = parsed.get("volumes", [])
                if isinstance(volumes_list, list) and len(volumes_list) > 0:
                    db.save_volumes(nid, volumes_list)
        else:
            raise ValueError("故事架構設計生成失敗：未返回合法的結構化數據（JSON 解析失敗或格式不符）。")
            
    return run_agent_stream(novel_id, "architect", messages, save_callback)

def assemble_and_run_volumes_planner(novel_id, user_prompt=None):
    context = compile_context(novel_id)
    existing_vols = db.get_volumes(novel_id)
    is_revision = user_prompt and any(k in user_prompt for k in ["修改篇卷", "修改卷", "調整篇卷", "調整卷", "現有篇卷"])
    
    if is_revision and existing_vols:
        v_str = json.dumps([
            {
                "volume_index": v.get("volume_index"),
                "title": v.get("title"),
                "summary": v.get("summary"),
                "chapter_count": v.get("chapter_count", 50),
                "factions": v.get("parsed_factions", []),
                "time_timeline": v.get("time_timeline", ""),
                "sequence_context": v.get("sequence_context", ""),
                "applicable_rules": v.get("parsed_applicable_rules", [])
            } for v in existing_vols
        ], ensure_ascii=False, indent=2)
        
        revision_directive = """
⚠️【重要注意：這是一項篇卷增量修正/退回修改任務】
你目前正在對現有的篇卷劃分進行局部精細修正與優化，而不是從頭隨意重新生成！
請務必嚴格遵循以下「防崩塌修正」紅線條款：
1. **無損保留未要求修改的全部卷結構**：必須在回傳的 JSON 中，完整保留大部分原本已經規劃好的篇卷 title、summary 與 chapter_count，絕不能讓原本已有的完好設定流失或被隨意覆蓋！
2. **微創手術式修正**：僅針對總監/用戶在指示中提出的具體問題或章節數量調整，進行局部的精確調整。
3. **維持 JSON 標準格式**：回傳 of the JSON 根結構必須完整無缺，特別是 volumes 陣列 of volume_index 從 1 開始必須連續、無遺失。
"""
        messages = [
            {"role": "system", "content": VOLUMES_PLANNER_PROMPT + "\n\n" + revision_directive},
            {"role": "user", "content": f"世界觀設定：\n{context['worldbuilding']}\n\n已有的角色設定：\n{context['characters']}\n\n目前已有的篇卷劃分（JSON格式）：\n{v_str}\n\n請根據以下總監指示，對現有的篇卷進行增量修改，並輸出完整的 JSON：\n\n{user_prompt}"}
        ]
    else:
        prompt_content = f"以下是小說的世界觀設定與故事架構：\n{context['worldbuilding']}\n\n"
        if context['characters'] != "No characters designed yet.":
            prompt_content += f"已有的角色設定：\n{context['characters']}\n\n"
        if user_prompt:
            prompt_content += f"用戶對篇卷設定的特定要求：\n{user_prompt}\n\n"
        prompt_content += "請規劃整部小說的篇卷劃分（通常為 5-15 卷，每卷 30-100 章）。嚴格以 JSON 格式輸出。"
        
        messages = [
            {"role": "system", "content": VOLUMES_PLANNER_PROMPT},
            {"role": "user", "content": prompt_content}
        ]
        
    def save_callback(nid, text):
        from incremental_patch_engine import parse_incremental_response
        parsed = parse_incremental_response(text)
        if isinstance(parsed, dict) and "volumes" in parsed:
            volumes_list = parsed.get("volumes", [])
            if isinstance(volumes_list, list) and len(volumes_list) > 0:
                db.save_volumes(nid, volumes_list)
            else:
                raise ValueError("篇卷規劃生成為空列表")
        else:
            raise ValueError("篇卷規劃解析失敗：未返回合法的結構化 volumes 數據。")
            
    return run_agent_stream(novel_id, "architect", messages, save_callback)
    
def assemble_and_run_character_designer(novel_id, user_prompt=None):
    context = compile_context(novel_id)
    prompt_content = f"以下是已確立的世界觀與故事架構：\n{context['worldbuilding']}\n\n"
    if context['characters'] != "No characters designed yet.":
        prompt_content += f"目前已有的角色設定（供參考變更）：\n{context['characters']}\n\n"
    if user_prompt:
        prompt_content += f"用戶對角色的特定要求：\n{user_prompt}\n\n"
    prompt_content += "請設計或修正角色。嚴格以 JSON 格式輸出。"
    
    is_revision = user_prompt and any(k in user_prompt for k in ["修改角色設定", "重新設計角色", "回退修改角色", "現有角色設定", "指示重新設計角色", "新增角色"])
    
    if is_revision:
        # 優化提示詞：明確指示 AI 不需要完整生成，只需提供變更集
        revision_directive = """
⚠️【重要注意：這是一項角色聖經「增量修改 / 補充」任務】
你目前正在對已有的角色設定進行局部精細修正或增量補充。為了節省時間與提升效率，**你不需要完整生成所有未修改的舊角色**！
請務必嚴格遵循以下規範：
1. **僅輸出變更或新增項**：請在 `characters` 陣列中，只放入「需要修改欄位或設定的現有角色」或「全新增加的角色」。
2. **同名識別機制**：如果是要修改/增補現有角色，請確保 JSON 中的 `name`（姓名）與原角色完全一致，後端會自動識別並將新舊欄位進行合併（更新）；如果是新角色，請賦予一個全新的名字。
3. **維持標準 JSON 格式**：不論本次回傳的角色只有 1 個還是多個，格式必須為標準的 `{"characters": [ 僅包含新增或修改的角色項目 ]}`。
"""
        messages = [
            {"role": "system", "content": CHARACTER_DESIGNER_PROMPT + "\n\n" + revision_directive},
            {"role": "user", "content": prompt_content}
        ]
    else:
        messages = [
            {"role": "system", "content": CHARACTER_DESIGNER_PROMPT},
            {"role": "user", "content": prompt_content}
        ]
    
    def save_callback(nid, text):
        from incremental_patch_engine import parse_incremental_response, post_merge_validation
        parsed = parse_incremental_response(text)
        if isinstance(parsed, list):
            parsed = {"characters": parsed}
        elif isinstance(parsed, dict):
            for key in list(parsed.keys()):
                if key.lower() in ["characters", "character", "character_bible"]:
                    val = parsed[key]
                    if isinstance(val, list):
                        parsed = {"characters": val}
                        break
        
        if isinstance(parsed, dict) and "characters" in parsed:
            char_data = db.get_latest_characters(nid)
            original_data = char_data["parsed_data"] if (char_data and "parsed_data" in char_data) else {"characters": []}
            
            if is_revision:
                orig_chars = original_data.get("characters", [])
                new_chars = parsed.get("characters", [])
                
                merged_chars = []
                updated_names = set()
                updated_core_names = set()
                
                # 建立新變更角色的映射表，方便快速檢索
                new_chars_by_name = {nc.get("name"): nc for nc in new_chars if isinstance(nc, dict) and nc.get("name")}
                new_chars_by_core = {get_core_name(nc.get("name", "")): nc for nc in new_chars if isinstance(nc, dict) and nc.get("name")}
                
                # 階段 1：處理原有角色（判斷是「同名合併」還是「原樣保留」）
                for c in orig_chars:
                    name = c.get("name")
                    core_name = get_core_name(name) if name else ""
                    
                    # 雙軌識別：優先比對精準全名，其次比對核心姓名
                    matched = new_chars_by_name.get(name) or new_chars_by_core.get(core_name)
                    
                    if matched:
                        # 【核心變更】：識別為現有同名角色，讀取新欄位進行局部覆蓋合併
                        merged_c = c.copy()
                        merged_c.update(matched)
                        merged_chars.append(merged_c)
                        
                        if name: updated_names.add(name)
                        if core_name: updated_core_names.add(core_name)
                    else:
                        # 未被提及的舊角色，直接原樣保留
                        merged_chars.append(c)
                
                # 階段 2：處理全新角色（將未匹配到任何舊姓名的新角色追加進來）
                for nc in new_chars:
                    if isinstance(nc, dict):
                        name = nc.get("name")
                        core_name = get_core_name(name) if name else ""
                        
                        if name not in updated_names and core_name not in updated_core_names:
                            # 【核心變更】：識別為全新登場角色，直接追加到列表中
                            merged_chars.append(nc)
                            
                parsed["characters"] = merged_chars
                
                # 安全防禦：Unique Core-name 丟失檢查
                orig_cores = {get_core_name(c.get("name", "")) for c in orig_chars if c.get("name")}
                new_cores = {get_core_name(c.get("name", "")) for c in merged_chars if c.get("name")}
                orig_cores = {c for c in orig_cores if c and not any(pn in c.lower() for pn in ["新登場", "待補充", "暫無", "placeholder"])}
                lost_cores = orig_cores - new_cores
                if lost_cores:
                    error_msg = f"新角色列表丟失了原有的核心角色：{list(lost_cores)}，拒絕覆蓋！"
                    raise ValueError(error_msg)
            
            # 呼叫資料庫層的去重器進行最後的清洗防線
            from db import clean_and_deduplicate_characters
            parsed["characters"] = clean_and_deduplicate_characters(parsed["characters"])
            
            # 安全驗證（過濾掉因為不完整輸出而導致的長度、數量減少的警告）
            is_valid_merge, errors = post_merge_validation(parsed, "characters", original_data)
            if not is_valid_merge:
                filtered_errors = [e for e in errors if "count" not in e.lower() and "smaller" not in e.lower()]
                if filtered_errors:
                    raise ValueError(f"角色設計合併後驗證失敗：{', '.join(filtered_errors)}")
                
            db.save_characters(nid, parsed)
        else:
            raise ValueError(f"角色解析失敗，未返回包含 'characters' 陣列的 JSON 結構。")
            
    return run_agent_stream(novel_id, "character", messages, save_callback)
def assemble_and_run_volume_skeleton_planner(novel_id, volume_index, user_prompt=None):
    context = compile_context(novel_id)
    vols = db.get_volumes(novel_id)
    target_vol = next((v for v in vols if int(v.get("volume_index", 0)) == int(volume_index)), None)
    if not target_vol:
        raise ValueError(f"無法找到第 {volume_index} 卷的設定。")
        
    vol_title = target_vol.get("title", f"第 {volume_index} 卷")
    vol_summary = target_vol.get("summary", "")
    vol_chapter_count = int(target_vol.get("chapter_count", 50))
    
    start_ch, end_ch = db.get_volume_chapter_range(vols, int(volume_index))
    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    total_vols = len(vols)
    vol_progress = (int(volume_index) - 1) / max(total_vols - 1, 1) if total_vols > 1 else 0.0
    
    seeds_list = worldview_json.get("foreshadowing_seeds", [])
    turning_points = worldview_json.get("key_turning_points", [])
    
    focused_seeds = []
    if isinstance(seeds_list, list) and seeds_list:
        S = len(seeds_list)
        for idx, seed in enumerate(seeds_list):
            seed_pos = idx / S if S > 1 else 0.0
            if abs(seed_pos - vol_progress) <= 0.3:
                focused_seeds.append(f"[Seed-{idx + 1}] {seed}")
        if not focused_seeds:
            sorted_seeds = sorted(enumerate(seeds_list), key=lambda x: abs((x[0] / S if S > 1 else 0.0) - vol_progress))
            focused_seeds = [f"[Seed-{x[0] + 1}] {x[1]}" for x in sorted_seeds[:6]]
            
    focused_turning_points = []
    if isinstance(turning_points, list) and turning_points:
        T = len(turning_points)
        for idx, tp in enumerate(turning_points):
            tp_pos = idx / T if T > 1 else 0.0
            if abs(tp_pos - vol_progress) <= 0.3:
                focused_turning_points.append(f"[TurningPoint-{idx + 1}] {tp}")
        if not focused_turning_points:
            sorted_tps = sorted(enumerate(turning_points), key=lambda x: abs((x[0] / T if T > 1 else 0.0) - vol_progress))
            focused_turning_points = [f"[TurningPoint-{x[0] + 1}] {x[1]}" for x in sorted_tps[:6]]
            
    seeds_text = "\n".join(focused_seeds) if focused_seeds else "（尚無伏筆種子）"
    turning_points_text = "\n".join(focused_turning_points) if focused_turning_points else "（尚無關鍵轉折點）"
    
    prev_volume_context = ""
    if int(volume_index) > 1:
        prev_vol = next((v for v in vols if int(v.get("volume_index", 0)) == int(volume_index) - 1), None)
        if prev_vol:
            prev_vol_title = prev_vol.get("title", f"第 {volume_index - 1} 卷")
            prev_vol_summary = prev_vol.get("summary", "")
            prev_volume_context = f"\n\n【前卷銜接參考 - 第 {volume_index - 1} 卷《{prev_vol_title}》】\n{prev_vol_summary}\n本卷應承接前卷結尾的張力與懸念。"
            
    prompt_content = f"""
卷設定：
- 卷標題：{vol_title}
- 卷概要：{vol_summary}
- 本卷章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {vol_chapter_count} 章）
{prev_volume_context}

世界觀設定：
主題：{worldview_json.get("theme", "未設定")}
核心衝突：{worldview_json.get("main_conflict", "未設定")}
世界觀背景：{worldview_json.get("worldview", "未設定")}

本卷相關伏筆種子：
{seeds_text}

本卷相關關鍵轉折點：
{turning_points_text}
"""
    messages = [
        {"role": "system", "content": VOLUME_SKELETON_PROMPT.format(volume_index=volume_index, start_ch=start_ch, end_ch=end_ch, vol_chapter_count=vol_chapter_count)},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if isinstance(parsed, dict) and "chapters_skeleton" in parsed:
            db.save_volume_skeletons(nid, volume_index, parsed["chapters_skeleton"])
            
    return run_agent_stream(novel_id, "plot", messages, save_callback)

def run_foreshadowing_batch(batch_chapters):
    tasked_text = json.dumps(batch_chapters, ensure_ascii=False, indent=2)
    prompt = f"""
你是大長篇小說的伏筆編織大師與情節對齊導演。
我們已經透過系統精準分配演算法，為小說中的特定章節規劃好了伏筆與轉折指派任務。

## 任務
請審查以下『已被指派任務的章節清單』（本批共 {len(batch_chapters)} 個章節）。
針對每一個章節，將被指派的 [Seed-X] 或 [TurningPoint-Y] 任務，結合該章節的 brief_title 與 brief_summary，自然融合地撰寫具體文學性的敘事描述。
你的任務是將這些指派內容，拋光為優雅、自然融入情節的大綱敘事文字！

## ⚠️ 重要編織原則
1. **無損保留指派**：不要修改或遺漏被指派的 seed / turning_points 編號（例如 `[Seed-1]`, `[TurningPoint-2]`），這些編號必須完整保留在你的文字描述中！
2. **自然融入**：撰寫 1-2 句具體描述，說明伏筆是如何在情節中自然出現的。
3. **保持 JSON 格式**：你必須嚴格輸出 JSON 格式，其根結構包含一個 `allocations` 陣列。

## 指派任務的章節清單
{tasked_text}

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
```json
{{
  "allocations": [
    {{
      "chapter_index": 5,
      "foreshadowing_plants": ["主角在廢墟中拾獲刻有神秘符文的晶片 [Seed-1]，晶片微弱的魔力殘留引起了主角的注意..."],
      "foreshadowing_payoffs": [],
      "turning_points": []
    }}
  ]
}}
```
"""
    messages = [
        {"role": "system", "content": "你是一位嚴謹的小說伏筆編織導演，精通將線索自然織入情節骨架中。你必須完全以 JSON 格式回應，不說 any 廢話。"},
        {"role": "user", "content": prompt}
    ]
    return messages

def assemble_and_run_plot_planner(novel_id, user_prompt=None, planner_directive=None):
    context = compile_context(novel_id)
    
    # 進行滾動大綱規劃 (Chunk Generator) 本體邏輯
    plot = db.get_latest_plot_chapters(novel_id)
    existing_chapters = []
    if plot and "parsed_data" in plot:
        existing_chapters = plot["parsed_data"].get("chapters", [])
    if not isinstance(existing_chapters, list):
        existing_chapters = []
    
    def existing_chapter_index(ch):
        try:
            return int(ch.get("chapter_index", 0)) if isinstance(ch, dict) else 999999
        except (TypeError, ValueError):
            return 999999

    existing_chapters.sort(key=existing_chapter_index)
    existing_chapters = [ch for ch in existing_chapters if existing_chapter_index(ch) != 999999]

    last_chapter_index = 0
    if existing_chapters:
        last_chapter_index = existing_chapter_index(existing_chapters[-1])

    repair_start_candidates = []
    for written_chapter in db.get_all_chapters_latest(novel_id):
        try:
            if int(written_chapter.get("is_dirty", 0)) == 1:
                repair_start_candidates.append(int(written_chapter.get("chapter_index")))
        except (TypeError, ValueError):
            pass

    for vol in db.get_volumes(novel_id):
        try:
            if int(vol.get("is_dirty", 0)) == 1:
                start_ch, _ = db.get_volume_chapter_range(db.get_volumes(novel_id), int(vol.get("volume_index")))
                repair_start_candidates.append(start_ch)
        except (TypeError, ValueError):
            pass

    from agent_main import _looks_like_placeholder_chapter
    for ch in existing_chapters:
        try:
            ch_idx = int(ch.get("chapter_index"))
        except (TypeError, ValueError, AttributeError):
            continue
        if _looks_like_placeholder_chapter(ch):
            repair_start_candidates.append(ch_idx)

    is_revision = False
    extracted_start_chapter = None
    
    if planner_directive:
        is_revision = True
    elif user_prompt and any(k in user_prompt for k in ["請根據以下指示重新規劃", "重新規劃大綱", "修改大綱", "退回大綱"]):
        is_revision = True
        match = re.search(r'(?:重新規劃大綱|修改大綱|退回大綱)：?\s*\n*(.*?)\n*現有大綱：', user_prompt, re.DOTALL)
        if match:
            planner_directive = match.group(1).strip()
        else:
            planner_directive = user_prompt

    if is_revision:
        vol_match = re.search(r'(?:第|volume\s*)\s*(\d+)\s*(?:卷|vol)', (planner_directive or "") + (user_prompt or ""), re.IGNORECASE)
        ch_match = re.search(r'(?:第|chapter\s*)\s*(\d+)\s*(?:章|ch)', (planner_directive or "") + (user_prompt or ""), re.IGNORECASE)
        
        if ch_match:
            try:
                extracted_start_chapter = int(ch_match.group(1))
            except ValueError:
                pass
        elif vol_match:
            try:
                vol_idx = int(vol_match.group(1))
                volumes = db.get_volumes(novel_id)
                start_ch, _ = db.get_volume_chapter_range(volumes, vol_idx)
                extracted_start_chapter = start_ch
            except Exception:
                pass
                
        if extracted_start_chapter is not None:
            repair_start_candidates.append(extracted_start_chapter)
        else:
            if existing_chapters:
                repair_start_candidates.append(max(1, last_chapter_index - 1))
            else:
                repair_start_candidates.append(1)

    if repair_start_candidates:
        start_chapter = max(1, min(repair_start_candidates))
        existing_chapters = [
            ch for ch in existing_chapters
            if existing_chapter_index(ch) < start_chapter
        ]
        last_chapter_index = start_chapter - 1
    else:
        start_chapter = last_chapter_index + 1
        
    end_chapter = start_chapter + 1
    expected_count = end_chapter - start_chapter + 1
    
    prev_chapters_context = ""
    if existing_chapters:
        last_few = existing_chapters[-3:]
        prev_chapters_context = "【前文已生成的章節大綱銜接參考】:\n"
        for ch in last_few:
            prev_chapters_context += f"- 第 {ch.get('chapter_index')} 章《{ch.get('title')}》: {ch.get('summary')} (懸念: {ch.get('cliffhanger')})\n"

    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    volumes = db.get_volumes(novel_id)
    total_chapters = db.get_total_chapter_count(volumes)
    progress_percentage = min(max((start_chapter - 1) / total_chapters, 0.0), 1.0)
    
    ta_list = worldview_json.get("multi_act_structure", [])
    active_act_index = min(int(progress_percentage * len(ta_list)), len(ta_list) - 1) if ta_list else 0
    ta_text = ""
    for idx, act in enumerate(ta_list):
        title = act.get("title", f"項目 #{idx + 1}")
        content = act.get("content", "").strip()
        if idx < active_act_index:
            ta_text += f"- [已完成前文結構] 第 {idx + 1} 幕: {title}\n"
        elif idx == active_act_index:
            ta_text += f"- [🌟 當前主攻幕] 第 {idx + 1} 幕: {title}\n  【核心劇情與情節任務】：{content}\n"
        else:
            ta_text += f"- [未來預告結構] 第 {idx + 1} 幕: {title} (後續大綱的鋪墊方向，當前僅供伏線參考，暫勿在此展開)\n"

    cp_list = worldview_json.get("progressive_character_plan", [])
    active_stage_index = min(int(progress_percentage * len(cp_list)), len(cp_list) - 1) if cp_list else 0
    cp_text = ""
    for idx, stage in enumerate(cp_list):
        title = stage.get("title", f"階段 #{idx + 1}")
        content = stage.get("content", "").strip()
        if idx < active_stage_index:
            cp_text += f"- [已歷經成長階段] 階段 {idx + 1}: {title}\n"
        elif idx == active_stage_index:
            cp_text += f"- [🌟 當前主要成長重點] 階段 {idx + 1}: {title}\n  【心境成長與核心轉變】：{content}\n"
        else:
            cp_text += f"- [未來成長預告] 階段 {idx + 1}: {title} (後續轉變方向，當前僅作細微暗示，暫勿完全爆發)\n"

    seeds_list = worldview_json.get("foreshadowing_seeds", [])
    turning_points = worldview_json.get("key_turning_points", [])

    focused_seeds = []
    if isinstance(seeds_list, list) and seeds_list:
        S = len(seeds_list)
        for idx, seed in enumerate(seeds_list):
            seed_pos = idx / S if S > 1 else 0.0
            if abs(seed_pos - progress_percentage) <= 0.25:
                focused_seeds.append(f"[Seed-{idx + 1}] {seed}")
        if len(focused_seeds) < 4:
            sorted_seeds = sorted(enumerate(seeds_list), key=lambda x: abs((x[0] / S if S > 1 else 0.0) - progress_percentage))
            focused_seeds = [f"[Seed-{x[0] + 1}] {x[1]}" for x in sorted_seeds[:4]]

    focused_turning_points = []
    if isinstance(turning_points, list) and turning_points:
        T = len(turning_points)
        for idx, tp in enumerate(turning_points):
            tp_pos = idx / T if T > 1 else 0.0
            if abs(tp_pos - progress_percentage) <= 0.25:
                focused_turning_points.append(f"[TurningPoint-{idx + 1}] {tp}")
        if len(focused_turning_points) < 4:
            sorted_tps = sorted(enumerate(turning_points), key=lambda x: abs((x[0] / T if T > 1 else 0.0) - progress_percentage))
            focused_turning_points = [f"[TurningPoint-{x[0] + 1}] {x[1]}" for x in sorted_tps[:4]]

    seeds_text = "\n".join(focused_seeds) if focused_seeds else "  (無目前適合發展的伏筆)"
    tps_text = "\n".join(focused_turning_points) if focused_turning_points else "  (無目前適合發展的轉折)"

    vol_idx = db.get_chapter_volume_index(volumes, start_chapter)
    current_vol = next((v for v in volumes if v["volume_index"] == vol_idx), None)
    current_vol_text = ""
    if current_vol:
        current_vol_text = f"""【當前大綱規劃聚焦篇卷：第 {vol_idx} 卷《{current_vol.get('title')}》】
篇卷核心情節概要與高潮方向：
{current_vol.get('summary')}
活躍勢力：{current_vol.get('factions')}
本卷大綱骨架與伏筆分配任務表（請務必嚴格執行此分配任務！）：
"""
        from db import get_all_volume_skeletons
        all_sk = get_all_volume_skeletons(novel_id)
        sk_list = [s for s in all_sk if int(s.get("volume_index", -1)) == int(vol_idx)]
        for sk in sk_list:
            ch_idx = sk.get("chapter_index")
            if start_chapter <= ch_idx <= end_chapter:
                alloc = sk.get("allocated_tasks", {}) or {}
                current_vol_text += f"- 第 {ch_idx} 章骨架：《{sk.get('brief_title')}》\n"
                current_vol_text += f"  • 里程碑目的：{sk.get('brief_summary')}\n"
                if alloc.get("foreshadowing_plants"):
                    current_vol_text += f"  • ⚠️ 【硬性指定埋設伏筆】：{alloc['foreshadowing_plants']}\n"
                if alloc.get("foreshadowing_payoffs"):
                    current_vol_text += f"  • ⚠️ 【硬性指定回收伏筆】：{alloc['foreshadowing_payoffs']}\n"
                if alloc.get("turning_points"):
                    current_vol_text += f"  • ⚠️ 【硬性指定觸發轉折】：{alloc['turning_points']}\n"

    revision_context = ""
    if is_revision and planner_directive:
        revision_context = f"""
⚠️【重要：這是大綱微創局部修補任務】
使用者/總監提出了以下大綱修正指示，你必須完美在規劃第 {start_chapter} 至 {end_chapter} 章大綱時融合此要求：
💡 【修正指示】：{planner_directive}
"""

    prompt_content = f"""
【全域世界觀核心設定】
核心主題：{worldview_json.get("theme", "無")}
核心衝突：{worldview_json.get("main_conflict", "無")}
世界觀環境：{worldview_json.get("worldview", "無")}

【動態故事起承轉合進度 (全書當前大綱進度約 {int(progress_percentage * 100)}%)】
{ta_text}

【角色群像當前心境階段進度】
{cp_text}

【滑動窗口動態篩選 - 當前階段最適合引入/回收的伏筆種子池】
{seeds_text}

【滑動窗口動態篩選 - 當前階段最適合觸發的轉折點池】
{tps_text}

{current_vol_text}
{prev_chapters_context}
{revision_context}
已有的角色人設聖經：
{context['characters']}

請嚴格為接下來的第 {start_chapter} 章至第 {end_chapter} 章大綱進行精細的微觀場景與事件編排，只輸出符合格式的 JSON，不要包含 any 解釋。
"""
    messages = [
        {"role": "system", "content": PLOT_PLANNER_PROMPT},
        {"role": "user", "content": prompt_content}
    ]

    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if isinstance(parsed, dict) and "error" in parsed:
            parsed = parse_json_safely(clean_json_text(text))
            
        from agent_main import _normalize_chapter_outlines
        node_chapters = _normalize_chapter_outlines(parsed, start_chapter, expected_count=expected_count)
        
        if node_chapters:
            from incremental_patch_engine import validate_incremental_payload
            is_valid_payload, err_msg = validate_incremental_payload("plot", {"chapters": node_chapters}, "PATCH")
            if is_valid_payload:
                # 融合原有大綱
                merged_full_chapters = existing_chapters + node_chapters
                # 按章節排序
                merged_full_chapters.sort(key=lambda x: int(x.get("chapter_index", 0)))
                # 寫回 DB
                db.save_plot_chapters(nid, {"chapters": merged_full_chapters})
            else:
                raise ValueError(f"章節大綱校準驗證失敗：{err_msg}")
        else:
            raise ValueError("滾動式大綱生成失敗：未返回合法的 JSON 大綱。")
            
    # 開始 streamAPI
    yield "data: " + json.dumps({"type": "content", "delta": f"=== [滾動式大綱生成] ===\n目前已規劃 {last_chapter_index} 章。正在規劃接下來的第 {start_chapter} 章至第 {end_chapter} 章大綱...\n\n"}, ensure_ascii=False) + "\n\n"
    for chunk in run_agent_stream(novel_id, "plot", messages, save_callback):
        yield chunk

def assemble_and_run_chapter_writer(novel_id, chapter_index, custom_style):
    context = compile_context(novel_id)
    plot_json = parse_json_safely(context['plot'])
    
    current_chapter_outline = None
    if "chapters" in plot_json:
        for ch in plot_json["chapters"]:
            if ch.get("chapter_index") == int(chapter_index):
                current_chapter_outline = ch
                break
                
    if not current_chapter_outline:
        raise ValueError(f"無法找到第 {chapter_index} 章的大綱設定。")
        
    prev_chapters_summary = ""
    written_chaps = db.get_all_chapters_latest(novel_id)
    for c in written_chaps:
        if int(c["chapter_index"]) < int(chapter_index):
            ch_summary = c.get("synopsis") or (c["content"][:100] + "...")
            prev_chapters_summary += f"第 {c['chapter_index']} 章正文劇情梗概：{ch_summary}\n\n"
            
    vols = db.get_volumes(novel_id)
    target_vol_idx = db.get_chapter_volume_index(vols, int(chapter_index))
    target_vol = next((v for v in vols if v["volume_index"] == target_vol_idx), None)
    
    vol_context = ""
    if target_vol:
        vol_context = f"\n\n【當前寫作所屬篇卷精確定位資訊】：\n- 篇卷名稱：《{target_vol.get('title')}》\n- 篇卷概要定位：{target_vol.get('summary')}\n- 陣營局勢：{target_vol.get('factions')}\n- 必須遵守的世界法則限制：{target_vol.get('applicable_rules') or '無'}"

    prompt_content = f"""
【寫作參考之世界觀設定】
{context['worldbuilding']}{vol_context}
 
【寫作參考之核心角色聖經設定】
{context['characters']}
 
【前章正文劇情進度梗概（承接因果）】
{prev_chapters_summary if prev_chapters_summary else "（本章為小說開篇第一章，無前文背景，請大膽開篇）"}
 
【本章寫作必須嚴格遵守的微觀章節大綱】
{json.dumps(current_chapter_outline, ensure_ascii=False, indent=2)}
"""
    messages = [
        {"role": "system", "content": CHAPTER_WRITER_PROMPT.format(writing_style=custom_style)},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text, thinking=""):
        from db import save_chapter, apply_worldview_patch, mark_subsequent_dirty
        content = text
        inline_thinking = ""
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            
        special_words = ["[START_OF_PROSE]", "[正文開始]"]
        for sw in special_words:
            if sw in content:
                parts = content.split(sw, 1)
                inline_thinking = (inline_thinking + "\n" + parts[0].strip()).strip()
                content = parts[1].strip()
                break
                
        final_thinking = (thinking.strip() + "\n" + inline_thinking.strip()).strip()
        
        law_pattern = r'\[NEW_WORLD_LAW:\s*([^\]\-]+?)\s*-\s*([^\]]+?)\]'
        laws = re.findall(law_pattern, content)
        if laws:
            for cat, details in laws:
                apply_worldview_patch(nid, cat.strip(), details.strip())
            mark_subsequent_dirty(nid, int(chapter_index))
            
        content = re.sub(law_pattern, '', content).strip()
        from agent_main import generate_chapter_synopsis
        synopsis = generate_chapter_synopsis(content)
        save_chapter(nid, int(chapter_index), content, synopsis, final_thinking)
        
    return run_agent_stream(novel_id, "writer", messages, save_callback)

# ============================================================
# EXTENSION & DIRECTOR ASSEMBLERS (擴增與總監參數組合器)
# ============================================================

def get_simplified_director_prompt(current_stage, has_wb_and_char_at_init=False):
    """
    動態生成各階段的特化 system prompt。
    """
    stage_focus = ""
    if current_stage in ["init", "worldview", "worldview_review", "worldview_go_back"]:
        stage_focus = STAGE_FOCUS_WORLDVIEW
        if has_wb_and_char_at_init:
            stage_focus += STAGE_FOCUS_WORLDVIEW_AT_INIT
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        stage_focus = STAGE_FOCUS_CHARACTERS
    elif current_stage in ["volumes", "volumes_review", "volumes_go_back"]:
        stage_focus = STAGE_FOCUS_VOLUMES
    elif current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align", "volume_skeleton", "foreshadowing_orchestration"]:
        stage_focus = STAGE_FOCUS_SKELETONS
    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        stage_focus = STAGE_FOCUS_PLOT
    elif current_stage in ["writer", "writer_review"]:
        stage_focus = STAGE_FOCUS_WRITER
    else:
        stage_focus = "\n## 💡 當前審核重點：【常規階段把關】\n1. 檢查目前產出的資料是否合格。若無誤請決策 CONTINUE。\n"
        
    return DIRECTOR_COMMON_HEADER + stage_focus + "\n{pre_check}\n\n## 系統底層結構完整性與情節邏輯校驗報告\n{validation_report}\n\n## 用戶原始創作需求\n{user_prompt}\n" + DIRECTOR_COMMON_FOOTER

def assemble_and_run_volume_jit_alignment(novel_id, volume_index):
    """
    非同步 JIT 篇卷大綱對齊機制 (包含雙軌安全重試與診斷)
    """
    context = compile_context(novel_id)
    patches = db.get_worldview_patches(novel_id)
    patches_str = json.dumps(patches, ensure_ascii=False, indent=2) if patches else "尚無新世界規律補丁設定。"
    
    volumes = db.get_volumes(novel_id)
    current_vol = next((v for v in volumes if v["volume_index"] == volume_index), None)
    if not current_vol:
        def error_gen():
            yield "data: " + json.dumps({"type": "error", "message": f"找不到第 {volume_index} 篇卷設定。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return error_gen()
        
    prev_chapters_context = "這是整部小說的開篇第一卷，無前卷大綱銜接參考。"
    if volume_index > 1:
        prev_vol = next((v for v in volumes if v["volume_index"] == volume_index - 1), None)
        if prev_vol and prev_vol["chapters_outline"]:
            try:
                prev_outline = json.loads(prev_vol["chapters_outline"])
                if isinstance(prev_outline, list) and len(prev_outline) > 0:
                    last_few = prev_outline[-3:]
                    prev_chapters_context = "【前卷結尾章節銜接參考】:\n"
                    for ch in last_few:
                        prev_chapters_context += f"- 第 {ch.get('chapter_index')} 章《{ch.get('title')}》: {ch.get('summary')} (懸念: {ch.get('cliffhanger')})\n"
            except:
                pass
                
    start_chapter, end_chapter = db.get_volume_chapter_range(volumes, volume_index)
    volume_ch_count = end_chapter - start_chapter + 1
    
    total_volumes = len(volumes) if volumes else 10
    total_chapters = db.get_total_chapter_count(volumes)
    progress_percentage = min(max((int(start_chapter) - 1) / total_chapters, 0.0), 1.0)
    
    current_volume_details = ""
    if current_vol:
        v_rules = current_vol.get("applicable_rules") or []
        if isinstance(v_rules, str):
            try:
                v_rules = json.loads(v_rules)
            except:
                v_rules = [v_rules]
        rules_text = "\n  - ".join(v_rules) if v_rules else "無特定世界法則限制"
        current_volume_details = f"""【🌟 當前篇卷故事精準定位資訊】：
- 故事時間軸起迄定位：{current_vol.get('time_timeline') or '承接前文，持續推進'}
- 系列續作情節定位：{current_vol.get('sequence_context') or '主要故事衝突階段'}
- 本卷必須遵守的世界法則與陣營規則：
  - {rules_text}"""
  
    def _sse_content(delta_text):
        return "data: " + json.dumps({"type": "content", "delta": delta_text}, ensure_ascii=False) + "\n\n"
        
    def _sse_error(err_text):
        return "data: " + json.dumps({"type": "error", "message": err_text}, ensure_ascii=False) + "\n\n"

    def jit_gen():
        yield _sse_content(f"=== [篇卷大綱 JIT 對齊啟動] ===\n正在針對第 {volume_index} 卷《{current_vol['title']}》進行 {volume_ch_count} 章節微觀大綱 JIT 校準對齊...\n")
        
        narrative_stage = "開篇 (Setup)" if progress_percentage <= 0.2 else "發展/衝突升級 (Confrontation)" if progress_percentage <= 0.8 else "高潮/收尾 (Resolution)"
        
        prompt = VOLUME_JIT_ALIGNMENT_PROMPT.format(
            current_volume_details=current_volume_details,
            worldbuilding=context['worldbuilding'],
            patches_str=patches_str,
            characters=context['characters'],
            total_chapters=total_chapters,
            volume_index=volume_index,
            total_volumes=total_volumes,
            progress_percentage=int(progress_percentage * 100),
            narrative_stage=narrative_stage,
            volume_ch_count=volume_ch_count,
            volume_title=current_vol['title'],
            volume_summary=current_vol['summary'],
            volume_factions=current_vol['factions'],
            prev_chapters_context=prev_chapters_context,
            start_chapter=start_chapter,
            end_chapter=end_chapter
        )
        
        messages = [
            {"role": "system", "content": "你是一位頂尖的微觀劇情規劃大師。你只輸出嚴格、合法、無多餘寒暄的標準 JSON 陣列數據。"},
            {"role": "user", "content": prompt}
        ]
        
        accumulated_text = ""
        for sse_line in call_llm_stream("plot", messages):
            yield sse_line
            if sse_line.startswith("data:"):
                try:
                    data_str = sse_line[5:].strip()
                    if data_str != "[DONE]":
                        data = json.loads(data_str)
                        if data.get("type") == "content":
                            accumulated_text += data.get("delta", "")
                except:
                    pass
                    
        parsed = parse_json_safely(accumulated_text)
        if isinstance(parsed, dict) and "error" in parsed:
            parsed = parse_json_safely(clean_json_text(accumulated_text))
            
        from agent_main import _normalize_chapter_outlines
        node_chapters = _normalize_chapter_outlines(parsed, start_chapter, expected_count=volume_ch_count)
            
        if node_chapters:
            for idx, ch in enumerate(node_chapters):
                ch["chapter_index"] = start_chapter + idx
                
            from incremental_patch_engine import validate_incremental_payload
            is_valid_payload, err_msg = validate_incremental_payload("plot", {"chapters": node_chapters}, "PATCH")
            if is_valid_payload:
                db.update_volume_outline(novel_id, volume_index, node_chapters)
                yield _sse_content(f"\n\n✓ 第 {volume_index} 卷對齊與規劃完成！已成功儲存 {len(node_chapters)} 章大綱。\n")
            else:
                yield _sse_error(f"第 {volume_index} 卷大綱校準驗證失敗：{err_msg}；啟動救援機制。\n")
                node_chapters = None
        
        if not node_chapters:
            yield _sse_content(f"\n\n⚠️ 第 {volume_index} 卷 JIT 對齊失敗；停止保底佔位，改請總監救援診斷並重新操作。\n")
            
            rescue_prompt = RESCUE_PROMPT.format(
                volume_index=volume_index,
                volume_title=current_vol['title'],
                volume_ch_count=volume_ch_count,
                worldbuilding=context['worldbuilding'],
                patches_str=patches_str,
                characters=context['characters'],
                volume_summary=current_vol['summary'],
                volume_factions=current_vol['factions'],
                current_volume_details=current_volume_details,
                start_chapter=start_chapter,
                end_chapter=end_chapter
            )
            
            messages_rescue = [
                {"role": "system", "content": "你是一位頂尖的流程救援官，專門診斷生成失敗並給出行動指令。請嚴格輸出合法的 JSON，不說 any 廢話。"},
                {"role": "user", "content": rescue_prompt}
            ]
            
            rescue_output = ""
            for chunk in call_llm_stream("copilot", messages_rescue):
                if chunk.startswith("data:"):
                    try:
                        data_str = chunk[5:].strip()
                        if data_str != "[DONE]":
                            data = json.loads(data_str)
                            if data.get("type") == "content":
                                rescue_output += data.get("delta", "")
                    except:
                        pass
                        
            parsed_rescue = parse_json_safely(rescue_output)
            if isinstance(parsed_rescue, dict) and "error" in parsed_rescue:
                parsed_rescue = parse_json_safely(clean_json_text(rescue_output))
                
            planner_directive = parsed_rescue.get("planner_directive") if isinstance(parsed_rescue, dict) else None
            if not planner_directive:
                planner_directive = f"請遵循第 {volume_index} 卷的簡易章大綱，並融入最新世界觀規律，編寫 {volume_ch_count} 個章節。"
                
            yield _sse_content(f"  🎬 總監診斷完畢。診斷原因：{parsed_rescue.get('diagnosis', '未知格式錯誤')}；最新決策指令：{planner_directive}\n  🚨 正在進行第二次安全重試生成...\n")
            
            retry_prompt = RETRY_PROMPT.format(
                worldbuilding=context['worldbuilding'],
                patches_str=patches_str,
                characters=context['characters'],
                volume_index=volume_index,
                volume_title=current_vol['title'],
                volume_summary=current_vol['summary'],
                volume_ch_count=volume_ch_count,
                current_volume_details=current_volume_details,
                prev_chapters_context=prev_chapters_context,
                planner_directive=planner_directive,
                start_chapter=start_chapter,
                end_chapter=end_chapter
            )
            
            messages_retry = [
                {"role": "system", "content": "你是一位頂尖的小說大綱精細調度師。你只輸出嚴格、合法、無多餘寒暄的標準 JSON 陣列數據。"},
                {"role": "user", "content": retry_prompt}
            ]
            
            retry_text = ""
            for chunk in call_llm_stream("plot", messages_retry):
                yield chunk
                if chunk.startswith("data:"):
                    try:
                        data_str = chunk[5:].strip()
                        if data_str != "[DONE]":
                            data = json.loads(data_str)
                            if data.get("type") == "content":
                                retry_text += data.get("delta", "")
                    except:
                        pass
                        
            parsed_retry = parse_json_safely(retry_text)
            if isinstance(parsed_retry, dict) and "error" in parsed_retry:
                parsed_retry = parse_json_safely(clean_json_text(retry_text))
                
            node_chapters = _normalize_chapter_outlines(parsed_retry, start_chapter, expected_count=volume_ch_count)
            if node_chapters:
                for idx, ch in enumerate(node_chapters):
                    ch["chapter_index"] = start_chapter + idx
                db.update_volume_outline(novel_id, volume_index, node_chapters)
                yield _sse_content(f"\n\n✓ JIT 雙軌對齊安全重寫存檔成功！已成功部署第 {volume_index} 卷的 {len(node_chapters)} 章大綱。\n")
            else:
                yield _sse_error(f"\n\n❌ [JIT ALIGN FATAL] 重試亦無法產出合法大綱；終止寫作，改為拋出 runtime error。\n")
                
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return jit_gen()
