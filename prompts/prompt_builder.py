# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
import agent_json
from prompts.prompt_main import (
    STORY_ARCHITECT_PROMPT,
    VOLUMES_PLANNER_PROMPT,
    VOLUME_SKELETON_PROMPT,
    CHARACTER_DESIGNER_PROMPT,
    PLOT_PLANNER_PROMPT,
    CHAPTER_WRITER_PROMPT,
    VOLUME_SKELETON_PROMPT_PLUS,
    CHARACTER_DESIGNER_PROMPT_PLUS
)
from prompts.prompt_detail_modifier import (
    EDITOR_PROMPT,
    INCREMENTAL_CHARACTER_PROMPT,
    INCREMENTAL_CHARACTER_APPEND_PROMPT
)
from prompts.prompt_instructions import (
    CO_PILOT_ORCHESTRATOR_PROMPT,
    DIRECTOR_COMMON_FOOTER
)

# --- 世界觀摘要輔助函數 ---
# 用於提取世界觀的關鍵摘要，避免過長的上下文導致 API 失敗
MAX_WORLDVIEW_SUMMARY_LENGTH = 4500  # 限制摘要長度
MAX_MACRO_OUTLINE_LENGTH = 3500       # 限制大綱長度

# --- 角色基本設定輔助函數 ---
# 定義角色只需要傳入的基本欄位，過濾掉冗長的背景故事等欄位
# 核心欄位：name 和 personality 是必留的，其他可以過濾
CHARACTER_BASIC_FIELDS = [
    "name",
    "role", 
    "entry_phase",
    "personality",
    "want",
    "need",
    "fatal_flaw",
    "speech_style"
]

MAX_CHARACTERS_SUMMARY_LENGTH = 5000  # 限制角色摘要總長度

def extract_character_basic(characters_data):
    """
    從完整角色資料中提取基本設定：
    - 只保留核心識別與寫作需要的欄位
    - 過濾掉冗長的背景故事、詳細背景等欄位
    - name 和 personality 是必留欄位，確保角色識別和寫作風格參考
    
    這樣可以大幅減少 token 消耗，同時保留寫作時需要的關鍵角色資訊。
    """
    # 如果是 {"characters": [...]} 格式
    if isinstance(characters_data, dict):
        if "characters" in characters_data:
            chars_list = characters_data["characters"]
        else:
            chars_list = [characters_data]
    elif isinstance(characters_data, list):
        chars_list = characters_data
    elif isinstance(characters_data, str):
        # 可能是 JSON 字串，先解析
        try:
            parsed = json.loads(characters_data)
            return extract_character_basic(parsed)
        except:
            return characters_data
    else:
        return characters_data
    
    if not isinstance(chars_list, list):
        return characters_data
    
    filtered_chars = []
    total_len = 0
    
    for char in chars_list:
        if not isinstance(char, dict):
            continue
        
        # 確保 name 和 personality 必留
        filtered_char = {}
        for field in CHARACTER_BASIC_FIELDS:
            if field in char:
                filtered_char[field] = char[field]
        
        # 如果缺少 name，跳過
        if "name" not in filtered_char:
            continue
            
        # 計算預估長度
        char_json = json.dumps(filtered_char, ensure_ascii=False)
        if total_len + len(char_json) > MAX_CHARACTERS_SUMMARY_LENGTH:
            # 如果加入這個角色會超長，只加入角色名稱作為識別
            filtered_chars.append({"name": filtered_char["name"], "note": "（內容過長已簡化）"})
            total_len += len(filtered_char.get("name", "")) + 30
        else:
            filtered_chars.append(filtered_char)
            total_len += len(char_json)
    
    return {"characters": filtered_chars}

def extract_character_names_list(characters_data):
    """
    從完整角色資料中提取角色名稱列表，用於總監決策。
    格式為 "名字(role)"，確保總監能看到完整的角色識別資訊，
    不會因為缺少內容而錯誤地給出"再次生成角色列表"的指令。
    
    返回格式：字串列表，每項為 "角色名稱(角色定位)" 或僅 "角色名稱"
    """
    if not characters_data:
        return []
    
    # 解析資料
    if isinstance(characters_data, str):
        try:
            parsed = json.loads(characters_data)
            return extract_character_names_list(parsed)
        except:
            return []
    elif isinstance(characters_data, dict):
        if "characters" in characters_data:
            chars_list = characters_data["characters"]
        else:
            chars_list = [characters_data]
    elif isinstance(characters_data, list):
        chars_list = characters_data
    else:
        return []
    
    if not isinstance(chars_list, list):
        return []
    
    names_list = []
    for char in chars_list:
        if not isinstance(char, dict):
            continue
        name = char.get("name", "").strip()
        if not name:
            continue
        role = char.get("role", "").strip()
        if role:
            names_list.append(f"{name}({role})")
        else:
            names_list.append(name)
    
    return names_list

def extract_worldview_summary(worldview_text):
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
                    worldview_content = worldview_content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\n...（內容過長已截斷）"
                summary_parts.append(f"【世界觀設定】\n{worldview_content}")
            
            # 整體故事大綱
            macro_outline = parsed.get("macro_outline", "")
            if macro_outline:
                if len(macro_outline) > MAX_MACRO_OUTLINE_LENGTH:
                    macro_outline = macro_outline[:MAX_MACRO_OUTLINE_LENGTH] + "\n...（內容過長已截斷）"
                summary_parts.append(f"【整體故事大綱】\n{macro_outline}")
            
            # 如果有摘要則返回
            if summary_parts:
                return "\n\n".join(summary_parts)
    except json.JSONDecodeError:
        # JSON 解析失敗，使用純文字解析
        pass
    
    # Fallback: 嘗試用文本方式提取
    # 找 【世界觀設定】 和 【整體故事大綱】 區塊
    result_parts = []
    
    lines = worldview_text.split('\n')
    current_section = None
    section_content = []
    
    for line in lines:
        line = line.strip()
        if '【世界觀設定】' in line:
            # 保存前一個區塊
            if current_section == 'worldview' and section_content:
                content = '\n'.join(section_content)
                if len(content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
                    content = content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\n...（內容過長已截斷）"
                result_parts.append(f"【世界觀設定】\n{content}")
            current_section = 'worldview'
            section_content = []
        elif '【整體故事大綱】' in line:
            if current_section == 'worldview' and section_content:
                content = '\n'.join(section_content)
                if len(content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
                    content = content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\n...（內容過長已截斷）"
                result_parts.append(f"【世界觀設定】\n{content}")
            current_section = 'macro_outline'
            section_content = []
        elif current_section:
            section_content.append(line)
    
    # 保存最後一個區塊
    if current_section == 'worldview' and section_content:
        content = '\n'.join(section_content)
        if len(content) > MAX_WORLDVIEW_SUMMARY_LENGTH:
            content = content[:MAX_WORLDVIEW_SUMMARY_LENGTH] + "\n...（內容過長已截斷）"
        result_parts.append(f"【世界觀設定】\n{content}")
    elif current_section == 'macro_outline' and section_content:
        content = '\n'.join(section_content)
        if len(content) > MAX_MACRO_OUTLINE_LENGTH:
            content = content[:MAX_MACRO_OUTLINE_LENGTH] + "\n...（內容過長已截斷）"
        result_parts.append(f"【整體故事大綱】\n{content}")
    
    if result_parts:
        return "\n\n".join(result_parts)
    
    # 最終 fallback: 返回原始文本的前面部分
    truncated = worldview_text[:MAX_WORLDVIEW_SUMMARY_LENGTH]
    if len(worldview_text) > MAX_WORLDVIEW_SUMMARY_LENGTH:
        truncated += "\n...（內容過長已截斷）"
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
    return f"\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this schema. Wrap in ```json ... ``` codeblock]\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n"

def build_story_architect_messages(genre, style, user_prompt):
    """世界觀架構師提示詞拼接"""
    # 這裡的 STORY_ARCHITECT_PROMPT 包含了 generate_style
    # 為了告知模型多幕式與多波段不限於 3，我們加入說明引導
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    system_prompt = f"{STORY_ARCHITECT_PROMPT.format(generate_style=style)}\n\n{schema_snippet}\n"
    # 強調可以任意增長/縮短 multi_act_structure 與 progressive_character_plan 的長度，不限於 3 個元素
    system_prompt += "\n*[提示：`multi_act_structure` 與 `progressive_character_plan` 可以依據需要規劃任意數量的多幕/波段（例如：4幕、5波等），無須限制為範例中的數量。]*\n"
    
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
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\n\n{schema_snippet}\n"
    
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
                    target_char_content = f"\n【被修改角色的完整內容 (Index {target_char_index})】\n{json.dumps(chars_list[target_char_index], ensure_ascii=False, indent=2)}"
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
    system_prompt = f"{VOLUMES_PLANNER_PROMPT}\n\n{schema_snippet}\n"
    
    if mode == "generate":
        vols_context = ""
        if existing_vols:
            vols_context = "\n【現有已規劃篇卷概述】\n"
            for v in existing_vols:
                vols_context += f"- 卷 {v['volume_index']}：{v['title']} (大綱: {v['summary']})\n"
                
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
            surrounding_context += f"\n【前 1 卷 (卷 {v_idx - 1}) 大綱與概要】\n標題：{pre_vol['title']}\n概要：{pre_vol['summary']}\n"
        if next_vol:
            surrounding_context += f"\n【後 1 卷 (卷 {v_idx + 1}) 大綱與概要】\n標題：{next_vol['title']}\n概要：{next_vol['summary']}\n"
            
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
    system_prompt = f"{VOLUME_SKELETON_PROMPT.format(volume_index=volume_index, start_ch=start_ch, end_ch=end_ch, vol_chapter_count=vol_chapter_count)}\n\n{schema_snippet}\n"
    
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
    system_prompt = f"{PLOT_PLANNER_PROMPT.format(seens='對於骨架中指定的 ⚠️【硬性指定埋設伏筆】 與 ⚠️【硬性指定回收伏筆】，你必須在對應章節的 foreshadowing_plant 與 foreshadowing_payoff 欄位中完美承接並展開編織，不得遺漏！', turning_points='對於骨架中指定的 配合指定關鍵轉折點進展，你必須在對應章節的 turning_points 欄位中確實寫入，並在情節中給予充足的戲劇爆發張力！')}\n\n{schema_snippet}\n"
    
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
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_copilot_chat_messages(worldview_text, characters_text, plot_text, history_context, user_message):
    """Copilot 創意決策總監聊天提示詞"""
    validation_report = "底層校驗一切正常。全階段架構完備。"
    written_chapters_text = "未進入正文寫作"
    
    # 對角色聖經進行基本設定篩選
    characters_filtered = extract_character_basic(characters_text)
    
    # 填充 CO_PILOT_ORCHESTRATOR_PROMPT
    system_prompt = CO_PILOT_ORCHESTRATOR_PROMPT.format(
        worldview=worldview_text[:300] + "...",
        characters=json.dumps(characters_filtered, ensure_ascii=False)[:300] + "...",
        plot=plot_text[:300] + "...",
        written_chapters=written_chapters_text,
        validation_report=validation_report
    )
    
    user_content = f"""【當前專案狀態】
- 世界觀：{worldview_text[:300]}...
- 角色 Bible：{json.dumps(characters_filtered, ensure_ascii=False)[:300]}...
- 大綱概要：{plot_text[:300]}...

【最近對話歷史】
{history_context}

【使用者最新輸入】
{user_message}

請以總監身份給出精彩回覆，並在末尾推薦對應的 Flow 狀態 JSON 區塊。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_director_decision_messages(current_stage, worldview_text, characters_text, plot_text, written_chapters_text, user_prompt):
    """總監決策評判提示詞"""
    system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前階段的創作質量，並決定下一步的最佳動作。

【審查原則】
1. 當前階段是「{current_stage}」。
2. 對比使用者的原始意圖，檢查是否有邏輯跳躍、設定穿幫、或者是套用流水帳的情形。
3. ⚠️ 【Plot / Outline 階段強制放行】：若當前階段是 `plot` 或 `plot_review`，除非有嚴重人物缺失需要 `GO_BACK_TO_CHARACTERS`，否則必須直接給出 `CONTINUE`，不得故意阻斷。

{DIRECTOR_COMMON_FOOTER.format(current_stage=current_stage)}
"""
    # 取得角色名稱列表（"名字(role)" 格式），確保總監能看到完整角色識別
    characters_names_list = extract_character_names_list(characters_text)
    characters_names_str = "、".join(characters_names_list) if characters_names_list else "尚無角色設定"
    
    # 對角色聖經進行基本設定篩選
    characters_filtered = extract_character_basic(characters_text)
    
    user_content = f"""【創作主軸需求】
{user_prompt}

【當前各板塊詳細數據】
- 世界觀設定：{worldview_text[:1500] + "以下截斷..." }
- 角色清單（完整）：{characters_names_str}
- 角色 Bible（基本設定）：{json.dumps(characters_filtered, ensure_ascii=False)}
- 章節大綱：{plot_text[:1500] + "以下截斷..." }
- {written_chapters_text}

請進行深度評估，決定下一步行動！
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_director_decision_help_messages(help_reason, target_data):
    """總監調閱輔助決策提示詞"""
    system_prompt = """你是一位極度嚴格的小說創作總監。你剛剛調閱了完整的詳細板塊數據。
請在仔細審閱調閱數據後，給出最深刻、最犀利的洞察反饋，並決定下一步的實質決策 action (如 CONTINUE, GO_BACK_TO_plot, MODIFY_CURRENT_CHAPTER 等)。

請直接輸出【審閱反饋】，並在最後輸出 JSON 指令區塊。
"""
    user_content = f"""【總監調閱原因】
{help_reason}

【被調閱板塊數據】
{target_data}

請提供分析並給出下一步決策 JSON。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_incremental_architect_messages(target_section, worldview_text, user_hint):
    """增量世界觀提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    system_prompt = f"""你是一位精準的世界觀增量修正師。請根據用戶的修改要求，對現有的世界觀進行精準的局部修改或增量追加。
你只需要回傳【本次有新增或被修改的 {target_section}】的內容 JSON 區塊即可，後端會自動完成替換與合併。

{schema_snippet}
"""
    user_content = f"""【現有世界觀】
{worldview_text}

【目標修改板塊】
- target_section: {target_section}

【使用者修改要求 (user_hint)】
{user_hint}

請輸出更新後的 JSON 區塊：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_incremental_character_messages(worldview_text, existing_chars_json, target_char_content, target_char_index, field_name, user_hint):
    """增量角色修改提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("character")
    
    if target_char_index is not None:
        if field_name:
            # Modify specific field of character
            system_prompt = INCREMENTAL_CHARACTER_PROMPT.format(
                existing_worldbuilding=worldview_text,
                existing_characters=existing_chars_json + "\n" + target_char_content,
                user_hint=f"請修改角色索引 {target_char_index} 的 {field_name} 欄位。具體修改要求：{user_hint}"
            )
        else:
            # Modify full character design
            system_prompt = CHARACTER_DESIGNER_PROMPT_PLUS.format(
                hints=f"修改角色索引 {target_char_index} 的完整角色設定。要求：{user_hint}\n現有角色聖經：\n{existing_chars_json}\n被修改角色原設定：\n{target_char_content}"
            )
    else:
        # Append mode
        system_prompt = INCREMENTAL_CHARACTER_APPEND_PROMPT.format(
            existing_worldbuilding=worldview_text,
            existing_characters=existing_chars_json,
            new_characters="請根據修改要求追加新角色",
            user_hint=user_hint
        )
        
    system_prompt += f"\n\n{schema_snippet}"
    
    user_content = f"""請根據以上增量指令與規則，輸出更新後的 JSON 區塊："""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_incremental_skeleton_messages(worldview_text, volume_index, existing_skeleton, user_hint):
    """卷骨架增量修正提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = VOLUME_SKELETON_PROMPT_PLUS.format(hints=user_hint) + f"\n\n{schema_snippet}"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前篇卷】
- 卷索引: {volume_index}

【現有骨架大綱】
{existing_skeleton}

【修改要求】
{user_hint}

請僅針對第 {volume_index} 卷的章節大綱骨架進行修改，並回傳格式完全合法的 chapters_skeleton JSON。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_incremental_plot_planner_messages(worldview_text, plot_text, insert_after_index, user_hint):
    """增量大綱更新提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("plot")
    system_prompt = f"""你是一位精準的劇情大綱增量修正師。請根據用戶的要求，在指定位置增量插入或修改章節大綱。
你只需要回傳【本次新增/修改的章節大綱】列表即可，後端會自動完成替換與合併。

{schema_snippet}
"""
    user_content = f"""【世界觀背景】
{worldview_text}

【現有詳細章節大綱】
{plot_text}

【插入位置】
- 插入在第 {insert_after_index} 章之後

【使用者修改要求 (user_hint)】
{user_hint}

請輸出新增的章節大綱 JSON：
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]