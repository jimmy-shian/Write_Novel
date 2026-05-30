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
    db.save_chat_message(novel_id, "user", f"開始生成世界觀。要求: {user_prompt}", message_type="chat")
    
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
        db.save_chat_message(novel_id, "assistant", f"世界觀生成成功！版本已更新。", message_type="chat")


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
    
    db.save_chat_message(novel_id, "user", f"執行角色設計。模式: {mode}, 指示: {user_prompt or hint}", message_type="chat")
    
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
        db.save_chat_message(novel_id, "assistant", f"角色聖經更新完畢！版本已更新。", message_type="chat")


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
    
    db.save_chat_message(novel_id, "user", f"執行篇卷規劃。模式: {mode}, 卷數: {target_vol_idx or '全書'}", message_type="chat")
    
    stream = call_llm_stream("architect", messages) # Map to architect model for volumes planning
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
                db.save_volumes(novel_id, list(merged_vols.values()))
            else:
                db.save_volumes(novel_id, vols_list)
            
            # 預計算全局伏筆與轉折藍圖
            try:
                db.precompute_global_foreshadowing(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to precompute global foreshadowing in run_volumes_planner: {e}")
                
        db.save_chat_message(novel_id, "assistant", f"篇卷結構已儲存成功！", message_type="chat")


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
    
    db.save_chat_message(novel_id, "user", f"生成第 {volume_index} 卷骨架大綱。章節範圍: {start_ch} - {end_ch}", message_type="chat")
    
    stream = call_llm_stream("plot", messages) # Map to plot model
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
        db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷簡易骨架大綱已更新成功！", message_type="chat")


# =============================================================================
# 5. Plot Planner Agent (Detailed Outline)
# =============================================================================
def run_plot_planner(novel_id, user_prompt=None, planner_directive=None):
    """
    Detailed Outline Stage:
    Generate detailed chapter outline based on:
    - worldview summary
    - skeleton outline of preceding & succeeding 1 chapters
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    
    # Retrieve all volume skeletons to build continuous chapter contexts
    all_vols = db.get_volumes(novel_id)
    all_skeleton_chapters = []
    for v in all_vols:
        if v.get("chapters_outline"):
            all_skeleton_chapters.extend(v["chapters_outline"])
            
    all_skeleton_chapters.sort(key=lambda x: int(x.get("chapter_index", 0)))
    
    if not all_skeleton_chapters:
        all_skeleton_chapters = [{"chapter_index": 1, "brief_title": "開篇第一章", "brief_summary": "主角登場與初始世界展現"}]
        
    skeleton_context_list = []
    for idx, ch in enumerate(all_skeleton_chapters):
        c_idx = int(ch.get("chapter_index", idx + 1))
        pre_ch = next((x for x in all_skeleton_chapters if int(x.get("chapter_index", 0)) == c_idx - 1), None)
        nxt_ch = next((x for x in all_skeleton_chapters if int(x.get("chapter_index", 0)) == c_idx + 1), None)
        
        wv_item = f"第 {c_idx} 章：【{ch.get('brief_title', ch.get('title', ''))}】\n  - 本章骨架概要：{ch.get('brief_summary', ch.get('summary', ''))}\n"
        if pre_ch:
            wv_item += f"  - 前一章 (第 {c_idx - 1} 章) 骨架概要：{pre_ch.get('brief_summary', pre_ch.get('summary', ''))}\n"
        if nxt_ch:
            wv_item += f"  - 後一章 (第 {c_idx + 1} 章) 骨架概要：{nxt_ch.get('brief_summary', nxt_ch.get('summary', ''))}\n"
        wv_item += f"  - 伏筆任務安排：{json.dumps(ch.get('allocated_tasks', {}), ensure_ascii=False)}\n"
        skeleton_context_list.append(wv_item)
        
    skeleton_contexts = "\n\n".join(skeleton_context_list)
    
    messages = build_plot_planner_messages(worldview_text, skeleton_contexts, user_prompt)
    
    db.save_chat_message(novel_id, "user", f"生成詳細章節大綱。要求: {user_prompt or '依骨架展開'}", message_type="chat")
    
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
        db.save_plot_chapters(novel_id, parsed_plot)
        db.save_chat_message(novel_id, "assistant", f"詳細大綱已保存成功！", message_type="chat")


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
    
    current_outline = next((ch for ch in chapters_outlines if int(ch.get("chapter_index", 0)) == chapter_index), None)
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
        
    pre_ch_outline = next((ch for ch in chapters_outlines if int(ch.get("chapter_index", 0)) == chapter_index - 1), None)
    nxt_ch_outline = next((ch for ch in chapters_outlines if int(ch.get("chapter_index", 0)) == chapter_index + 1), None)
    
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
    next_three_chaps = [ch for ch in chapters_outlines if chapter_index < int(ch.get("chapter_index", 0)) <= chapter_index + 3]
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
    
    db.save_chat_message(novel_id, "user", f"開始寫作第 {chapter_index} 章。風格: {custom_style}", message_type="chat")
    
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
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文寫作完成！", message_type="chat")


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
    
    db.save_chat_message(novel_id, "user", f"調用編輯姬潤色第 {chapter_index} 章。指示: {edit_instructions}", message_type="chat")
    
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
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文已成功潤色替換！", message_type="chat")


# =============================================================================
# 8. Copilot / Director Orchestration
# =============================================================================
def run_copilot_chat(novel_id, user_message):
    """
    AI Copilot Chat: User speaks, Copilot analyzes intent, recommends best flow, and chats.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    plot_data = db.get_stitched_plot(novel_id)
    plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else "尚無章節大綱"
    
    # 建立系統記憶歷史以保證上下文連貫
    history = db.get_chat_memory(novel_id, limit=10)
    history_context = ""
    for h in history:
        history_context += f"【{h['role']}】：{h['content']}\n"

    messages = build_copilot_chat_messages(worldview_text, characters_text, plot_text, history_context, user_message)
    
    db.save_chat_message(novel_id, "user", user_message, message_type="chat")
    
    stream = call_llm_stream("copilot", messages)
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
        db.save_chat_message(novel_id, "assistant", full_text, message_type="chat")


# =============================================================================
# 9. Director Decision Checks (Pipeline Gatekeeper)
# =============================================================================
def run_director_decision(novel_id, current_stage, user_prompt):
    """
    Gateway review after a stage completes. Returns next action:
    CONTINUE, AUTO_REGENERATE, GO_BACK_TO_WORLDVIEW, GO_BACK_TO_CHARACTERS, GO_BACK_TO_PLOT, WAIT_USER, FINISH.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    plot_data = db.get_stitched_plot(novel_id)
    plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else "尚無章節大綱"
    written_ch = db.get_all_chapters_latest(novel_id)
    written_chapters_text = f"已完成正文章節數：{len(written_ch)} 章"
    
    messages = build_director_decision_messages(current_stage, worldview_text, characters_text, plot_text, written_chapters_text, user_prompt)
    
    stream = call_llm_stream("copilot", messages)
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
        db.save_chat_message(novel_id, "director", f"【總監階段評估 ({current_stage})】\n{full_text}", message_type="director")


def run_director_decision_help(novel_id, current_stage, help_action, help_reason):
    """
    Subsequent Help check:
    If Director wants to retrieve full details (like help_worldview, help_plot) mid-stream.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = wb["content"] if wb else "尚無世界觀設定"  # 這裡需要完整內容因為是調閱
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
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
        db.save_chat_message(novel_id, "director", f"【總監輔助評估 ({current_stage})】\n{full_text}", message_type="director")


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
    
    db.save_chat_message(novel_id, "user", f"增量世界觀修改。板塊: {target_section}, 要求: {user_hint}", message_type="chat")
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
            db.save_chat_message(novel_id, "assistant", f"增量世界觀更新完成 (版本 {version})", message_type="chat")
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
    db.save_chat_message(novel_id, "user", f"增量角色修改。目標: {target_char_index if target_char_index is not None else '新增'}, 要求: {user_hint}", message_type="chat")
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
            db.save_chat_message(novel_id, "assistant", f"角色增量更新完成 (版本 {version})", message_type="chat")
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
    
    db.save_chat_message(novel_id, "user", f"增量大綱更新。插入位置: {insert_after_index}, 要求: {user_hint}", message_type="chat")
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
            db.save_chat_message(novel_id, "assistant", f"詳細大綱增量更新完成 (版本 {version})", message_type="chat")
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
    
    db.save_chat_message(novel_id, "user", f"增量卷骨架修改。卷: {volume_index}, 要求: {user_hint}", message_type="chat")
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
        parsed = extract_json_block(full_text)
        chapters_skeleton = parsed.get("chapters_skeleton", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
        
        if chapters_skeleton:
            db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
            db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷骨架增量更新完成", message_type="chat")


def run_global_foreshadowing_precompute(novel_id):
    """
    [新功能] 預計算全域伏筆與轉折絕對分配藍圖的包裝函數
    """
    db.precompute_global_foreshadowing(novel_id)