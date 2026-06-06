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
import traceback
import asyncio
from functools import partial
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
    build_chapter_writer_messages,
    build_editor_agent_messages,
    build_copilot_chat_messages,
    build_director_decision_messages,
    build_director_decision_help_messages,
    build_incremental_architect_messages,
    build_incremental_character_messages,
    extract_worldview_summary
)


async def safe_generator_wrapper(gen):
    """
    Async wrapper around a sync generator.
    - Detects client disconnect (asyncio.CancelledError) and closes the generator cleanly.
    - Prevents exceptions from propagating after data has been yielded.
    - If it raises before yielding anything, re-raises so FastAPI can send a proper error response.
    """
    loop = asyncio.get_running_loop()
    has_yielded = False
    sentinel = object()
    try:
        while True:
            chunk = await loop.run_in_executor(None, partial(next, gen, sentinel))
            if chunk is sentinel:
                break
            has_yielded = True
            yield chunk
    except asyncio.CancelledError:
        print("[SAFE_WRAPPER] Client disconnected, stopping generator.")
        try:
            gen.close()
        except (ValueError, RuntimeError):
            pass
    except Exception as e:
        print(f"[SAFE_WRAPPER] Generator raised: {e}")
        traceback.print_exc()
        if has_yielded:
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"伺服器內部錯誤（串流後處理失敗）: {str(e)}"
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        else:
            raise


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
    # generate 模式傳入完整世界觀讓 LLM 自行決定卷數與章數分配
    worldview_text = wb["content"] if wb else "尚無世界觀設定"
    
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
            # Programmatic Adjustment & Constraints Check
            adjusted_vols = []
            for i, vol in enumerate(vols_list):
                try:
                    ch_count = int(vol.get("chapter_count", 45))
                except:
                    ch_count = 45
                if ch_count <= 0 or ch_count > 50:
                    ch_count = 45
                vol["chapter_count"] = ch_count
                
                try:
                    vol_idx = int(vol.get("volume_index", i + 1))
                except:
                    vol_idx = i + 1
                vol["volume_index"] = vol_idx
                adjusted_vols.append(vol)

            if mode != "patch" and len(adjusted_vols) < 8:
                while len(adjusted_vols) < 8:
                    new_idx = len(adjusted_vols) + 1
                    adjusted_vols.append({
                        "volume_index": new_idx,
                        "title": f"第 {new_idx} 卷",
                        "summary": f"第 {new_idx} 卷情節大綱，承接前文，故事在此階段逐步走向新的衝突與起伏。",
                        "factions": [],
                        "chapter_count": 45,
                        "time_timeline": "",
                        "sequence_context": "",
                        "applicable_rules": []
                    })
            
            if mode == "patch" and target_vol_idx is not None:
                # Patch mode: upsert only the target volume, preserve all others
                db.save_volumes(novel_id, adjusted_vols, clear_downstream=False, target_vol_idx=target_vol_idx)
            else:
                db.save_volumes(novel_id, adjusted_vols, clear_downstream=True)
            
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
    volume_index = int(volume_index)
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

【新角色【{new_char_name}】登場的第 {chapter_outline.get('chapter_index')} 章大綱】
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

請為新角色【{new_char_name}】生成高品質的完整角色 JSON 卡片。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]





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


def _collect_volume_skeleton_chapters(novel_id):
    skeleton_chapters = []
    for vol in db.get_volumes(novel_id):
        ch_list = vol.get("chapters_outline")
        if isinstance(ch_list, list):
            skeleton_chapters.extend(ch_list)
    return _normalize_chapter_list(skeleton_chapters)

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
        surrounding_plot += f"\n【前一章 (第 {chapter_index - 1} 章) 大綱】\n{json.dumps(pre_ch_outline, ensure_ascii=False, indent=2)}\n"
    if nxt_ch_outline:
        surrounding_plot += f"\n【後一章 (第 {chapter_index + 1} 章) 大綱】\n{json.dumps(nxt_ch_outline, ensure_ascii=False, indent=2)}\n"
        
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
        novel_id, worldview_text, characters_text, plot_text, history_context, user_message, 
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
def run_director_decision(novel_id, current_stage, user_prompt, chapter_index=None, volume_index=None, character_review_mode=None, character_review_hint=None, character_review_target_content=None, suggested_next_chapter=None):
    """
    Gateway review after a stage completes. Returns next action:
    CONTINUE, GO_BACK_TO_WORLDVIEW, GO_BACK_TO_CHARACTERS, GO_BACK_TO_PLOT, WAIT_USER, FINISH.
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
        # 補入目標卷的標題與大綱摘要
        if volume_index is not None:
            target_vol = next((v for v in vols if v["volume_index"] == volume_index), None)
            if target_vol:
                vol_highlight = f"\n\n【當前審查之目標卷 - 第 {volume_index} 卷】\n標題：{target_vol.get('title', '')}\n卷概要：{target_vol.get('summary', '')}"
                plot_text += vol_highlight
    elif current_stage == "plot":
        plot_data = db.get_stitched_plot(novel_id)
        chapters_outlines = plot_data.get("chapters", []) if plot_data else []
        normalized_outlines = _normalize_chapter_list(chapters_outlines)
        
        if chapter_index is None:
            chapter_index = max([ch["chapter_index"] for ch in normalized_outlines], default=1)
        
        review_payload = {
            "current_chapter_index": chapter_index,
            "chapters": normalized_outlines
        }
        plot_text = json.dumps(review_payload, ensure_ascii=False, indent=2)
            
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
        
        clue_payoff_context = ""
        next_three_chaps = [ch for ch in normalized_outlines if target_ch_idx < ch["chapter_index"] <= target_ch_idx + 3]
        payoff_clues = []
        for ch in next_three_chaps:
            payoffs = ch.get("foreshadowing_payoff", []) or ch.get("allocated_tasks", {}).get("foreshadowing_payoffs", [])
            if payoffs:
                payoff_clues.append(f"第 {ch.get('chapter_index')} 章預計收回的伏筆：{json.dumps(payoffs, ensure_ascii=False)}")
        if payoff_clues:
            clue_payoff_context = "\n".join(payoff_clues)
        
        writer_review_data = {
            "chapter_index": target_ch_idx,
            "chapter_title": curr_ch_outline.get("title", f"第 {target_ch_idx} 章") if curr_ch_outline else f"第 {target_ch_idx} 章",
            "outline": curr_ch_outline if curr_ch_outline else "（尚未生成章節大綱）",
            "allocated_tasks_and_clues": curr_ch_outline.get("allocated_tasks", {}) if curr_ch_outline else {},
            "clue_payoff_upcoming_3_chapters": clue_payoff_context or "（後三章無需回收的伏筆）",
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
        if not plot_data:
            plot_text = "尚無章節大綱"
        else:
            chapters = plot_data.get("chapters", [])

            indexes = sorted(
                int(ch["chapter_index"])
                for ch in chapters
                if ch.get("chapter_index") is not None
            )

            if indexes:
                existing = set(indexes)

                missing = [
                    i
                    for i in range(indexes[0], indexes[-1] + 1)
                    if i not in existing
                ]

                plot_text = f"""
        大綱檢查報告
        -------------
        總章節數：{len(indexes)}
        章節範圍：{indexes[0]} ~ {indexes[-1]}
        缺失章節數：{len(missing)}
        缺失章節：{missing[:30] if missing else "無"}
        """
            else:
                plot_text = "尚無章節大綱"

        written_ch = db.get_all_chapters_latest(novel_id)
        written_chapters_text = f"已完成正文章節數：{len(written_ch)} 章"
        
    # 生成 Python 剛性指標檢查報告
    validation_report = db.generate_validation_report(
        novel_id, 
        current_stage=current_stage, 
        active_volume_index=volume_index, 
        active_chapter_index=chapter_index
    )
    
    messages = build_director_decision_messages(
        novel_id, current_stage, worldview_text, characters_text, plot_text, written_chapters_text, 
        user_prompt, validation_report,
        character_review_mode=character_review_mode,
        character_review_hint=character_review_hint,
        character_review_target_content=character_review_target_content,
        suggested_next_chapter=suggested_next_chapter,
        chapter_index=chapter_index
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
        target_data = f"【完整篇卷與大綱數據】\n{plot_text}"
        
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



def run_incremental_volume_skeleton(novel_id, volume_index, user_hint):
    """
    Incremental Volume Skeleton Stage:
    Updates a specific volume's skeleton based on user hint, then auto-merges and updates the DB.
    """
    volume_index = int(volume_index)
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
