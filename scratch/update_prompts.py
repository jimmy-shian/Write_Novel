# -*- coding: utf-8 -*-
import sys
import os

target_file = b"prompts/prompt_builder.py"

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

# Replace extract_worldview_summary and build functions
old_text = '''def extract_worldview_summary(worldview_text):
    """
    從完整世界觀文本中提取關鍵摘要：
    - 世界觀設定 (worldview)
    - 整體故事大綱 (macro_outline)
    只返回這兩個核心區塊的內容，避免過長。
    """
    if not worldview_text:
        return "（尚無世界觀設定）"
    
    # 嘗試解析為 JSON
    try:
        parsed = json.loads(worldview_text)
        if isinstance(parsed, dict):
            # 提取關鍵字段
            summary_parts = []
            
            # 世界觀設定
            worldview_content = parsed.get("worldview", "")
            if worldview_content:
                # 如果太長，截斷
                if len(worldview_content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
                    worldview_content = worldview_content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\\n...（內容過長已截斷）"
                summary_parts.append(f"【世界觀設定】\\n{worldview_content}")
            
            # 整體故事大綱
            macro_outline = parsed.get("macro_outline", "")
            if macro_outline:
                if len(macro_outline) > MAX_MACRO_OUTLINE_LENGTH:
                    macro_outline = macro_outline[:MAX_MACRO_OUTLINE_LENGTH] + "\\n...（內容過長已截斷）"
                summary_parts.append(f"【整體故事大綱】\\n{macro_outline}")
            
            # 如果有摘要則返回
            if summary_parts:
                return "\\n\\n".join(summary_parts)
    except json.JSONDecodeError:
        # JSON 解析失敗，使用純文字解析
        pass
    
    # Fallback: 嘗試用文本方式提取
    # 找 【世界觀設定】 和 【整體故事大綱】 區塊
    result_parts = []
    
    lines = worldview_text.split('\\n')
    current_section = None
    section_content = []
    
    for line in lines:
        line = line.strip()
        if '【世界觀設定】' in line:
            # 保存前一個區塊
            if current_section == 'worldview' and section_content:
                content = '\\n'.join(section_content)
                if len(content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
                    content = content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\\n...（內容過長已截斷）"
                result_parts.append(f"【世界觀設定】\\n{content}")
            current_section = 'worldview'
            section_content = []
        elif '【整體故事大綱】' in line:
            if current_section == 'worldview' and section_content:
                content = '\\n'.join(section_content)
                if len(content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
                    content = content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\\n...（內容過長已截斷）"
                result_parts.append(f"【世界觀設定】\\n{content}")
            current_section = 'macro_outline'
            section_content = []
        elif current_section:
            section_content.append(line)
    
    # 保存最後一個區塊
    if current_section == 'worldview' and section_content:
        content = '\\n'.join(section_content)
        if len(content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
            content = content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\\n...（內容過長已截斷）"
        result_parts.append(f"【世界觀設定】\\n{content}")
    elif current_section == 'macro_outline' and section_content:
        content = '\\n'.join(section_content)
        if len(content) > MAX_MACRO_OUTLINE_LENGTH:
            content = content[:MAX_MACRO_OUTLINE_LENGTH] + "\\n...（內容過長已截斷）"
        result_parts.append(f"【整體故事大綱】\\n{content}")
    
    if result_parts:
        return "\\n\\n".join(result_parts)
    
    # 最終 fallback: 返回原始文本的前面部分
    truncated = worldview_text[:MAX_WORLDVIEW_SUMMARY_LENGTH]
    if len(worldview_text) > MAX_WORLDVIEW_SUMMARY_LENGTH:
        truncated += "\\n...（內容過長已截斷）"
    return truncated

def get_json_schema_prompt_snippet(schema_name):
    """取得 JSON 格式綱要說明字串，已徹底移除非法 Python set literal {...} 以防 JSON 序列化失敗。"""
    schema_map = {
        "worldview": agent_json.WORLDVIEW_SCHEMA,
        "character": agent_json.CHARACTERS_ROOT_SCHEMA,
        "volumes": {"volumes": [agent_json.VOLUME_SCHEMA]},
        "skeleton": {"volume_index": 1, "chapters_skeleton": [agent_json.CHAPTER_SKELETON_WITH_ALLOC_SCHEMA]},
        "plot": agent_json.PLOT_ROOT_SCHEMA,
        "writer": agent_json.WRITER_OUTPUT_SCHEMA,
        "editor": agent_json.EDITOR_OUTPUT_SCHEMA
    }
    schema = schema_map.get(schema_name, {})
    return f"\\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this schema. Wrap in ```json ... ``` codeblock]\\n{json.dumps(schema, ensure_ascii=False, indent=2)}\\n"

def build_story_architect_messages(genre, style, user_prompt):
    """世界觀架構師提示詞拼接"""
    # 這裡的 STORY_ARCHITECT_PROMPT 包含了 generate_style
    # 為了告知模型多幕式與多波段不限於 3，我們加入說明引導
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    system_prompt = f"{STORY_ARCHITECT_PROMPT.format(generate_style=style)}\\n\\n{schema_snippet}\\n"
    # 強調可以任意增長/縮短 multi_act_structure 與 progressive_character_plan 的長度，不限於 3 個元素
    system_prompt += "\\n*[提示：`multi_act_structure` 與 `progressive_character_plan` 可以依據需要規劃任意數量的多幕/波段（例如：4幕、5波等），無須限制為範例中的數量。]*\\n"
    
    user_content = f"""【使用者創作需求與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：{user_prompt}

請根據以上設定，為本作品生成符合結構的完整世界觀 JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index):
    """角色設計師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("character")
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\\n\\n{schema_snippet}\\n"
    
    if mode == "generate":
        user_content = f"""【世界觀背景】
{worldview_text}

【使用者要求】
{user_prompt or "請根據世界觀，為我們設計核心角色與配角群像。"}

請為本作品生成符合結構的角色 Bible JSON 設定。
"""
    elif mode == "expand":
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}

【總監批判與擴增提示 (Hint)】
{hint or "請擴增有深度的新角色。"}

【一般提示詞 (Prompt)】
{user_prompt or "請在現有角色基礎上進行增量擴展，追加新角色。"}

請根據總監提示，追加新角色並輸出完整的角色 Bible JSON 設定。
"""
    else:  # modify
        target_char_content = ""
        if target_char_index is not None:
            try:
                parsed_chars = json.loads(existing_chars_json)
                chars_list = parsed_chars.get("characters", [])
                if 0 <= target_char_index < len(chars_list):
                    target_char_content = f"\\n【被修改角色的完整內容 (Index {target_char_index})】\\n{json.dumps(chars_list[target_char_index], ensure_ascii=False, indent=2)}"
            except:
                pass
                
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}
{target_char_content}

【修改指示 (Hint)】
{hint or "請修改角色設定。"}

【一般提示詞 (Prompt)】
{user_prompt or "請對指定角色進行內容調整。"}

請將以上修改與該角色的完整內容融會貫通，修正後輸出完整的角色 Bible JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx):
    """篇卷規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("volumes")
    system_prompt = f"{VOLUMES_PLANNER_PROMPT}\\n\\n{schema_snippet}\\n"
    
    if mode == "generate":
        vols_context = ""
        if existing_vols:
            vols_context = "\\n【現有已規劃篇卷概述】\\n"
            for v in existing_vols:
                vols_context += f"- 卷 {v['volume_index']}：{v['title']} (大綱: {v['summary']})\\n"
                
        user_content = f"""【世界觀背景】
{worldview_text}
{vols_context}
【使用者大綱/要求】
{user_prompt or "請合理規劃整部作品的篇卷結構。"}

請為本作品生成符合結構的篇卷 JSON 清單。
"""
    else:  # patch/add specific idx
        v_idx = target_vol_idx or 1
        surrounding_context = ""
        pre_vol = next((v for v in existing_vols if v["volume_index"] == v_idx - 1), None)
        next_vol = next((v for v in existing_vols if v["volume_index"] == v_idx + 1), None)
        
        if pre_vol:
            surrounding_context += f"\\n【前 1 卷 (卷 {v_idx - 1}) 大綱與概要】\\n標題：{pre_vol['title']}\\n概要：{pre_vol['summary']}\\n"
        if next_vol:
            surrounding_context += f"\\n【後 1 卷 (卷 {v_idx + 1}) 大綱與概要】\\n標題：{next_vol['title']}\\n概要：{next_vol['summary']}\\n"
            
        user_content = f"""【世界觀背景】
{worldview_text}
{surrounding_context}
【修補指定卷目標】
- 指定修補生成第 {v_idx} 卷

【總監批判與修改指示 (Hint)】
{hint or "請修正該卷的起承轉合與情節重心。"}

【一般提示詞 (Prompt)】
{user_prompt or f"請專注且只生成/修補第 {v_idx} 卷的大綱骨架，不要修改其他無關卷。"}

請僅針對第 {v_idx} 卷進行精細化生成/修補，並回傳格式完全合法的 volumes JSON，列表中應僅包含第 {v_idx} 卷的新/修改內容。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volume_skeleton_planner_messages(worldview_text, volume_index, current_vol, start_ch, end_ch, vol_chapter_count, surrounding_context, precalc_clues, user_prompt):
    """卷骨架大綱規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT.format(volume_index=volume_index, start_ch=start_ch, end_ch=end_ch, vol_chapter_count=vol_chapter_count)}\\n\\n{schema_snippet}\\n"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務】
- 當前篇卷序號：第 {volume_index} 卷
- 篇卷標題：{current_vol['title']}
- 篇卷概要：{current_vol['summary']}
- 章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {vol_chapter_count} 章）
請務必嚴格在此章節序號範圍內規劃骨架！

{surrounding_context}
{precalc_clues}
【使用者額外提示詞 (Prompt)】
{user_prompt or "請為本卷精心設計簡易骨架大綱。"}

請為本卷生成符合 JSON 結構的章節骨架清單。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_plot_planner_messages(worldview_text, skeleton_contexts, user_prompt):
    """劇情大綱規劃師提示詞拼接"""
    # 這裡將任務參數帶入大綱規劃
    schema_snippet = get_json_schema_prompt_snippet("plot")
    system_prompt = f"{PLOT_PLANNER_PROMPT.format(seens='對於骨架中指定的 ⚠️【硬性指定埋設伏筆】 與 ⚠️【硬性指定回收伏筆】，你必須在對應章節的 foreshadowing_plant 與 foreshadowing_payoff 欄位中完美承接並展開編織，不得遺漏！', turning_points='對於骨架中指定的 配合指定關鍵轉折點進展，你必須在對應章節的 turning_points 欄位中確實寫入，並在情節中給予充足的戲劇爆發張力！')}\\n\\n{schema_snippet}\\n"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【全書簡易章節骨架及前後章上下文對照表】
{skeleton_contexts}

【使用者微調/額外要求】
{user_prompt or "請根據簡易骨架大綱，為全書擴充並生成高品質的詳細大綱 JSON 設定。"}

請為所有章節生成符合結構的詳細大綱 JSON。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_chapter_writer_messages(worldview_text, characters_bible, current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, custom_style, chapter_index):
    """正文作家寫作提示詞拼接"""
    system_prompt = CHAPTER_WRITER_PROMPT.format(writing_style=custom_style)
    
    # 對角色 Bible 進行基本設定篩選，避免過長導致 API 失敗
    characters_bible_filtered = extract_character_basic(characters_bible)
    
    user_content = f"""【世界觀背景】
{worldview_text}

【角色 Bible 聖經】(基本設定)
{json.dumps(characters_bible_filtered, ensure_ascii=False, indent=2)}

【當前章節 (第 {chapter_index} 章) 詳細大綱】
{json.dumps(current_outline, ensure_ascii=False, indent=2)}

{surrounding_plot}
{vol_outline_context}
{clue_payoff_details}

請根據以上豐富的上下文細節，展開本章正文寫作，字數約 2000-3000 字。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_editor_agent_messages(chapter_index, edit_instructions, original_prose):
    """編輯姬提示詞拼接"""
    system_prompt = EDITOR_PROMPT
    user_content = f"""【修改指示 / 精修重點】
{edit_instructions or "精雕細琢遣詞造句，優化意象與文學美感，剔除冗詞贅字，增強情節張力與情緒渲染。"}

【待精修的第 {chapter_index} 章原始正文】
{original_prose}

請直接輸出拋光後的完整正文：
"""'''

new_text = '''def extract_worldview_summary(worldview_text):
    """
    從完整世界觀文本中提取關鍵摘要：
    - 世界觀設定 (worldview)
    - 整體故事大綱 (macro_outline)
    只返回這兩個核心區塊的內容，避免過長。
    """
    if not worldview_text:
        return "（尚無世界觀設定）"
    
    import re
    # 嘗試解析為 JSON
    parsed = None
    try:
        parsed = json.loads(worldview_text)
    except Exception:
        try:
            # 嘗試修復常見的單引號字典格式
            fixed_text = worldview_text.replace("'", '"')
            parsed = json.loads(fixed_text)
        except Exception:
            pass
            
    if parsed and isinstance(parsed, dict):
        summary_parts = []
        worldview_content = parsed.get("worldview", "")
        if worldview_content:
            summary_parts.append(f"【世界觀設定】\\n{worldview_content}")
        macro_outline = parsed.get("macro_outline", "")
        if macro_outline:
            summary_parts.append(f"【整體故事大綱】\\n{macro_outline}")
        if summary_parts:
            return "\\n\\n".join(summary_parts)

    # 如果 JSON 解析失敗，手動用正則表達式或字串清除 seeds 和 turns 等巨型欄位
    cleaned_text = worldview_text
    for key in ["foreshadowing_seeds", "key_turning_points", "multi_act_structure", "progressive_character_plan"]:
        cleaned_text = re.sub(fr'"{key}"\\s*:\\s*\\[.*?\\]', f'"{key}": []', cleaned_text, flags=re.DOTALL)
        cleaned_text = re.sub(fr"'{key}'\\s*:\\s*\\[.*?\\]", f"'{key}': []", cleaned_text, flags=re.DOTALL)
        
    # 保底只取前面適當長度，防備非 JSON 格式下的 Token 膨脹
    if len(cleaned_text) > 4000:
        cleaned_text = cleaned_text[:4000] + "\\n...（內容過長已自動過濾巨型伏筆與轉折欄位）"
        
    return cleaned_text

def get_json_schema_prompt_snippet(schema_name):
    """取得 JSON 格式綱要說明字串，已徹底移除非法 Python set literal {...} 以防 JSON 序列化失敗。"""
    schema_map = {
        "worldview": agent_json.WORLDVIEW_SCHEMA,
        "character": agent_json.CHARACTERS_ROOT_SCHEMA,
        "volumes": {"volumes": [agent_json.VOLUME_SCHEMA]},
        "skeleton": {"volume_index": 1, "chapters_skeleton": [agent_json.CHAPTER_SKELETON_WITH_ALLOC_SCHEMA]},
        "plot": agent_json.PLOT_ROOT_SCHEMA,
        "writer": agent_json.WRITER_OUTPUT_SCHEMA,
        "editor": agent_json.EDITOR_OUTPUT_SCHEMA
    }
    schema = schema_map.get(schema_name, {})
    return f"\\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this schema. Wrap in ```json ... ``` codeblock]\\n{json.dumps(schema, ensure_ascii=False, indent=2)}\\n"

def build_story_architect_messages(genre, style, user_prompt):
    """世界觀架構師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    criteria_snippet = agent_json.format_criteria_for_prompt("worldview")
    
    # 結合 agent_json 規範與 prompt_main 骨架提示詞
    system_prompt = f"{STORY_ARCHITECT_PROMPT.format(generate_style=style)}\\n\\n{criteria_snippet}\\n\\n{schema_snippet}\\n"
    system_prompt += "\\n*[提示：`multi_act_structure` 與 `progressive_character_plan` 可以依據需要規劃任意數量的多幕/波段（例如：4幕、5波等），無須限制為範例中的數量。]*\\n"
    
    user_content = f"""【使用者創作需求與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：{user_prompt}

請根據以上設定，為本作品生成符合結構的完整世界觀 JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index):
    """角色設計師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("character")
    criteria_snippet = agent_json.format_criteria_for_prompt("characters")
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\\n\\n{criteria_snippet}\\n\\n{schema_snippet}\\n"
    
    if mode == "generate":
        user_content = f"""【世界觀背景】
{worldview_text}

【使用者要求】
{user_prompt or "請根據世界觀，為我們設計核心角色與配角群像。"}

請為本作品生成符合結構的角色 Bible JSON 設定。
"""
    elif mode == "expand":
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}

【總監批判與擴增提示 (Hint)】
{hint or "請擴增有深度的新角色。"}

【一般提示詞 (Prompt)】
{user_prompt or "請在現有角色基礎上進行增量擴展，追加新角色。"}

請根據總監提示，追加新角色並輸出完整的角色 Bible JSON 設定。
"""
    else:  # modify
        target_char_content = ""
        if target_char_index is not None:
            try:
                parsed_chars = json.loads(existing_chars_json)
                chars_list = parsed_chars.get("characters", [])
                if 0 <= target_char_index < len(chars_list):
                    target_char_content = f"\\n【被修改角色的完整內容 (Index {target_char_index})】\\n{json.dumps(chars_list[target_char_index], ensure_ascii=False, indent=2)}"
            except:
                pass
                
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}
{target_char_content}

【修改指示 (Hint)】
{hint or "請修改角色設定。"}

【一般提示詞 (Prompt)】
{user_prompt or "請對指定角色進行內容調整。"}

請將以上修改與該角色的完整內容融會貫通，修正後輸出完整的角色 Bible JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx):
    """篇卷規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("volumes")
    criteria_snippet = agent_json.format_criteria_for_prompt("volumes")
    system_prompt = f"{VOLUMES_PLANNER_PROMPT}\\n\\n{criteria_snippet}\\n\\n{schema_snippet}\\n"
    
    if mode == "generate":
        vols_context = ""
        if existing_vols:
            vols_context = "\\n【現有已規劃篇卷概述】\\n"
            for v in existing_vols:
                vols_context += f"- 卷 {v['volume_index']}：{v['title']} (大綱: {v['summary']})\\n"
                
        user_content = f"""【世界觀背景】
{worldview_text}
{vols_context}
【使用者大綱/要求】
{user_prompt or "請合理規劃整部作品的篇卷結構。"}

請為本作品生成符合結構的篇卷 JSON 清單。
"""
    else:  # patch/add specific idx
        v_idx = target_vol_idx or 1
        surrounding_context = ""
        pre_vol = next((v for v in existing_vols if v["volume_index"] == v_idx - 1), None)
        next_vol = next((v for v in existing_vols if v["volume_index"] == v_idx + 1), None)
        
        if pre_vol:
            surrounding_context += f"\\n【前 1 卷 (卷 {v_idx - 1}) 大綱與概要】\\n標題：{pre_vol['title']}\\n概要：{pre_vol['summary']}\\n"
        if next_vol:
            surrounding_context += f"\\n【後 1 卷 (卷 {v_idx + 1}) 大綱與概要】\\n標題：{next_vol['title']}\\n概要：{next_vol['summary']}\\n"
            
        user_content = f"""【世界觀背景】
{worldview_text}
{surrounding_context}
【修補指定卷目標】
- 指定修補生成第 {v_idx} 卷

【總監批判與修改指示 (Hint)】
{hint or "請修正該卷的起承轉合與情節重心。"}

【一般提示詞 (Prompt)】
{user_prompt or f"請專注且只生成/修補第 {v_idx} 卷的大綱骨架，不要修改其他無關卷。"}

請僅針對第 {v_idx} 卷進行精細化生成/修補，並回傳格式完全合法的 volumes JSON，列表中應僅包含第 {v_idx} 卷的新/修改內容。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volume_skeleton_planner_messages(worldview_text, volume_index, current_vol, start_ch, end_ch, vol_chapter_count, surrounding_context, precalc_clues, user_prompt):
    """卷骨架大綱規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    criteria_snippet = agent_json.format_criteria_for_prompt("volume_skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT.format(volume_index=volume_index, start_ch=start_ch, end_ch=end_ch, vol_chapter_count=vol_chapter_count)}\\n\\n{criteria_snippet}\\n\\n{schema_snippet}\\n"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務】
- 當前篇卷序號：第 {volume_index} 卷
- 篇卷標題：{current_vol['title']}
- 篇卷概要：{current_vol['summary']}
- 章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {vol_chapter_count} 章）
請務必嚴格在此章節序號範圍內規劃骨架！

{surrounding_context}
{precalc_clues}
【使用者額外提示詞 (Prompt)】
{user_prompt or "請為本卷精心設計簡易骨架大綱。"}

請為本卷生成符合 JSON 結構的章節骨架清單。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_plot_planner_messages(worldview_text, skeleton_contexts, user_prompt):
    """劇情大綱規劃師提示詞拼接"""
    # 這裡將任務參數帶入大綱規劃
    schema_snippet = get_json_schema_prompt_snippet("plot")
    criteria_snippet = agent_json.format_criteria_for_prompt("plot")
    system_prompt = f"{PLOT_PLANNER_PROMPT.format(seens='對於骨架中指定的 ⚠️【硬性指定埋設伏筆】 與 ⚠️【硬性指定回收伏筆】，你必須在對應章節的 foreshadowing_plant 與 foreshadowing_payoff 欄位中完美承接並展開編織，不得遺漏！', turning_points='對於骨架中指定的 配合指定關鍵轉折點進展，你必須在對應章節的 turning_points 欄位中確實寫入，並在情節中給予充足的戲劇爆發張力！')}\\n\\n{criteria_snippet}\\n\\n{schema_snippet}\\n"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【全書簡易章節骨架及前後章上下文對照表】
{skeleton_contexts}

【使用者微調/額外要求】
{user_prompt or "請根據簡易骨架大綱，為全書擴充並生成高品質的詳細大綱 JSON 設定。"}

請為所有章節生成符合結構的詳細大綱 JSON。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_chapter_writer_messages(worldview_text, characters_bible, current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, custom_style, chapter_index):
    """正文作家寫作提示詞拼接"""
    criteria_snippet = agent_json.format_criteria_for_prompt("writer")
    system_prompt = f"{CHAPTER_WRITER_PROMPT.format(writing_style=custom_style)}\\n\\n{criteria_snippet}\\n"
    
    # 對角色 Bible 進行基本設定篩選，避免過長導致 API 失敗
    characters_bible_filtered = extract_character_basic(characters_bible)
    
    user_content = f"""【世界觀背景】
{worldview_text}

【角色 Bible 聖經】(基本設定)
{json.dumps(characters_bible_filtered, ensure_ascii=False, indent=2)}

【當前章節 (第 {chapter_index} 章) 詳細大綱】
{json.dumps(current_outline, ensure_ascii=False, indent=2)}

{surrounding_plot}
{vol_outline_context}
{clue_payoff_details}

請根據以上豐富的上下文細節，展開本章正文寫作，字數約 2000-3000 字。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_editor_agent_messages(chapter_index, edit_instructions, original_prose):
    """編輯姬提示詞拼接"""
    criteria_snippet = agent_json.format_criteria_for_prompt("editor")
    system_prompt = f"{EDITOR_PROMPT}\\n\\n{criteria_snippet}\\n"
    user_content = f"""【修改指示 / 精修重點】
{edit_instructions or "精雕細琢遣詞造句，優化意象與文學美感，剔除冗詞贅字，增強情節張力與情緒渲染。"}

【待精修的第 {chapter_index} 章原始正文】
{original_prose}

請直接輸出拋光後的完整正文：
"""'''

if old_text in content:
    content = content.replace(old_text, new_text)
    print("Match found and replaced!")
else:
    print("Exact old_text match not found! Doing generic replace...")

# Also replace the mask_worldview_seeds_and_turns call in build_director_decision_messages
old_decision = '''    # 總監評斷世界觀時需要完整傳入，而其他階段已經通過審核，將其內部的伏筆與轉折欄位改為 "此區塊通過審核不需評判"
    if current_stage != "worldview":
        worldview_text = mask_worldview_seeds_and_turns(worldview_text)'''

new_decision = '''    # 總監評斷世界觀時需要完整傳入，而其他階段已經通過審核，只傳入設定與大綱摘要以避免 Token 溢出與巨型欄位爆炸
    if current_stage != "worldview":
        worldview_text = extract_worldview_summary(worldview_text)'''

if old_decision in content:
    content = content.replace(old_decision, new_decision)
    print("Decision match found and replaced!")
else:
    print("Decision match not found!")

with open(target_file, "wb") as f:
    f.write(content.encode("utf-8"))

print("Update completed successfully!")
