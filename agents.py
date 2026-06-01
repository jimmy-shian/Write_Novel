# -*- coding: utf-8 -*-
"""
AI Novel Factory Agent Runner Functions
Implements the 6-stage golden axis of creation:
Worldview -> Character -> Volume -> Skeleton -> Outline -> Writing
Reinforced with JSON schemas and custom Director hooks.
All prompt construction is delegated to prompts.prompt_builder.
"""

import json
import os
import re
import db
from llm import call_llm_stream
from models.client import call_llm_sync, call_llm_json

# --- IMPORT SECURE PROMPT BUILDERS ---
from prompts.prompt_builder import (
    get_json_schema_prompt_snippet,
    build_story_architect_messages,
    build_character_designer_messages,
    build_volumes_planner_messages,
    build_volume_skeleton_planner_messages,
    build_plot_planner_messages,
    build_chapter_writer_messages,
    build_editor_agent_messages,
    build_copilot_chat_messages,
    build_director_decision_messages,
    build_director_decision_help_messages,
    build_incremental_architect_messages,
    build_incremental_character_messages,
    build_incremental_plot_planner_messages,
    extract_worldview_summary
)


# =============================================================================
# 1. Worldview Agent (Story Architect)
# =============================================================================
def run_story_architect(novel_id, user_prompt):
    """
    Worldview Stage: Generate worldview based on user's story setting.
    """
    novel = db.get_novel(novel_id)
    genre = novel.get("genre", "Fantasy")
    style = novel.get("style", "Classic Modernism")
    
    messages = build_story_architect_messages(genre, style, user_prompt)
    
    # Store chat history
    db.save_chat_message(novel_id, "user", f"開始生成世界觀。要求: {user_prompt}", message_type="pipeline")
    
    # Run streaming
    stream = call_llm_stream("architect", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    # Save output to database
    if full_text.strip():
        db.save_worldbuilding(novel_id, full_text)
        db.save_chat_message(novel_id, "assistant", f"世界觀生成成功！版本已更新。", message_type="pipeline")


# =============================================================================
# 2. Character Designer Agent
# =============================================================================
def run_character_designer(novel_id, user_prompt=None, hint=None, mode="generate", target_char_index=None):
    """
    Character Stage:
    - Mode 'generate': Generate characters based on worldview summary.
    - Mode 'expand': Character expansion using general prompt + director's critique hint.
    - Mode 'modify': Character modification requires hint + original character's full JSON.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要，避免過長導致 API 失敗
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    
    existing_char_data = db.get_latest_characters(novel_id)
    existing_chars_json = existing_char_data["json_data"] if existing_char_data else "{'characters': []}"
    
    messages = build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index)
    
    db.save_chat_message(novel_id, "user", f"執行角色設計。模式: {mode}, 指示: {user_prompt or hint}", message_type="pipeline")
    
    stream = call_llm_stream("character", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        db.save_characters(novel_id, full_text)
        db.save_chat_message(novel_id, "assistant", f"角色聖經更新完畢！版本已更新。", message_type="pipeline")


# =============================================================================
# 3. Volumes Planner Agent
# =============================================================================
def run_volumes_planner(novel_id, user_prompt=None, hint=None, mode="generate", target_vol_idx=None):
    """
    Volumes Planner Stage:
    - Mode 'generate': Generate volumes list based on worldview summary + outline of preceding & succeeding 1 volumes.
    - Mode 'patch': Volume patch/add: passes hint and specifies generating only `[idx]`.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    
    existing_vols = db.get_volumes(novel_id)
    
    messages = build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx)
    
    db.save_chat_message(novel_id, "user", f"執行篇卷規劃。模式: {mode}, 卷數: {target_vol_idx or '全書'}", message_type="pipeline")
    
    stream = call_llm_stream("volumes", messages) # Map to volumes model for volumes planning
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        # Parse and save volumes
        from models.parsers import extract_json_block
        parsed_vols = extract_json_block(full_text)
        vols_list = parsed_vols.get("volumes", []) if isinstance(parsed_vols, dict) else (parsed_vols if isinstance(parsed_vols, list) else [])
        
        if vols_list:
            if mode == "patch" and target_vol_idx is not None:
                # Merge the patched volume into existing volumes
                merged_vols = {v["volume_index"]: v for v in existing_vols}
                for pv in vols_list:
                    pv_idx = pv.get("volume_index", target_vol_idx)
                    pv["volume_index"] = pv_idx
                    merged_vols[pv_idx] = pv
                db.save_volumes(novel_id, list(merged_vols.values()), clear_downstream=False)
            else:
                db.save_volumes(novel_id, vols_list, clear_downstream=True)
            
            # 預計算全局伏筆與轉折藍圖
            try:
                db.precompute_global_foreshadowing(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to precompute global foreshadowing in run_volumes_planner: {e}")
                
        db.save_chat_message(novel_id, "assistant", f"篇卷結構已儲存成功！", message_type="pipeline")


# =============================================================================
# 4. Volume Skeleton Planner Agent
# =============================================================================
def run_volume_skeleton_planner(novel_id, volume_index, user_prompt=None):
    """
    Volume Skeleton Stage:
    Generate skeleton based on:
    - worldview summary
    - outline of preceding & succeeding 1 volumes
    - pre-calculated use/retrieval operations of clues/turns for this volume
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    worldview_parsed = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    
    all_vols = db.get_volumes(novel_id)
    current_vol = next((v for v in all_vols if v["volume_index"] == volume_index), None)
    if not current_vol:
        raise ValueError(f"Volume index {volume_index} not found!")
        
    start_ch, end_ch = db.get_volume_chapter_range(all_vols, volume_index)
    vol_chapter_count = end_ch - start_ch + 1
    
    # Preceding and succeeding volume context
    pre_vol = next((v for v in all_vols if v["volume_index"] == volume_index - 1), None)
    next_vol = next((v for v in all_vols if v["volume_index"] == volume_index + 1), None)
    
    surrounding_context = ""
    if pre_vol:
        surrounding_context += f"\n【前 1 卷 (卷 {volume_index - 1}) 大綱概要】\n{pre_vol['summary']}\n"
    if next_vol:
        surrounding_context += f"\n【後 1 卷 (卷 {volume_index + 1}) 大綱概要】\n{next_vol['summary']}\n"
        
    # Pre-calculated use/retrieval operations of clues/turns for this volume
    all_seeds = worldview_parsed.get("foreshadowing_seeds", [])
    all_turns = worldview_parsed.get("key_turning_points", [])
    
    # 載入全局預計算的伏筆與轉折藍圖
    blueprint = db.get_global_foreshadowing_blueprint(novel_id)
    T = blueprint.get("T", 120)
    foreshadowing_allocations = blueprint.get("foreshadowing_allocations", [])
    turning_allocations = blueprint.get("turning_allocations", [])

    # Volume Slicing
    allocated_plants = []
    allocated_payoffs = []
    allocated_turns = []

    # Detailed assigned tasks by chapter inside current volume chapter range [start_ch, end_ch]
    assigned_tasks_by_chapter = {}
    for c in range(start_ch, end_ch + 1):
        assigned_tasks_by_chapter[c] = {"plants": [], "payoffs": [], "turns": []}

    for idx, seed in enumerate(all_seeds):
        P, R = foreshadowing_allocations[idx]
        if start_ch <= P <= end_ch:
            R_vol_idx = db.get_chapter_volume_index(all_vols, R)
            plant_msg = f"⚠️ 【硬性指定埋設伏筆】：[Seed-{idx+1}] {seed}。注意：此線索未來將在第 {R_vol_idx} 卷（絕對第 {R} 章）進行回收！"
            allocated_plants.append(plant_msg)
            assigned_tasks_by_chapter[P]["plants"].append(plant_msg)
        if start_ch <= R <= end_ch:
            P_vol_idx = db.get_chapter_volume_index(all_vols, P)
            payoff_msg = f"⚠️ 【硬性指定回收伏筆】：[Seed-{idx+1}] {seed}。別怕，這根線索當初在遙遠的第 {P_vol_idx} 卷（絕對第 {P} 章）就已經埋好了，你這卷只管完成因果收網就好！"
            allocated_payoffs.append(payoff_msg)
            assigned_tasks_by_chapter[R]["payoffs"].append(payoff_msg)

    for jdx, turn in enumerate(all_turns):
        K = turning_allocations[jdx]
        if start_ch <= K <= end_ch:
            turn_msg = f"配合指定關鍵轉折點進展：{turn} (絕對第 {K} 章)"
            allocated_turns.append(turn_msg)
            assigned_tasks_by_chapter[K]["turns"].append(turn_msg)

    # Format precalc_clues for prompt inject
    clues_lines = []
    for c in range(start_ch, end_ch + 1):
        tasks = assigned_tasks_by_chapter[c]
        if tasks["plants"] or tasks["payoffs"] or tasks["turns"]:
            clues_lines.append(f"- 第 {c} 章任務要求：")
            for p in tasks["plants"]:
                clues_lines.append(f"  * {p}")
            for rf in tasks["payoffs"]:
                clues_lines.append(f"  * {rf}")
            for t in tasks["turns"]:
                clues_lines.append(f"  * {t}")

    if clues_lines:
        precalc_clues = "【預先計算好的本卷各章伏筆與轉折硬性操作安排（你必須嚴格在對應 chapter_index 的 allocated_tasks 欄位中原封不動地填入這些要求！）】\n" + "\n".join(clues_lines)
    else:
        precalc_clues = "【預先計算好的本卷伏筆與轉折操作安排】\n本卷無特殊預算伏筆或轉折任務安排。"

    messages = build_volume_skeleton_planner_messages(
        worldview_text, volume_index, current_vol, start_ch, end_ch, vol_chapter_count,
        surrounding_context, precalc_clues, user_prompt
    )
    
    db.save_chat_message(novel_id, "user", f"生成第 {volume_index} 卷骨架大綱。章節範圍: {start_ch} - {end_ch}", message_type="pipeline")
    
    stream = call_llm_stream("volume_skeleton", messages) # Map to volume skeleton model
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        # Parse and save outline JSON to database in volume record
        from models.parsers import extract_json_block
        parsed_skeleton = extract_json_block(full_text)
        chapters_skeleton = parsed_skeleton.get("chapters_skeleton", []) if isinstance(parsed_skeleton, dict) else (parsed_skeleton if isinstance(parsed_skeleton, list) else [])
        
        if chapters_skeleton:
            db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
        db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷簡易骨架大綱已更新成功！", message_type="pipeline")


def build_missing_character_designer_messages(worldview_summary, existing_chars_json, new_char_name, chapter_outline):
    schema = {
        "name": "",
        "role": "",
        "entry_phase": "",
        "personality": [],
        "want": "",
        "need": "",
        "fatal_flaw": "",
        "motivation": "",
        "arc": "",
        "speech_style": "",
        "appearance": "",
        "background": "",
        "relationships": []
    }
    
    # 僅提取現有角色的名稱與角色定位，節省 Token 並防範衝突
    existing_names_str = "暫無角色"
    if existing_chars_json:
        try:
            from prompts.prompt_builder import extract_character_names_list
            names = extract_character_names_list(existing_chars_json)
            if names:
                existing_names_str = ", ".join(names)
        except Exception:
            pass
            
    system_prompt = f"""你是一位頂尖的角色設計大師（Character Designer）。
請根據世界觀背景與新角色首次登場的詳細章節大綱，為新登場的角色【{new_char_name}】設計一個具備深度與心理層次的角色卡設定。

⚠️【剛性約束項目】：
1. 輸出格式必須嚴格是 JSON，符合以下角色 Schema：
{json.dumps(schema, ensure_ascii=False, indent=2)}
2. name 欄位必須是角色的具體姓名【{new_char_name}】，絕對禁止填寫無關名稱。
3. 角色的人設、動機 (motivation)、致命缺陷 (fatal_flaw)、發聲風格 (speech_style) 必須與章節大綱的情境完全契合，且不可與現有的其他角色衝突。
"""
    user_content = f"""【世界觀背景大綱】
{worldview_summary}

【現有已登場角色清單 (避免人設重複或名稱衝突)】
{existing_names_str}

【新角色【{new_char_name}】登場的第 {chapter_outline.get('chapter_index')} 章詳細大綱】
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

請為新角色【{new_char_name}】生成高品質的完整角色 JSON 卡片。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


# =============================================================================
# 5. Plot Planner Agent (Detailed Outline)
# =============================================================================
def collect_referenced_indices(chapters_list):
    """
    從前1、後1及當前大綱或骨架中，動態收集所有被關聯/分配的伏筆與轉折點索引 (1-based)。
    """
    seed_indices = set()
    turn_indices = set()
    
    for ch in chapters_list:
        if not isinstance(ch, dict):
            continue
        tasks = ch.get("allocated_tasks", {}) or {}
        if not isinstance(tasks, dict):
            if isinstance(tasks, str):
                try:
                    tasks = json.loads(tasks)
                except:
                    tasks = {}
            else:
                tasks = {}
                
        # 收集 foreshadowing_plants 和 foreshadowing_payoffs
        for key in ["foreshadowing_plants", "foreshadowing_payoffs"]:
            items = tasks.get(key) or []
            if not isinstance(items, list):
                items = [items]
            for item in items:
                if isinstance(item, int):
                    seed_indices.add(item)
                elif isinstance(item, str):
                    match = re.search(r'(?:Seed|伏筆)?[-_\s]*(\d+)', item, re.IGNORECASE)
                    if match:
                        seed_indices.add(int(match.group(1)))
                        
        # 收集 turning_points
        turns = tasks.get("turning_points") or []
        if not isinstance(turns, list):
            turns = [turns]
        for item in turns:
            if isinstance(item, int):
                turn_indices.add(item)
            elif isinstance(item, str):
                match = re.search(r'(?:Turn|轉折點)?[-_\s]*(\d+)', item, re.IGNORECASE)
                if match:
                    turn_indices.add(int(match.group(1)))
                    
    return seed_indices, turn_indices


def filter_worldview_seeds_and_turns(worldview_text, seed_indices, turn_indices):
    """
    解析世界觀文本 JSON，僅保留被指定/分配的伏筆種子與轉折點，其餘過濾移除，避免干擾 LLM。
    """
    cleaned = worldview_text.strip()
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    
    # 清理 markdown code blocks
    if "```" in cleaned:
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if json_match:
            cleaned = json_match.group(1).strip()
        else:
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace != -1:
                cleaned = cleaned[first_brace:last_brace + 1].strip()
                
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            # 篩選 foreshadowing_seeds
            seeds = parsed.get("foreshadowing_seeds", [])
            filtered_seeds = []
            for idx, seed in enumerate(seeds):
                if (idx + 1) in seed_indices:
                    filtered_seeds.append(seed)
            parsed["foreshadowing_seeds"] = filtered_seeds
            
            # 篩選 key_turning_points
            turns = parsed.get("key_turning_points", [])
            filtered_turns = []
            for idx, turn in enumerate(turns):
                if (idx + 1) in turn_indices:
                    filtered_turns.append(turn)
            parsed["key_turning_points"] = filtered_turns
            
            from db import _convert_obj_to_traditional
            parsed = _convert_obj_to_traditional(parsed)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] filter_worldview_seeds_and_turns failed: {e}")
        
    return worldview_text


def _get_plot_review_batch_size():
    """Director plot review cadence. Defaults to 3 chapters per review batch."""
    raw = os.getenv("PLOT_REVIEW_BATCH_SIZE", "3")
    try:
        val = int(raw)
        return val if val > 0 else 3
    except Exception:
        return 3


def _normalize_chapter_list(chapters):
    normalized = []
    for idx, ch in enumerate(chapters or []):
        if not isinstance(ch, dict):
            continue
        item = dict(ch)
        try:
            raw_idx = item.get("chapter_index") or item.get("chapter") or item.get("chapter_number") or item.get("index") or item.get("id") or (idx + 1)
            item["chapter_index"] = int(raw_idx)
        except Exception:
            item["chapter_index"] = idx + 1
        normalized.append(item)
    normalized.sort(key=lambda x: x["chapter_index"])
    return normalized


def _is_detailed_outline(chapter):
    events = chapter.get("events") or chapter.get("scenes")
    return isinstance(events, list) and len(events) > 0


def _collect_volume_skeleton_chapters(novel_id):
    skeleton_chapters = []
    for vol in db.get_volumes(novel_id):
        ch_list = vol.get("chapters_outline")
        if isinstance(ch_list, list):
            skeleton_chapters.extend(ch_list)
    return _normalize_chapter_list(skeleton_chapters)


def _skeleton_snapshot(chapter):
    keep_keys = [
        "chapter_index", "chapter_title", "brief_title", "title", "name",
        "chapter_summary", "brief_summary", "summary",
        "allocated_tasks", "time_setting", "time_span", "scene", "location"
    ]
    return {k: chapter.get(k) for k in keep_keys if k in chapter and chapter.get(k) not in (None, "")}


def run_plot_planner(novel_id, chapter_index=None, user_prompt=None, planner_directive=None):
    """
    Detailed Outline Stage:
    Generate detailed chapter outline based on:
    - worldview summary (or complete worldview if needed)
    - skeleton outline of preceding & succeeding 1 chapters
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 使用世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    print("worldview_text:", len(worldview_text), worldview_text[:100] + "...")
    # Retrieve all volume skeletons to build continuous chapter contexts
    all_vols = db.get_volumes(novel_id)
    all_skeleton_chapters = []
    for v in all_vols:
        if v.get("chapters_outline"):
            ch_list = v["chapters_outline"]
            if isinstance(ch_list, list):
                all_skeleton_chapters.extend(ch_list)
                
    # 💡 核心修復：標準化所有骨架章節的 chapter_index，避免因鍵名不一致導致前後章節比對錯誤
    normalized_skeleton_chapters = []
    for idx, ch in enumerate(all_skeleton_chapters):
        if not isinstance(ch, dict):
            continue
        try:
            raw_idx = ch.get("chapter_index") or ch.get("chapter") or ch.get("chapter_number") or ch.get("index") or ch.get("id") or (idx + 1)
            ch["chapter_index"] = int(raw_idx)
        except:
            ch["chapter_index"] = idx + 1
        normalized_skeleton_chapters.append(ch)
            
    normalized_skeleton_chapters.sort(key=lambda x: x["chapter_index"])
    
    if not normalized_skeleton_chapters:
        normalized_skeleton_chapters = [{"chapter_index": 1, "brief_title": "開篇第一章", "brief_summary": "主角登場與初始世界展現"}]
        
    skeleton_context_list = []
    if chapter_index is not None:
        try:
            chapter_index = int(chapter_index)
        except:
            chapter_index = None
            
    if chapter_index is not None:
        # 僅篩選當前章節、前一章與後一章進行精細大綱設計，避免大綱資訊膨脹
        target_indices = {chapter_index - 1, chapter_index, chapter_index + 1}
        filtered_chapters = [ch for ch in normalized_skeleton_chapters if ch.get("chapter_index") in target_indices]
        
        # 💡 核心修復：僅將前1、後1及當前章節關聯的伏筆與轉折過濾保留在 worldview 中，排除其餘無關數據以精簡 context
        seed_indices, turn_indices = collect_referenced_indices(filtered_chapters)
        worldview_text = filter_worldview_seeds_and_turns(worldview_text, seed_indices, turn_indices)
        
        for ch in filtered_chapters:
            c_idx = ch["chapter_index"]
            role_label = ""
            if c_idx == chapter_index - 1:
                role_label = "【前一章骨架參考】"
            elif c_idx == chapter_index + 1:
                role_label = "【後一章骨架參考】"
            else:
                role_label = "【當前待規劃大綱目標章節】"
                
            title = ch.get("chapter_title") or ch.get("brief_title") or ch.get("title") or ch.get("name") or ""
            summary = ch.get("chapter_summary") or ch.get("brief_summary") or ch.get("summary") or ""
            wv_item = f"{role_label} 第 {c_idx} 章：【{title}】\n  - 本章骨架概要：{summary}\n"
            wv_item += f"  - 伏筆任務安排：{json.dumps(ch.get('allocated_tasks', {}), ensure_ascii=False)}\n"
            skeleton_context_list.append(wv_item)
    else:
        for ch in normalized_skeleton_chapters:
            c_idx = ch["chapter_index"]
            title = ch.get("chapter_title") or ch.get("brief_title") or ch.get("title") or ch.get("name") or ""
            summary = ch.get("chapter_summary") or ch.get("brief_summary") or ch.get("summary") or ""
            wv_item = f"第 {c_idx} 章：【{title}】\n  - 本章骨架概要：{summary}\n"
            wv_item += f"  - 伏筆任務安排：{json.dumps(ch.get('allocated_tasks', {}), ensure_ascii=False)}\n"
            skeleton_context_list.append(wv_item)
            
    skeleton_contexts = "\n\n".join(skeleton_context_list)
    
    # 建立動態精確要求 prompt
    effective_user_prompt = user_prompt
    if chapter_index is not None:
        target_ch = next((ch for ch in normalized_skeleton_chapters if ch.get("chapter_index") == chapter_index), None)
        brief_title = ""
        brief_summary = ""
        if target_ch:
            brief_title = target_ch.get("chapter_title") or target_ch.get("brief_title") or target_ch.get("title") or target_ch.get("name") or ""
            brief_summary = target_ch.get("chapter_summary") or target_ch.get("brief_summary") or target_ch.get("summary") or ""
        
        chapter_instructions = f"\n\n👉 【請特別注意】：此時你只需且必須為「第 {chapter_index} 章」生成詳細的情節大綱！\n第 {chapter_index} 章暫定標題為：【{brief_title}】，簡易骨架大綱為：{brief_summary}。\n請仔細查看前一章和後一章的骨架上下文，專門為第 {chapter_index} 章生成符合結構的詳細大綱 JSON 欄位（例如 title, chapter_index, events, cliffhanger, characters_active, purpose, time_setting, time_span, foreshadowing_plant, foreshadowing_payoff, turning_points 等）。"
        if user_prompt:
            effective_user_prompt = user_prompt + chapter_instructions
        else:
            effective_user_prompt = f"請根據簡易骨架大綱，為第 {chapter_index} 章生成高品質的詳細大綱 JSON。{chapter_instructions}"
            
    messages = build_plot_planner_messages(worldview_text, skeleton_contexts, effective_user_prompt, target_chapter_index=chapter_index)
    print("messages:", len(messages), messages)
    db.save_chat_message(novel_id, "user", f"生成詳細章節大綱 (第 {chapter_index if chapter_index is not None else '全書'} 章)。要求: {user_prompt or '依骨架展開'}", message_type="pipeline")
    
    stream = call_llm_stream("plot", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        from models.parsers import extract_json_block
        parsed_plot = extract_json_block(full_text)
        
        if chapter_index is not None:
            # 智慧提取單個章節
            target_ch_outline = None
            if isinstance(parsed_plot, dict):
                if "chapters" in parsed_plot and isinstance(parsed_plot["chapters"], list) and len(parsed_plot["chapters"]) > 0:
                    target_ch_outline = parsed_plot["chapters"][0]
                elif "chapter_index" in parsed_plot or "title" in parsed_plot or "events" in parsed_plot:
                    target_ch_outline = parsed_plot
            elif isinstance(parsed_plot, list) and len(parsed_plot) > 0:
                target_ch_outline = parsed_plot[0]
                
            if target_ch_outline:
                db.save_single_plot_chapter(novel_id, chapter_index, target_ch_outline)
                db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章詳細大綱已保存成功！", message_type="pipeline")
                
                # 自動補齊大綱中出現但未在角色列表中登記的角色人設
                try:
                    active_names = target_ch_outline.get("characters_active", []) or target_ch_outline.get("characters", [])
                    if isinstance(active_names, str):
                        active_names = [active_names]
                    active_names = [str(n).strip() for n in active_names if n]
                    
                    char_data = db.get_latest_characters(novel_id)
                    existing_chars_parsed = char_data.get("parsed_data") if char_data else None
                    if not existing_chars_parsed or not isinstance(existing_chars_parsed, dict):
                        existing_chars_parsed = {"characters": []}
                    existing_chars_list = existing_chars_parsed.get("characters", [])
                    
                    existing_names = {c.get("name", "").strip() for c in existing_chars_list if c.get("name")}
                    
                    missing_chars = []
                    for name in active_names:
                        if not name:
                            continue
                        if name not in existing_names and not any(name in en or en in name for en in existing_names):
                            missing_chars.append(name)
                            
                    if missing_chars:
                        db.save_chat_message(novel_id, "assistant", f"🔍 偵測到第 {chapter_index} 章大綱中出現新登場角色：{', '.join(missing_chars)}。正在呼叫角色 Agent 補齊人設設定...", message_type="pipeline")
                        
                        worldview_summary = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
                        
                        for missing_name in missing_chars:
                            char_messages = build_missing_character_designer_messages(
                                worldview_summary,
                                json.dumps(existing_chars_parsed, ensure_ascii=False),
                                missing_name,
                                target_ch_outline
                            )
                            
                            new_char_card = call_llm_json("character", char_messages)
                            if new_char_card and isinstance(new_char_card, dict) and new_char_card.get("name"):
                                existing_chars_list.append(new_char_card)
                                db.save_chat_message(novel_id, "assistant", f"👤 角色 Agent 已成功為新角色【{missing_name}】補齊人設設定！", message_type="pipeline")
                            else:
                                fallback_card = {
                                    "name": missing_name,
                                    "role": "登場配角",
                                    "entry_phase": f"第 {chapter_index} 章",
                                    "personality": ["待補充"],
                                    "want": "待補充",
                                    "need": "待補充",
                                    "fatal_flaw": "無",
                                    "motivation": "無",
                                    "arc": "無",
                                    "speech_style": "普通",
                                    "appearance": "普通",
                                    "background": "待補充",
                                    "relationships": []
                                }
                                existing_chars_list.append(fallback_card)
                                db.save_chat_message(novel_id, "assistant", f"👤 角色 Agent 為【{missing_name}】生成設定時遇到異常，已使用保底人設模板！", message_type="pipeline")
                        
                        db.save_characters(novel_id, {"characters": existing_chars_list})
                        db.save_chat_message(novel_id, "assistant", f"✅ 角色列表 JSON 已更新完畢！共新增 {len(missing_chars)} 位角色設定。", message_type="pipeline")
                except Exception as ex:
                    print(f"[ERROR] Failed to auto-supplement missing characters: {ex}")
        else:
            db.save_plot_chapters(novel_id, parsed_plot, clear_chapters=True)
            db.save_chat_message(novel_id, "assistant", f"詳細大綱已保存成功！", message_type="pipeline")


# =============================================================================
# 6. Chapter Writer Agent
# =============================================================================
def run_chapter_writer(novel_id, chapter_index, custom_style="Classic Modernism"):
    """
    Writing Stage:
    Generate prose based on:
    - worldview summary
    - writing style (user setting)
    - current chapter's detailed outline
    - detailed outline of preceding & succeeding 1 volumes (or nearby chapters)
    - clue retrieval details of the next 3 chapters (if any) + writing content where clue is retrieved
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    
    char_data = db.get_latest_characters(novel_id)
    characters_bible = char_data["json_data"] if char_data else "尚無角色設定"
    
    plot_data = db.get_stitched_plot(novel_id)
    chapters_outlines = plot_data.get("chapters", []) if plot_data else []
    
    # 💡 核心修復：在 Chapter Writer 階段，同樣標準化大綱中所有章節的 chapter_index，避免前後章節比對與查找錯誤
    normalized_outlines = []
    for idx, ch in enumerate(chapters_outlines):
        if not isinstance(ch, dict):
            continue
        try:
            raw_idx = ch.get("chapter_index") or ch.get("chapter") or ch.get("chapter_number") or ch.get("index") or ch.get("id") or (idx + 1)
            ch["chapter_index"] = int(raw_idx)
        except:
            ch["chapter_index"] = idx + 1
        normalized_outlines.append(ch)
        
    normalized_outlines.sort(key=lambda x: x["chapter_index"])
    
    current_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index), None)
    if not current_outline:
        current_outline = {
            "chapter_index": chapter_index,
            "title": f"第 {chapter_index} 章",
            "time_setting": "故事時間",
            "time_span": "緊接前文",
            "events": [{"scene": "發生場景", "action": "核心情節", "consequence": "引發後果"}],
            "purpose": "推進情節",
            "characters_active": []
        }
        
    pre_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index - 1), None)
    nxt_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index + 1), None)
    
    # 💡 核心修復：精簡角色聖經，僅傳入當前章節大綱中出現（活躍）的角色設定，避免上下文膨脹與人設混淆
    try:
        active_names = current_outline.get("characters_active", []) or current_outline.get("characters", [])
        if isinstance(active_names, str):
            active_names = [active_names]
        active_names = [str(n).strip() for n in active_names if n]
        
        if active_names and characters_bible != "尚無角色設定":
            parsed_chars = json.loads(characters_bible) if isinstance(characters_bible, str) else characters_bible
            chars_list = parsed_chars.get("characters", []) if isinstance(parsed_chars, dict) else []
            
            filtered_chars = []
            for c in chars_list:
                c_name = c.get("name", "").strip()
                if c_name and any(c_name in name or name in c_name for name in active_names):
                    filtered_chars.append(c)
                    
            if filtered_chars:
                characters_bible = json.dumps({"characters": filtered_chars}, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] Failed to filter active characters: {e}")
    
    surrounding_plot = ""
    if pre_ch_outline:
        surrounding_plot += f"\n【前一章 (第 {chapter_index - 1} 章) 詳細大綱】\n{json.dumps(pre_ch_outline, ensure_ascii=False, indent=2)}\n"
    if nxt_ch_outline:
        surrounding_plot += f"\n【後一章 (第 {chapter_index + 1} 章) 詳細大綱】\n{json.dumps(nxt_ch_outline, ensure_ascii=False, indent=2)}\n"
        
    all_vols = db.get_volumes(novel_id)
    curr_vol_idx = db.get_chapter_volume_index(all_vols, chapter_index)
    pre_vol = next((v for v in all_vols if v["volume_index"] == curr_vol_idx - 1), None)
    next_vol = next((v for v in all_vols if v["volume_index"] == curr_vol_idx + 1), None)
    
    vol_outline_context = ""
    if pre_vol:
        vol_outline_context += f"\n【前一卷 (第 {curr_vol_idx - 1} 卷) 全卷概要】\n標題：{pre_vol['title']}\n大綱：{pre_vol['summary']}\n"
    if next_vol:
        vol_outline_context += f"\n【後一卷 (第 {curr_vol_idx + 1} 卷) 全卷概要】\n標題：{next_vol['title']}\n大綱：{next_vol['summary']}\n"
        
    clue_payoff_details = ""
    next_three_chaps = [ch for ch in normalized_outlines if chapter_index < ch["chapter_index"] <= chapter_index + 3]
    payoff_clues = []
    for ch in next_three_chaps:
        payoffs = ch.get("foreshadowing_payoff", []) or ch.get("allocated_tasks", {}).get("foreshadowing_payoffs", [])
        if payoffs:
            payoff_clues.append(f"第 {ch.get('chapter_index')} 章預計收回的伏筆：{json.dumps(payoffs, ensure_ascii=False)}")
            
    if payoff_clues:
        clue_payoff_details = "\n【後三章預計將要收回的伏筆內容與寫作線索】\n" + "\n".join(payoff_clues) + "\n*(寫作時請合理埋設對應的前置鋪墊，使後續收回顯得自然流暢)*\n"

    messages = build_chapter_writer_messages(
        worldview_text, characters_bible, current_outline, surrounding_plot,
        vol_outline_context, clue_payoff_details, custom_style, chapter_index
    )
    
    db.save_chat_message(novel_id, "user", f"開始寫作第 {chapter_index} 章。風格: {custom_style}", message_type="pipeline")
    
    stream = call_llm_stream("writer", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        prose_val = full_text
        thinking_val = ""
        special_words = ["[START_OF_PROSE]", "[正文開始]"]
        for sw in special_words:
            idx = full_text.find(sw)
            if idx != -1:
                thinking_val = full_text[:idx].strip()
                prose_val = full_text[idx + len(sw):].strip()
                break
                
        db.save_chapter(novel_id, chapter_index, prose_val, synopsis=current_outline.get("title", f"第 {chapter_index} 章"), thinking=thinking_val)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文寫作完成！", message_type="pipeline")


# =============================================================================
# 7. Editor Agent
# =============================================================================
def run_editor_agent(novel_id, chapter_index, edit_instructions=None):
    """
    Editor Stage:
    Polishes/edits the chapter prose using Senior Editor, replacing the original content directly.
    """
    chapter_data = db.get_latest_chapter(novel_id, chapter_index)
    if not chapter_data:
        raise ValueError(f"Chapter {chapter_index} prose not found for editing!")
        
    original_prose = chapter_data.get("content", "")
    current_synopsis = chapter_data.get("synopsis", "")
    
    messages = build_editor_agent_messages(chapter_index, edit_instructions, original_prose)
    
    db.save_chat_message(novel_id, "user", f"調用編輯姬潤色第 {chapter_index} 章。指示: {edit_instructions}", message_type="pipeline")
    
    stream = call_llm_stream("editor", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        db.save_chapter(novel_id, chapter_index, full_text, synopsis=current_synopsis)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文已成功潤色替換！", message_type="pipeline")


# =============================================================================
# 8. Copilot / Director Orchestration
# =============================================================================
def run_copilot_chat(novel_id, user_message):
    """
    AI Copilot Chat: User speaks, Copilot analyzes intent, recommends best flow, and chats.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 由於 MAX_WORLDVIEW_SUMMARY_LENGTH = 999999，extract_worldview_summary 會保留完整設定
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    
    # 透過 Python 動態偵測階段，修復先前 current_stage 未定義 Bug
    current_stage = db.detect_current_stage(novel_id)
    
    if current_stage == "volumes":
        vols = db.get_volumes(novel_id)
        plot_text = json.dumps({"volumes": vols}, ensure_ascii=False, indent=2) if vols else "尚無篇卷規劃"
    else:
        plot_data = db.get_stitched_plot(novel_id)
        plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else "尚無章節大綱"
    
    # 建立系統記憶歷史以保證上下文連貫
    history = db.get_chat_memory(novel_id, limit=10)
    history_context = ""
    for h in history:
        history_context += f"【{h['role']}】：{h['content']}\n"

    # 生成 Python 剛性指標檢查報告
    validation_report = db.generate_validation_report(novel_id)

    messages = build_copilot_chat_messages(
        worldview_text, characters_text, plot_text, history_context, user_message, 
        validation_report=validation_report
    )
    
    db.save_chat_message(novel_id, "user", user_message, message_type="chat")
    
    stream = call_llm_stream("copilot", messages)
    accumulated = []
    thinking_accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
                elif data.get("type") == "thinking":
                    thinking_accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    full_thinking = "".join(thinking_accumulated)
    if full_text.strip():
        db.save_chat_message(novel_id, "assistant", full_text, thinking=full_thinking if full_thinking.strip() else None, message_type="chat")


# =============================================================================
# 9. Director Decision Checks (Pipeline Gatekeeper)
# =============================================================================
def run_director_decision(novel_id, current_stage, user_prompt, chapter_index=None):
    """
    Gateway review after a stage completes. Returns next action:
    CONTINUE, AUTO_REGENERATE, GO_BACK_TO_WORLDVIEW, GO_BACK_TO_CHARACTERS, GO_BACK_TO_PLOT, WAIT_USER, FINISH.
    """
    if not current_stage or current_stage == "init":
        current_stage = db.detect_current_stage(novel_id)
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = wb["content"] if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    
    if chapter_index is not None:
        try:
            chapter_index = int(chapter_index)
        except:
            chapter_index = None
            
    plot_text = ""
    written_chapters_text = ""
    
    if current_stage == "worldview":
        plot_text = "世界觀審查階段"
    elif current_stage == "characters":
        plot_text = "角色審查階段"
    elif current_stage == "volumes":
        vols = db.get_volumes(novel_id)
        plot_text = json.dumps(vols, ensure_ascii=False, indent=2) if vols else "尚無篇卷規劃"
    elif current_stage == "volume_skeleton":
        # volume_skeleton: 完整骨架(每2卷一組)
        vols = db.get_volumes(novel_id)
        plot_text = json.dumps(vols, ensure_ascii=False, indent=2) if vols else "尚無骨架規劃"
    elif current_stage == "plot":
        # plot: batch review. For batch size 3 and current chapter 6,
        # send detailed outlines 4-6 plus skeleton context 3-7.
        plot_data = db.get_stitched_plot(novel_id)
        chapters_outlines = plot_data.get("chapters", []) if plot_data else []
        normalized_outlines = _normalize_chapter_list(chapters_outlines)
        detailed_outlines = [ch for ch in normalized_outlines if _is_detailed_outline(ch)]
        skeleton_outlines = _collect_volume_skeleton_chapters(novel_id)
        
        batch_size = _get_plot_review_batch_size()
        if chapter_index is None:
            chapter_index = max([ch["chapter_index"] for ch in detailed_outlines], default=1)
        
        detail_start = max(1, chapter_index - batch_size + 1)
        detail_end = chapter_index
        skeleton_start = max(1, detail_start - 1)
        skeleton_end = detail_end + 1
        
        detailed_batch = [
            ch for ch in detailed_outlines
            if detail_start <= ch["chapter_index"] <= detail_end
        ]
        skeleton_context = [
            _skeleton_snapshot(ch) for ch in skeleton_outlines
            if skeleton_start <= ch["chapter_index"] <= skeleton_end
        ]
        
        if not skeleton_context:
            skeleton_context = [
                _skeleton_snapshot(ch) for ch in normalized_outlines
                if skeleton_start <= ch["chapter_index"] <= skeleton_end
            ]
        
        review_payload = {
            "review_batch_size": batch_size,
            "current_completed_chapter_index": chapter_index,
            "detailed_outline_context_range": f"第 {detail_start} 章至第 {detail_end} 章",
            "skeleton_context_range": f"第 {skeleton_start} 章至第 {skeleton_end} 章",
            "detailed_outlines_generated_for_review": detailed_batch,
            "skeleton_outlines_for_before_after_context": skeleton_context
        }
        plot_text = json.dumps(review_payload, ensure_ascii=False, indent=2)
        
        worldview_text = extract_worldview_summary(worldview_text)
        target_chaps = detailed_batch + skeleton_context
        seed_indices, turn_indices = collect_referenced_indices(target_chaps)
        worldview_text = filter_worldview_seeds_and_turns(worldview_text, seed_indices, turn_indices)
            
    elif current_stage == "writer":
        # writer: 該章的完整內容(正文+大綱+角色聖經+伏筆)
        plot_data = db.get_stitched_plot(novel_id)
        chapters_outlines = plot_data.get("chapters", []) if plot_data else []
        
        normalized_outlines = []
        for idx, ch in enumerate(chapters_outlines):
            if not isinstance(ch, dict):
                continue
            try:
                raw_idx = ch.get("chapter_index") or ch.get("chapter") or ch.get("chapter_number") or ch.get("index") or (idx + 1)
                ch["chapter_index"] = int(raw_idx)
            except:
                ch["chapter_index"] = idx + 1
            normalized_outlines.append(ch)
            
        target_ch_idx = chapter_index if chapter_index is not None else 1
        curr_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == target_ch_idx), None)
        
        chapter_data = db.get_latest_chapter(novel_id, target_ch_idx)
        prose_content = chapter_data.get("content", "") if chapter_data else "（無寫作正文內容）"
        
        writer_review_data = {
            "chapter_index": target_ch_idx,
            "chapter_title": curr_ch_outline.get("title", f"第 {target_ch_idx} 章") if curr_ch_outline else f"第 {target_ch_idx} 章",
            "detailed_outline": curr_ch_outline if curr_ch_outline else "（尚未生成詳細大綱）",
            "allocated_tasks_and_clues": curr_ch_outline.get("allocated_tasks", {}) if curr_ch_outline else {},
            "prose_text": prose_content
        }
        
        plot_text = json.dumps(writer_review_data, ensure_ascii=False, indent=2)
        written_chapters_text = prose_content
        
    elif current_stage == "editor":
        # editor: 該章的完整潤色與比較內容
        target_ch_idx = chapter_index if chapter_index is not None else 1
        
        # Get polished (latest) and original (second latest) chapter versions
        latest_chapter = db.get_latest_chapter(novel_id, target_ch_idx)
        polished_prose = latest_chapter.get("content", "") if latest_chapter else "（無寫作正文內容）"
        
        second_latest = db.get_second_latest_chapter(novel_id, target_ch_idx)
        original_prose = second_latest.get("content", "") if second_latest else polished_prose # Fallback to polished if no previous version exists
        
        edit_instructions = db.get_latest_edit_instructions(novel_id, target_ch_idx)
        
        editor_review_data = {
            "chapter_index": target_ch_idx,
            "edit_instructions": edit_instructions,
            "original_prose": original_prose,
            "polished_prose": polished_prose
        }
        
        plot_text = json.dumps(editor_review_data, ensure_ascii=False, indent=2)
        written_chapters_text = polished_prose
        
    else:
        plot_data = db.get_stitched_plot(novel_id)
        plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else "尚無章節大綱"
        written_ch = db.get_all_chapters_latest(novel_id)
        written_chapters_text = f"已完成正文章節數：{len(written_ch)} 章"
        
    # 生成 Python 剛性指標檢查報告
    validation_report = db.generate_validation_report(novel_id)
    
    messages = build_director_decision_messages(
        current_stage, worldview_text, characters_text, plot_text, written_chapters_text, 
        user_prompt, validation_report
    )
    
    stream = call_llm_stream("copilot", messages)
    accumulated = []
    thinking_accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
                elif data.get("type") == "thinking":
                    thinking_accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    full_thinking = "".join(thinking_accumulated)
    if full_text.strip():
        db.save_chat_message(novel_id, "director", f"【總監階段評估 ({current_stage})】\n{full_text}", thinking=full_thinking if full_thinking.strip() else None, message_type="director")


def run_director_decision_help(novel_id, current_stage, help_action, help_reason):
    """
    Subsequent Help check:
    If Director wants to retrieve full details (like help_worldview, help_plot) mid-stream.
    """
    if not current_stage or current_stage == "init":
        current_stage = db.detect_current_stage(novel_id)
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = wb["content"] if wb else "尚無世界觀設定"  # 這裡需要完整內容因為是調閱
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    if current_stage == "volumes":
        vols = db.get_volumes(novel_id)
        plot_text = json.dumps({"volumes": vols}, ensure_ascii=False, indent=2) if vols else "尚無篇卷規劃"
    else:
        plot_data = db.get_stitched_plot(novel_id)
        plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else "尚無章節大綱"
    
    target_data = ""
    if "worldview" in help_action:
        target_data = f"【完整世界觀設定數據】\n{worldview_text}"
    elif "character" in help_action:
        target_data = f"【完整角色 Bible 數據】\n{characters_text}"
    elif "plot" in help_action or "volume" in help_action:
        target_data = f"【完整篇卷與詳細大綱數據】\n{plot_text}"
        
    messages = build_director_decision_help_messages(help_reason, target_data)
    
    stream = call_llm_stream("copilot", messages)
    accumulated = []
    thinking_accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
                elif data.get("type") == "thinking":
                    thinking_accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    full_thinking = "".join(thinking_accumulated)
    if full_text.strip():
        db.save_chat_message(novel_id, "director", f"【總監輔助評估 ({current_stage})】\n{full_text}", thinking=full_thinking if full_thinking.strip() else None, message_type="director")


# =============================================================================
# 10. Incremental / Standalone AI Generators (Auxiliary Buttons support)
# =============================================================================
def run_incremental_architect(novel_id, target_section, user_hint):
    """
    Incremental Architect Stage:
    Updates a specific section of worldview based on user hint, then auto-merges using patch engine.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = wb["content"] if wb else "尚無世界觀設定"
    
    messages = build_incremental_architect_messages(target_section, worldview_text, user_hint)
    
    db.save_chat_message(novel_id, "user", f"增量世界觀修改。板塊: {target_section}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("architect", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        from incremental_patch_engine import validate_and_merge_incremental_patch
        success, version, err = validate_and_merge_incremental_patch(novel_id, target_section, "PATCH", full_text)
        if success:
            db.save_chat_message(novel_id, "assistant", f"增量世界觀更新完成 (版本 {version})", message_type="pipeline")
        else:
            yield "data: " + json.dumps({"type": "error", "message": f"增量世界觀更新合併失敗: {err}"}, ensure_ascii=False) + "\n\n"


def run_incremental_character_designer(novel_id, target_char_index, field_name, user_hint):
    """
    Incremental Character Stage:
    Updates a single character field or appends a new character, then auto-merges using patch engine.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    existing_chars_json = char_data["json_data"] if char_data else "{'characters': []}"
    
    target_char_content = ""
    if target_char_index is not None:
        try:
            parsed = json.loads(existing_chars_json)
            chars_list = parsed.get("characters", [])
            if 0 <= target_char_index < len(chars_list):
                target_char_content = f"\n【待修改角色的完整原內容】\n{json.dumps(chars_list[target_char_index], ensure_ascii=False, indent=2)}"
        except:
            pass
            
    messages = build_incremental_character_messages(
        worldview_text, existing_chars_json, target_char_content, target_char_index, field_name, user_hint
    )
    
    action = "PATCH" if target_char_index is not None else "APPEND"
    db.save_chat_message(novel_id, "user", f"增量角色修改。目標: {target_char_index if target_char_index is not None else '新增'}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("character", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        from incremental_patch_engine import validate_and_merge_incremental_patch
        extra = {}
        if target_char_index is not None:
            extra["char_index"] = target_char_index
        if field_name:
            extra["field_name"] = field_name
        success, version, err = validate_and_merge_incremental_patch(novel_id, "characters", action, full_text, extra)
        if success:
            db.save_chat_message(novel_id, "assistant", f"角色增量更新完成 (版本 {version})", message_type="pipeline")
        else:
            yield "data: " + json.dumps({"type": "error", "message": f"角色增量更新合併失敗: {err}"}, ensure_ascii=False) + "\n\n"


def run_incremental_plot_planner(novel_id, insert_after_index, user_hint):
    """
    Incremental Plot Stage:
    Inserts a new detailed outline chapter at position, then auto-merges using patch engine.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    plot_data = db.get_stitched_plot(novel_id)
    plot_text = json.dumps(plot_data, ensure_ascii=False, indent=2) if plot_data else "尚無章節大綱"
    
    messages = build_incremental_plot_planner_messages(worldview_text, plot_text, insert_after_index, user_hint)
    
    db.save_chat_message(novel_id, "user", f"增量大綱更新。插入位置: {insert_after_index}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("plot", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        from incremental_patch_engine import validate_and_merge_incremental_patch
        success, version, err = validate_and_merge_incremental_patch(novel_id, "plot", "INSERT", full_text, {"insert_after_index": insert_after_index})
        if success:
            db.save_chat_message(novel_id, "assistant", f"詳細大綱增量更新完成 (版本 {version})", message_type="pipeline")
        else:
            yield "data: " + json.dumps({"type": "error", "message": f"大綱增量更新合併失敗: {err}"}, ensure_ascii=False) + "\n\n"


def run_incremental_volume_skeleton(novel_id, volume_index, user_hint):
    """
    Incremental Volume Skeleton Stage:
    Updates a specific volume's skeleton based on user hint, then auto-merges and updates the DB.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    
    all_vols = db.get_volumes(novel_id)
    current_vol = next((v for v in all_vols if v["volume_index"] == volume_index), None)
    if not current_vol:
        raise ValueError(f"Volume index {volume_index} not found!")
        
    existing_skeleton = json.dumps(current_vol.get("chapters_outline") or [], ensure_ascii=False, indent=2)
    
    from prompts.prompt_builder import build_incremental_skeleton_messages
    messages = build_incremental_skeleton_messages(worldview_text, volume_index, existing_skeleton, user_hint)
    
    db.save_chat_message(novel_id, "user", f"增量卷骨架修改。卷: {volume_index}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("volume_skeleton", messages)
    accumulated = []
    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
            except:
                pass
                
    full_text = "".join(accumulated)
    if full_text.strip():
        from models.parsers import extract_json_block
        parsed = extract_json_block(full_text)
        chapters_skeleton = parsed.get("chapters_skeleton", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
        
        if chapters_skeleton:
            db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
            db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷骨架增量更新完成", message_type="pipeline")


def run_global_foreshadowing_precompute(novel_id):
    """
    [新功能] 預計算全域伏筆與轉折絕對分配藍圖的包裝函數
    """
    db.precompute_global_foreshadowing(novel_id)
