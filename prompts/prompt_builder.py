# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
import agent_json
from agent_json import CHARACTER_BASIC_FIELDS
from prompts.prompt_main import (
    STORY_ARCHITECT_PROMPT,
    VOLUMES_PLANNER_PROMPT,
    VOLUME_SKELETON_PROMPT,
    CHARACTER_DESIGNER_PROMPT,
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
MAX_WORLDVIEW_SUMMARY_LENGTH = 999999  # 徹底砍掉 1500 字上限，以完整設定提供大上下文
MAX_MACRO_OUTLINE_LENGTH = 999999       # 徹底砍掉大綱長度限制

# --- 角色基本設定輔助函數 ---
# 定義角色只需要傳入的基本欄位，過濾掉冗長的背景故事等欄位
# 核心欄位：name 和 personality 是必留的，其他可以過濾
# CHARACTER_BASIC_FIELDS 定義在 agent_json.py 中，供各模組統一引用

MAX_CHARACTERS_SUMMARY_LENGTH = 999999  # 徹底砍掉角色摘要長度限制

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
            summary_parts = []
            
            fields_to_extract = {
                "theme": "【核心主題】",
                "main_conflict": "【核心衝突】",
                "worldview": "【世界觀設定】",
                "macro_outline": "【整體故事大綱】",
                "multi_act_structure": "【多幕結構】",
                "progressive_character_plan": "【角色漸進規劃】"
            }
            
            for key, title in fields_to_extract.items():
                val = parsed.get(key, "")
                if val:
                    if isinstance(val, (list, dict)):
                        val = json.dumps(val, ensure_ascii=False, indent=2)
                    summary_parts.append(f"{title}\n{val}")
                
            if summary_parts:
                return "\n\n".join(summary_parts)
    except json.JSONDecodeError:
        pass
        
    return worldview_text

def get_json_schema_prompt_snippet(schema_name):
    """取得 JSON 格式綱要說明字串，已徹底移除非法 Python set literal {...} 以防 JSON 序列化失敗。"""
    schema_map = {
        "worldview": agent_json.WORLDVIEW_SCHEMA,
        "character": agent_json.CHARACTERS_ROOT_SCHEMA,
        "volumes": {"volumes": [agent_json.VOLUME_SCHEMA]},
        "skeleton": {"volume_index": 1, "chapters_skeleton": [agent_json.CHAPTER_SKELETON_WITH_ALLOC_SCHEMA]},
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
        user_content = f"""【世界觀背景】
{worldview_text}

【使用者大綱/要求】
{user_prompt or "請根據完整世界觀，自行決定全書的卷數、每卷標題、概要與章節數量設定。"}

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

def build_chapter_writer_messages(worldview_text, characters_bible, current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, custom_style, chapter_index, user_prompt=None):
    """正文作家寫作提示詞拼接"""
    system_prompt = CHAPTER_WRITER_PROMPT.format(writing_style=custom_style)
    
    # 對角色 Bible 進行基本設定篩選，避免過長導致 API 失敗
    characters_bible_filtered = extract_character_basic(characters_bible)
    
    extra_prompt_block = ""
    if user_prompt and str(user_prompt).strip():
        extra_prompt_block = f"""
【本章額外創作指令】
{str(user_prompt).strip()}
"""

    user_content = f"""【世界觀背景】
{worldview_text}

【角色 Bible 聖經】(基本設定)
{json.dumps(characters_bible_filtered, ensure_ascii=False, indent=2)}

【當前章節 (第 {chapter_index} 章) 大綱】
{json.dumps(current_outline, ensure_ascii=False, indent=2)}

{surrounding_plot}
{vol_outline_context}
{clue_payoff_details}
{extra_prompt_block}

請根據以上豐富的上下文細節，展開本章正文寫作，字數適中。
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

def simplify_plot_data_for_copilot(plot_text):
    if not plot_text or not isinstance(plot_text, str) or plot_text.startswith("尚無"):
        return plot_text
    try:
        data = json.loads(plot_text)
        if isinstance(data, dict):
            if "volumes" in data:
                vols = data["volumes"]
                simplified_vols = []
                for v in vols:
                    v_copy = dict(v)
                    if "chapters_outline" in v_copy:
                        if isinstance(v_copy["chapters_outline"], list):
                            v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                        else:
                            v_copy["chapters_outline"] = "尚未生成骨架"
                    simplified_vols.append(v_copy)
                return json.dumps({"volumes": simplified_vols}, ensure_ascii=False, indent=2)
            elif "chapters" in data:
                chapters = data["chapters"]
                simplified_chapters = []
                for ch in chapters:
                    if isinstance(ch, dict):
                        simplified_ch = {
                            "chapter_index": ch.get("chapter_index") or ch.get("chapter") or ch.get("index"),
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or ch.get("brief_title") or "未命名章節",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or ch.get("brief_summary") or "（尚無摘要說明）"
                        }
                        simplified_chapters.append(simplified_ch)
                return json.dumps({"chapters": simplified_chapters}, ensure_ascii=False, indent=2)
        elif isinstance(data, list):
            if data and "volume_index" in data[0]:
                simplified_vols = []
                for v in data:
                    v_copy = dict(v)
                    if "chapters_outline" in v_copy:
                        if isinstance(v_copy["chapters_outline"], list):
                            v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                        else:
                            v_copy["chapters_outline"] = "尚未生成骨架"
                    simplified_vols.append(v_copy)
                return json.dumps(simplified_vols, ensure_ascii=False, indent=2)
            else:
                simplified_chapters = []
                for ch in data:
                    if isinstance(ch, dict):
                        simplified_ch = {
                            "chapter_index": ch.get("chapter_index") or ch.get("chapter") or ch.get("index"),
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or ch.get("brief_title") or "未命名章節",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or ch.get("brief_summary") or "（尚無摘要說明）"
                        }
                        simplified_chapters.append(simplified_ch)
                return json.dumps(simplified_chapters, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to simplify plot data for copilot: {e}")
    return plot_text


def build_copilot_chat_messages(novel_id, worldview_text, characters_text, plot_text, history_context, user_message, validation_report=None):
    """Copilot 創意決策總監聊天提示詞"""
    if not validation_report:
        validation_report = "底層校驗一切正常。全階段架構完備。"
    
    from diagnostics import diagnose_all_phases
    diags = diagnose_all_phases(novel_id)
    
    # 填充 CO_PILOT_ORCHESTRATOR_PROMPT
    system_prompt = CO_PILOT_ORCHESTRATOR_PROMPT.format(
        worldview=diags["worldview"],
        characters=diags["characters"],
        plot=diags["plot"],
        written_chapters=diags["written_chapters"],
        validation_report=validation_report
    )
    
    # Filter/simplify the inputs to keep context token count safe but provide actual content
    worldview_summary = worldview_text
    
    characters_filtered = extract_character_basic(characters_text)
    characters_summary = json.dumps(characters_filtered, ensure_ascii=False, indent=2) if isinstance(characters_filtered, dict) else str(characters_filtered)
    
    plot_summary = simplify_plot_data_for_copilot(plot_text)
    
    user_content = f"""【當前專案實際設定與大綱內容】
- 【世界觀主題與設定】：
{worldview_summary}

- 【角色 Bible 聖經（基本人設）】：
{characters_summary}

- 【全書篇卷與大綱（簡化版）】：
{plot_summary}

【目前系統診斷狀態】
- 世界觀：{diags["worldview"]}
- 角色 Bible：{diags["characters"]}
- 大綱概要：{diags["plot"]}

【最近對話歷史】
{history_context}

【使用者最新輸入】
{user_message}

請以總監身份給出專業回覆意見，並在末尾推薦對應的 Flow 狀態 JSON 區塊。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def mask_worldview_seeds_and_turns(worldview_text):
    if not worldview_text:
        return worldview_text
    
    try:
        parsed = json.loads(worldview_text)
        if isinstance(parsed, dict):
            if "foreshadowing_seeds" in parsed:
                parsed["foreshadowing_seeds"] = "此區塊通過審核不需評判"
            if "key_turning_points" in parsed:
                parsed["key_turning_points"] = "此區塊通過審核不需評判"
            return json.dumps(parsed, ensure_ascii=False, indent=2)
    except:
        pass
        
    content = worldview_text
    headers = [
        "【核心主題】",
        "【核心衝突】",
        "【世界觀設定】",
        "【整體故事大綱】",
        "【多幕式結構】",
        "【角色漸進規劃策略】",
        "【伏筆種子】",
        "【關鍵轉折點】"
    ]
    
    pos = []
    for h in headers:
        idx = content.find(h)
        if idx != -1:
            pos.append((idx, h))
    pos.sort()
    
    if not pos:
        return worldview_text
        
    new_parts = []
    last_end = 0
    for i in range(len(pos)):
        start_idx = pos[i][0]
        header = pos[i][1]
        end_idx = pos[i+1][0] if i + 1 < len(pos) else len(content)
        
        if start_idx > last_end:
            new_parts.append(content[last_end:start_idx])
            
        if header in ["【伏筆種子】", "【關鍵轉折點】"]:
            new_parts.append(f"{header}\n此區塊通過審核不需評判\n")
        else:
            new_parts.append(content[start_idx:end_idx])
            
        last_end = end_idx
        
    if last_end < len(content):
        new_parts.append(content[last_end:])
        
    return "".join(new_parts)

def build_director_decision_messages(
    novel_id,
    current_stage,
    worldview_text,
    characters_text,
    plot_text,
    written_chapters_text,
    user_prompt,
    validation_report,
    character_review_mode=None,
    character_review_hint=None,
    character_review_target_content=None,
    suggested_next_chapter=None,
    chapter_index=None,
    director_context_block=None
):
    from diagnostics import diagnose_all_phases
    diags = diagnose_all_phases(novel_id)
    """總監決策評判提示詞
    
    根據不同階段傳入對應的審查內容：
    - worldview: 完整世界觀內容 + 評斷提示詞
    - characters: 完整角色列表
    - volumes: 完整卷列表 + 世界觀的 macro_outline
    - volume_skeleton: 完整骨架(每2卷一組) + 世界觀的 macro_outline
    - writer: 該章的完整內容(正文+大綱+角色聖經+伏筆)
    - editor: 該章的完整潤色內容
    """
    # 取得該階段的通過標準
    from agent_json import format_criteria_for_prompt
    stage_criteria = format_criteria_for_prompt(current_stage)
    
    # 取得世界觀的 macro_outline
    macro_outline = ""
    if worldview_text:
        try:
            parsed = json.loads(worldview_text)
            macro_outline = parsed.get("macro_outline", "")
        except:
            # 嘗試從文本提取
            if "【整體故事大綱】" in worldview_text:
                parts = worldview_text.split("【整體故事大綱】")
                if len(parts) > 1:
                    macro_outline = parts[1].strip()
                    
    # 總監評斷世界觀時需要完整傳入，而其他階段已經通過審核，將其內部的伏筆與轉折欄位改為 "此區塊通過審核不需評判"
    if current_stage != "worldview":
        worldview_text = mask_worldview_seeds_and_turns(worldview_text)

    # 根據 current_stage 構建不同的審查內容
    if current_stage == "worldview":
        # 世界觀階段：只傳世界觀完整內容 + 評斷提示詞
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前世界觀的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（世界觀架構師）。
2. 對比使用者的原始意圖，檢查世界觀是否完整且具備深度。
3. 確認伏筆種子與關鍵轉折點是否足夠且相互呼應。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""【使用者原始需求】
{user_prompt}
 
【完整世界觀設定】
{worldview_text}
 
請進行深度評估，決定下一步行動！
"""
    
    elif current_stage == "characters":
        # 角色階段：完整角色列表
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前角色設計的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（角色設計師）。
2. 角色關係網是否邏輯連貫。
3. 確認角色的心理深度、成長弧線是否完整。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        character_extra_context = ""
        if character_review_mode in ("modify", "expand") and character_review_hint:
            character_extra_context += f"\n\n【本次修改/新增的總監指示 (Hint)】\n{character_review_hint}"
        if character_review_mode in ("modify", "expand") and character_review_target_content:
            character_extra_context += f"\n\n【被修改/新增角色的完整內容】\n{character_review_target_content}"
        if character_review_mode == "generate":
            character_extra_context = "\n\n【重要】此為世界觀生成後的首次角色生成，請確認角色陣容是否完整且與世界觀設定契合。"
        
        user_content = f"""【世界觀背景】
{worldview_text}
 
【完整角色列表（完整設定）】
{characters_text}
{character_extra_context}
 
請進行深度評估，決定下一步行動！
"""
    
    elif current_stage == "volumes":
        # 卷階段：完整卷列表 + 世界觀的 macro_outline
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前篇卷規劃的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（篇卷規劃師）。
2. 檢查卷結構是否與世界觀的 multi_act_structure 呼應。
3. 確認每卷的功能定位是否明確，情節銜接是否連貫。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""【世界觀的整體故事大綱 (macro_outline)】
{macro_outline}
 
【完整篇卷列表（完整設定）】
{plot_text}
 
請進行深度評估，決定下一步行動！
"""
    
    elif current_stage == "volume_skeleton":
        # 骨架階段：完整骨架(每2卷一組) + 世界觀的 macro_outline
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前卷骨架的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（篇卷骨架規劃師）。
2. 檢查骨架是否和該卷的設定相關。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""【世界觀的整體故事大綱 (macro_outline)】
{macro_outline}
 
【完整卷骨架列表（完整設定）】
{plot_text}
 
請進行深度評估，決定下一步行動！
"""
    

    elif current_stage == "writer":
        # 寫作階段：該章的完整內容(正文+大綱+角色聖經+伏筆+後三章伏筆回收預告)
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前章節正文的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（正文寫作作家）。
2. 檢查角色台詞、語氣、動作是否100%符合角色聖經。
3. 確認伏筆是否自然融入，轉折點是否有足夠鋪陳。
4. ⚠️【後三章伏筆預埋審查】：請特別注意檢查「clue_payoff_upcoming_3_chapters」中預告的後三章即將回收之伏筆，是否已在本章正文中有合理的前置鋪墊與自然埋入。
5. 角色聖經的配角欄位缺失不是 writer 階段阻斷理由；除非主角資料缺失已明顯造成正文無法寫作，否則不得改派角色修補，應繼續 writer/editor 流程。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        # 對角色聖經進行基本設定篩選
        characters_filtered = extract_character_basic(characters_text)
        user_content = f"""【世界觀背景】
{worldview_text}
 
【角色 Bible 聖經（基本設定）】
{json.dumps(characters_filtered, ensure_ascii=False, indent=2)}
 
【當前章節大綱】
{plot_text}
 
【本章正文（完整內容）】
{written_chapters_text}
 
請進行深度評估，決定下一步行動！
"""
    
    elif current_stage == "editor":
        # 編輯階段：該章的完整潤色內容
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前潤色後正文的質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（編輯姬）。
2. 檢查潤色後是否比原版有明顯提升。
3. 確認角色人設、大綱走向、伏筆完整性是否保持。
4. 角色聖經的配角欄位缺失不是 editor 階段阻斷理由；若本章正文與大綱可正常審核，應放行到下一章 writer。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        extra_guideline = ""
        current_ch = chapter_index if chapter_index is not None else 1
        if suggested_next_chapter is not None:
            # 檢查是否為非常規（如補寫、補充缺漏章節）
            is_supplementary = (suggested_next_chapter != current_ch + 1)
            supp_msg = "（⚠️ 此為補充/填補缺漏章節）" if is_supplementary else ""
            extra_guideline = f"\n\n💡【編輯姬審核後前往下一章指引】{supp_msg}：當前審查的章節為第 {current_ch} 章。本系統建議的下一章計畫前往：第 {suggested_next_chapter} 章。若此章為補齊先前缺漏的章節或繼續推展，請優先在 JSON 決策中將 `chapter_index` 設為 {suggested_next_chapter}，並將 `target` 設為 `writer`，以利全自動管線能無縫銜接到正確的章節位置。"

        user_content = f"""【世界觀背景】
{worldview_text}
 
【原章節大綱】
{plot_text}
 
【潤色後正文（完整內容）】
{written_chapters_text}{extra_guideline}
 
請進行深度評估，決定下一步行動！
"""
    
    else:
        # 默認通用格式
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前階段的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」。
2. 對比使用者的原始意圖，檢查是否有邏輯跳躍、設定穿幫、或者是套用流水帳的情形。
3. ⚠️ 【Plot / Outline 階段強制放行】：若當前階段是 `plot` 或 `plot_review`，除非有嚴重人物缺失需要 `GO_BACK_TO_CHARACTERS`，否則必須直接給出 `CONTINUE`，不得故意阻斷。
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""【創作主軸需求】
{user_prompt}
 
【當前各板塊數據】
- 世界觀設定：{worldview_text[:1500] if worldview_text else "（空）"}
- 角色設定：{characters_text[:1500] if characters_text else "（空）"}
- 大綱設定：{plot_text[:1500] if plot_text else "（空）"}
- 正文：{written_chapters_text if written_chapters_text else "（空）"}
 
請進行深度評估，決定下一步行動！
"""
    
    if current_stage in ("volumes", "volume_skeleton", "writer", "editor"):
        system_prompt += """

## 伏筆/轉折審核紅線
1. 伏筆與轉折的硬性位置，以 Python 預計算分配表與章節大綱 allocated_tasks 為唯一依據。
2. 世界觀 foreshadowing_seeds / key_turning_points 內的 act、stage、volume、chapter 等欄位，只是早期草稿參考，不得當成本階段硬性任務。
3. 你不得在審核時臨時發明新的伏筆/轉折義務，也不得要求 Agent 隨意新增未分配的伏筆。
4. 若某章/某卷沒有被分配 plant、payoff 或 turning point，請只做一般品質審核，不得因「應該有伏筆感」而退回。
5. 若要退回修改，必須引用分配表中的 seed_id / turn_id、指定章節與缺失位置。
"""

    if suggested_next_chapter is not None:
        if current_stage in ("writer", "editor"):
            system_prompt += f"\n\n💡【系統寫作計畫指引】：若本次審核放行並準備繼續正文寫作，系統建請下一章前往：第 {suggested_next_chapter} 章（這可能是一般的順序下一章，或是為了補齊斷檔/缺漏的章節）。請在輸出 JSON 決策時，優先將 `chapter_index` 設為 {suggested_next_chapter}，並將 `target` 設為 `writer`。\n"
        elif current_stage == "volume_skeleton":
            system_prompt += f"\n\n💡【系統寫作計畫指引】：若剛性校驗報告確認【所有卷】的骨架皆已完全生成且無缺漏，準備放行進入正文寫作階段時，系統建請從第 {suggested_next_chapter} 章開始寫作。請在決策放行且 target 為 writer 時，將 `chapter_index` 設為 {suggested_next_chapter}。\n"

    system_prompt += f"\n\n## 系統底層剛性校驗報告（Python 計算絕對事實，請以此為準）\n{validation_report}\n"
    
    if director_context_block:
        user_content += f"\n\n{director_context_block}"

    # 統一在 user_content 尾端附加額外的 user_prompt，確保大綱、寫作或編輯階段也能接收此提示 (包括錯誤自癒報告)
    if user_prompt and user_prompt.strip() and "【使用者原始需求】" not in user_content:
        user_content += f"\n\n【使用者指示 / 系統錯誤自癒回報（請優先滿足此要求）】\n{user_prompt.strip()}"
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_director_decision_help_messages(help_reason, target_data):
    """總監調閱輔助決策提示詞"""
    system_prompt = """你是一位極度嚴格的小說創作總監。你剛剛調閱了完整的詳細板塊數據。
請在仔細審閱調閱數據後，給出最深刻、最犀利的洞察反饋，並決定下一步的實質決策 action (如 CONTINUE, GO_BACK_TO_SKELETON_EXPANSION, MODIFY_CURRENT_CHAPTER 等)。

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
    if field_name:
        patch_schema = {
            field_name: "只填此欄位的新值；可以是字串、陣列或物件，依原欄位型別決定"
        }
    elif target_char_index is not None:
        patch_schema = {
            "character": {
                "name": "只有需要修改名稱時才填",
                "role": "可省略未修改欄位",
                "personality": ["可只回傳被修改欄位"],
                "want": "可省略",
                "need": "可省略",
                "fatal_flaw": "可省略",
                "motivation": "可省略",
                "arc": "可省略",
                "speech_style": "可省略",
                "appearance": "可省略",
                "background": "可省略",
                "relationships": []
            }
        }
    else:
        patch_schema = {
            "characters": [
                {
                    "name": "新角色具體姓名/代號",
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
            ]
        }
    schema_snippet = (
        "\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this incremental patch schema. "
        "Wrap in ```json ... ``` codeblock]\n"
        f"{json.dumps(patch_schema, ensure_ascii=False, indent=2)}\n"
    )
    
    if target_char_index is not None:
        if field_name:
            # Modify specific field of character
            system_prompt = INCREMENTAL_CHARACTER_PROMPT.format(
                existing_worldbuilding=worldview_text,
                existing_characters=existing_chars_json + "\n" + target_char_content,
                user_hint=f"請只修改角色索引 {target_char_index} 的 `{field_name}` 欄位。具體修改要求：{user_hint}\n\n輸出只能包含 `{field_name}` 或 `value/new_value`，不得輸出其他未修改角色。"
            )
        else:
            # Modify full character design
            system_prompt = INCREMENTAL_CHARACTER_PROMPT.format(
                existing_worldbuilding=worldview_text,
                existing_characters=existing_chars_json + "\n" + target_char_content,
                user_hint=f"請局部修正角色索引 {target_char_index}。要求：{user_hint}\n\n只輸出本角色被修改欄位的 patch；未修改欄位請省略，後端會與原角色深度合併。不得回傳完整角色列表。"
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
    patch_schema = {
        "volume_index": volume_index,
        "chapters_skeleton": [
            {
                "chapter_index": "必填：要修改的絕對章節序號",
                "chapter_title": "可省略未修改欄位",
                "chapter_summary": "可省略未修改欄位",
                "time_setting": "可省略未修改欄位",
                "scene_setting": "可省略未修改欄位",
                "events": "若修改事件，回傳完整的新 events 陣列",
                "characters_active": "可省略未修改欄位",
                "emotional_tone": "可省略未修改欄位",
                "cliffhanger": "可省略未修改欄位",
                "allocated_tasks": "除非明確要求修改伏筆/轉折，否則省略"
            }
        ]
    }
    schema_snippet = (
        "\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this incremental skeleton patch schema. "
        "Wrap in ```json ... ``` codeblock]\n"
        f"{json.dumps(patch_schema, ensure_ascii=False, indent=2)}\n"
    )
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
只回傳被修改或新增補全的章節物件；每個物件必須包含 chapter_index。未修改章節不要回傳，未修改欄位請省略，後端會按 chapter_index 深度合併。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

