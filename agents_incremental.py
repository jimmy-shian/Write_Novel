"""
增量生成 Agent 函數 - 細粒度編輯功能
這些函數允許對 JSON 的子項目進行單獨修改，而不是全部重新生成
"""

import json
from db import (
    get_latest_worldbuilding,
    get_latest_characters,
    get_latest_plot_chapters,
    get_latest_chapter,
    get_all_chapters_latest,
    save_worldbuilding,
    save_characters,
    save_plot_chapters,
    append_foreshadowing,
    insert_plot_chapter,
    update_character_single_field,
    parse_worldview_to_json
)
from llm import call_llm_stream

# ============================================================
# INCREMENTAL WORLDVIEW (增量世界觀生成)
# ============================================================

INCREMENTAL_ARCHITECT_PROMPT = """你是故事架構師，專精於對現有世界觀進行局部增強與擴充。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

## 核心原則
1. **局部修改**：只生成/修改指定的特定部分，不重新生成全部內容。
2. **保持一致**：新增內容必須與現有世界觀設定保持邏輯一致性。
3. **精煉輸出**：只輸出用戶要求的內容，不輸出多餘解釋。

## 任務類型
根據 target_section 不同，專注於生成對應的內容：
- "foreshadowing_seeds"：生成新的伏筆種子（3-5個），每個包含早期埋設與後期收束方式。
- "multi_act_structure"：生成/修改多幕式結構。
- "progressive_character_plan"：生成/修改角色漸進規劃策略。
- "key_turning_points"：生成/修改關鍵轉折點。
- "volumes"：局部修正或新增篇卷（Volumes）大綱與故事時間軸配置。你的任務是針對篇卷標題、概要、活躍勢力、章節數(chapter_count)、故事時間軸起迄(time_timeline)、續作系列定位(sequence_context)以及世界法則(applicable_rules)進行精準的局部修改或新增，並輸出完整的 "volumes" 陣列配置，包含所有已存在篇卷（未修改的卷予以保留，已修改/新增的卷在陣列中予以替換/追加），確保 volume_index 從 1 開始順序連續。

## 輸出絕對限制（反格式污染）
1. 你是一個精準的後端 API 數據節點。嚴禁包含任何如「好的，這是我為您修改的設定...」等寒暄、過渡、解釋性旁白。
2. 你【只能且必須】回傳一個格式完全合法、可被 Python json.loads() 直接解析的標準 JSON 物件。
3. 必須嚴格包裹在 ```json ... ``` 區塊中。
4. 如果 target_section 是 "volumes"，請確保輸出的 JSON 物件最外層有 "volumes" 鍵值，或是直接輸出 volumes 陣列包裹在物件中，例如：{"volumes": [...] }。每個篇卷物件必須包含：volume_index, title, summary, factions, chapter_count, time_timeline, sequence_context, applicable_rules。

## 現有世界觀（局部上下文）
{existing_worldbuilding}

## 用戶要求
target_section: {target_section}
user_hint: {user_hint}
"""

def run_incremental_architect(novel_id, target_section, user_hint):
    """
    增量生成世界觀的特定部分
    
    Args:
        novel_id: 小說 ID
        target_section: 要生成的部分，如 "foreshadowing_seeds", "multi_act_structure"
        user_hint: 用戶的提示
    """
    wb = get_latest_worldbuilding(novel_id)
    existing_content = wb["content"] if wb else "尚無世界觀設定"
    
    prompt = INCREMENTAL_ARCHITECT_PROMPT.format(
        existing_worldbuilding=existing_content,
        target_section=target_section,
        user_hint=user_hint
    )
    
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"請基於以上現有世界觀，{user_hint}\n\n只輸出與 {target_section} 相關的內容。"}
    ]
    
    def save_callback(nid, text):
        import json
        wb = get_latest_worldbuilding(nid)
        existing_content = wb["content"] if wb else ""
        
        current_json = parse_worldview_to_json(existing_content)
        parsed = parse_json_safely(text)
        
        # 💡 嚴格防禦：若 LLM 污染嚴重無法解析 JSON，直接報錯不進行髒數據縫合
        if parsed is None or (isinstance(parsed, dict) and "error" in parsed):
            try:
                import sys
                encoding = sys.stdout.encoding or "utf-8"
                safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
                print(f"[ERROR] 增量生成失敗，模型未返回標準 JSON 數據。原始文字：\n{safe_text}")
            except Exception:
                pass
            return
            
        # 直接進行結構化 JSON 的精準 Key 縫合
        if target_section in ["foreshadowing_seeds", "key_turning_points"]:
            # 支援 LLM 直接回傳純陣列，或是包在 Key 裡面的物件
            new_items = parsed if isinstance(parsed, list) else parsed.get(target_section, [])
            if isinstance(new_items, list) and len(new_items) > 0:
                # 💡 如果原本沒有這個欄位，初始化它
                if target_section not in current_json or not isinstance(current_json[target_section], list):
                    current_json[target_section] = []
                
                # 💡 無上限追加新種子/新轉折，保留所有舊有設定
                current_json[target_section].extend([x for x in new_items if isinstance(x, str)])
                print(f"[SUCCESS] 成功增量追加 {len(new_items)} 個新設定到 {target_section}！目前總數：{len(current_json[target_section])}")
                
        elif target_section == "multi_act_structure":
            act_data = parsed.get("multi_act_structure", parsed)
            if isinstance(act_data, list):
                current_json["multi_act_structure"] = act_data
            elif isinstance(act_data, dict):
                current_json["multi_act_structure"] = [
                    {"title": "第一幕 (Setup)", "content": act_data.get("act1_setup", act_data.get("act1", ""))},
                    {"title": "第二幕 (Confrontation)", "content": act_data.get("act2_confrontation", act_data.get("act2", ""))},
                    {"title": "第三幕 (Resolution)", "content": act_data.get("act3_resolution", act_data.get("act3", ""))}
                ]
                        
        elif target_section == "progressive_character_plan":
            plan_data = parsed.get("progressive_character_plan", parsed)
            if isinstance(plan_data, list):
                current_json["progressive_character_plan"] = plan_data
            elif isinstance(plan_data, dict):
                current_json["progressive_character_plan"] = [
                    {"title": "第一波開篇 (Wave 1)", "content": plan_data.get("wave_1_opening", "")},
                    {"title": "第二波發展 (Wave 2)", "content": plan_data.get("wave_2_development", "")},
                    {"title": "第三波高潮 (Wave 3)", "content": plan_data.get("wave_3_climax", "")}
                ]
        elif target_section == "volumes":
            volumes_data = parsed.get("volumes", parsed) if isinstance(parsed, dict) else parsed
            if isinstance(volumes_data, list) and len(volumes_data) > 0:
                current_json["volumes"] = volumes_data
                print(f"[SUCCESS] 成功增量更新篇卷大綱與時間軸配置！共 {len(volumes_data)} 卷。")
                
                # 同步到資料庫的 volumes 表以維持一致性
                from db import save_volumes
                save_volumes(nid, volumes_data)
        else:
            # 通用欄位直接覆寫
            val = parsed.get(target_section, text.strip()) if isinstance(parsed, dict) else text.strip()
            current_json[target_section] = val
            
        save_worldbuilding(nid, json.dumps(current_json, ensure_ascii=False, indent=2))
    
    return run_agent_stream(novel_id, "architect", messages, save_callback)

# ============================================================
# INCREMENTAL CHARACTER (增量角色生成)
# ============================================================

INCREMENTAL_CHARACTER_PROMPT = """你是角色設計大師，專精於對現有角色設定進行局部增強與修改。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

## 核心原則
1. **局部修改**：可以只修改特定角色的特定欄位，不重新生成全部。
2. **保持一致**：新增/修改的角色必須與現有世界觀設定和劇情保持邏輯一致。

## 輸出絕對限制（反格式污染）
1. 你是一個精準的後端 API 數據節點。嚴禁包含任何如「好的，這是我為您修改的角色設定...」等寒暄、過渡、解釋性旁白。
2. 你【只能且必須】回傳一個格式完全合法、可被 Python json.loads() 直接解析的標準 JSON 物件。
3. 必須嚴格包裹在 ```json ... ``` 區塊中。

## 現有世界觀（參考）
{existing_worldbuilding}

## 現有角色設定
{existing_characters}

## 用戶修改要求
{user_hint}
"""

def run_incremental_character_designer(novel_id, target_char_index, field_name, user_hint):
    """
    增量生成/修改角色（局部上下文）
    
    Args:
        novel_id: 小說 ID
        target_char_index: 要修改的角色索引，None 表示新增
        field_name: 要修改的欄位，None 表示全部
        user_hint: 用戶的提示
    """
    char = get_latest_characters(novel_id)
    existing_chars = char["json_data"] if char else '{"characters": []}'
    
    wb = get_latest_worldbuilding(novel_id)
    existing_wb = wb["content"] if wb else "尚無世界觀設定"
    
    prompt = INCREMENTAL_CHARACTER_PROMPT.format(
        existing_characters=existing_chars,
        existing_worldbuilding=existing_wb,
        user_hint=user_hint
    )
    
    additional_context = ""
    if target_char_index is not None:
        additional_context += f"\n\n目標修改角色索引：第 {target_char_index + 1} 個角色"
    if field_name:
        additional_context += f"\n\n只需要修改欄位：{field_name}"
    
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"請{user_hint}{additional_context}\n\n輸出完整的角色 JSON（包含所有欄位）。"}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        # 💡 嚴格防禦：若 LLM 污染嚴重無法解析 JSON，直接報錯
        if parsed is None or (isinstance(parsed, dict) and "error" in parsed):
            try:
                import sys
                encoding = sys.stdout.encoding or "utf-8"
                safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
                print(f"[ERROR] 增量角色設計失敗，模型未返回標準 JSON 數據。原始文字：\n{safe_text}")
            except Exception:
                pass
            return
            
        if isinstance(parsed, dict) and "characters" in parsed and parsed["characters"]:
            if target_char_index is not None and field_name:
                # 增量更新特定欄位
                new_value = parsed["characters"][0].get(field_name)
                if new_value is not None:
                    update_character_single_field(nid, target_char_index, field_name, new_value)
            elif target_char_index is not None:
                # 替換整個角色
                char_data = get_latest_characters(nid)
                if char_data and "parsed_data" in char_data:
                    pd = char_data["parsed_data"]
                    if "characters" in pd and target_char_index < len(pd["characters"]):
                        pd["characters"][target_char_index] = parsed["characters"][0]
                        save_characters(nid, pd)
            else:
                # 新增角色
                char_data = get_latest_characters(nid)
                if char_data and "parsed_data" in char_data:
                    pd = char_data["parsed_data"]
                    if "characters" not in pd:
                        pd["characters"] = []
                    pd["characters"].append(parsed["characters"][0])
                    save_characters(nid, pd)
                else:
                    save_characters(nid, parsed)
    
    return run_agent_stream(novel_id, "character", messages, save_callback)


# ============================================================
# INCREMENTAL CHARACTER APPEND (精準增量追加新角色到 Bible 末尾)
# ============================================================

INCREMENTAL_CHARACTER_APPEND_PROMPT = """你是角色設計大師，專精於對現有角色聖經進行精準增量追加。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

## 核心原則
1. **精準追加**：只往現有角色列表末尾追加新角色，不修改任何已存在的角色。
2. **保持一致**：新增角色必須與現有世界觀設定保持邏輯一致。
3. **格式標準**：輸出完整的角色 JSON 結構。

## 輸出絕對限制（反格式污染）
1. 你是一個精準的後端 API 數據節點。嚴禁包含任何如「好的，這是我為您新增的角色...」等寒暄、過渡、解釋性旁白。
2. 你【只能且必須】回傳一個格式完全合法、可被 Python json.loads() 直接解析的標準 JSON 物件。
3. 必須嚴格包裹在 ```json ... ``` 區塊中。

## 現有世界觀（參考）
{existing_worldbuilding}

## 現有角色聖經（請勿修改，只追加新角色到末尾）
{existing_characters}

## 必須追加的新角色名單
{new_characters}

## 用戶要求的角色定位與背景
{user_hint}
"""

def run_incremental_character_append(novel_id, new_character_names, user_hint=None):
    """
    精準增量追加新角色到角色聖經末尾
    
    Args:
        novel_id: 小說 ID
        new_character_names: 新角色名稱列表，例如 ["赵", "林浩", "張銘"]
        user_hint: 用戶對角色的要求（如：身份、背景、定位等）
    """
    char = get_latest_characters(novel_id)
    existing_chars = char["json_data"] if char else '{"characters": []}'
    
    wb = get_latest_worldbuilding(novel_id)
    existing_wb = wb["content"] if wb else "尚無世界觀設定"
    
    # 獲取當前角色數量，用於定位新角色的插入位置
    current_char_count = 0
    if char and "parsed_data" in char:
        current_char_count = len(char["parsed_data"].get("characters", []))
    
    prompt = INCREMENTAL_CHARACTER_APPEND_PROMPT.format(
        existing_characters=existing_chars,
        existing_worldbuilding=existing_wb,
        new_characters=json.dumps(new_character_names, ensure_ascii=False),
        user_hint=user_hint or "請根據世界觀和現有角色，為這些新角色設計合理的人設與背景。"
    )
    
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"""請為以下新角色設計完整的角色卡，並將它們追加到現有角色聖經的末尾。
        
新角色名稱列表：{json.dumps(new_character_names, ensure_ascii=False)}

要求：
1. 每個新角色都必須有完整的角色欄位（name, role, entry_phase, personality, speech_style, want, need, fatal_flaw, motivation, arc, relationships）
2. 新角色的 name 欄位必須精確使用傳入的角色名稱
3. 角色的 entry_phase 標註為"配角"或具體章節
4. 請為每個角色設計合理的背景故事、性格特質與人際關係
5. 只輸出包含新角色的 JSON 陣列，不要包含任何已存在的角色
6. 必須嚴格包裹在 ```json ... ``` 區塊中

輸出格式：
```json
{{"characters": [
  {{"name": "角色名", "role": "配角", "entry_phase": "...", ...}}
]}}
```"""}
    ]
    
    def save_callback(nid, text):
        import json as json_mod
        parsed = parse_json_safely(text)
        
        # 嚴格防禦：若 LLM 污染嚴重無法解析 JSON，直接報錯
        if parsed is None or (isinstance(parsed, dict) and "error" in parsed):
            try:
                import sys
                encoding = sys.stdout.encoding or "utf-8"
                safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
                print(f"[ERROR] 增量追加角色失敗，模型未返回標準 JSON 數據。原始文字：\n{safe_text}")
            except Exception:
                pass
            return
        
        # 提取新角色列表
        new_chars_list = []
        if isinstance(parsed, dict) and "characters" in parsed:
            new_chars_list = parsed["characters"]
        elif isinstance(parsed, list):
            new_chars_list = parsed
        
        if not new_chars_list:
            print("[WARNING] 未解析到新角色數據")
            return
        
        # 讀取當前角色聖經
        char_data = get_latest_characters(nid)
        if char_data and "parsed_data" in char_data:
            pd = char_data["parsed_data"]
            if "characters" not in pd:
                pd["characters"] = []
            
            # 追加新角色到末尾
            for new_char in new_chars_list:
                # 確保 name 欄位與請求的一致
                char_name = new_char.get("name", "")
                if char_name and char_name in new_character_names:
                    pd["characters"].append(new_char)
                    print(f"[SUCCESS] 成功追加新角色「{char_name}」到角色聖經末尾")
                else:
                    # 若 LLM 修改了角色名稱，仍予以追加但發出警告
                    pd["characters"].append(new_char)
                    print(f"[WARNING] 角色名稱不一致，但已追加：{char_name}")
            
            # 保存更新後的角色聖經
            save_characters(nid, pd)
            print(f"[SUCCESS] 角色聖經更新完畢，目前共 {len(pd['characters'])} 個角色")
        else:
            # 若無現有角色聖經，直接使用新角色創建
            new_pd = {"characters": new_chars_list}
            save_characters(nid, new_pd)
            print(f"[SUCCESS] 創建新角色聖經，包含 {len(new_chars_list)} 個角色")
    
    return run_agent_stream(novel_id, "character", messages, save_callback)


# ============================================================
# INCREMENTAL PLOT (增量劇情大綱)
# ============================================================

INCREMENTAL_PLOT_PROMPT = """你是劇情規劃大師，專精於對現有章節大綱進行局部增強與擴充。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

## 核心原則
1. **插入式生成**：可以在指定位置插入新的章節大綱，不破壞現有結構。
2. **保持連貫**：新章節必須與前後章節保持時間線和情節的邏輯連貫。
3. **橋樑功能**：新章節要起到銜接前後內容的作用。

## 輸出絕對限制（反格式污染）
1. 你是一個精準的後端 API 數據節點。嚴禁包含任何如「好的，這是我為您修改的劇情大綱...」等寒暄、過渡、解釋性旁白。
2. 你【只能且必須】回傳一個格式完全合法、可被 Python json.loads() 直接解析的標準 JSON 物件或 JSON 陣列。
3. 必須嚴格包裹在 ```json ... ``` 區塊中。
4. 如果是用於插入新章節，請輸出一個 JSON 陣列，陣列中包含一個或多個新章節物件。每個章節物件必須包含：title, time_setting, time_span, summary, events, purpose, foreshadowing_plant, foreshadowing_payoff, characters_active, scene, emotional_tone, cliffhanger 等欄位。

## 現有大綱（局部上下文）
{existing_plot}

## 現有角色（參考）
{existing_characters}

## 現有世界觀（參考）
{existing_worldbuilding}

## 插入位置
insert_after_index: {insert_after_index}（在第 {insert_after_index + 1} 個章節之後插入新章節）

## 用戶要求
{user_hint}
"""

def run_incremental_plot_planner(novel_id, insert_after_index, user_hint):
    """
    增量生成大綱章節（局部上下文，可在指定位置插入）
    
    Args:
        novel_id: 小說 ID
        insert_after_index: 插入位置（在此索引之後插入）
        user_hint: 用戶的提示
    """
    plot = get_latest_plot_chapters(novel_id)
    existing_plot = plot["outline_json"] if plot else '{"chapters": []}'
    
    char = get_latest_characters(novel_id)
    existing_chars = char["json_data"] if char else '{"characters": []}'
    
    wb = get_latest_worldbuilding(novel_id)
    existing_wb = wb["content"] if wb else "尚無世界觀設定"
    
    prompt = INCREMENTAL_PLOT_PROMPT.format(
        existing_plot=existing_plot,
        existing_characters=existing_chars,
        existing_worldbuilding=existing_wb,
        insert_after_index=insert_after_index,
        user_hint=user_hint
    )
    
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"請根據以上大綱，在第 {insert_after_index + 1} 章之後插入新章節。\n\n{user_hint}\n\n只輸出新的章節大綱 JSON陣列格式（陣列中包含一個或多個新章節）。"}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        # 💡 嚴格防禦：若 LLM 污染嚴重無法解析 JSON，直接報錯
        if parsed is None or (isinstance(parsed, dict) and "error" in parsed):
            try:
                import sys
                encoding = sys.stdout.encoding or "utf-8"
                safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
                print(f"[ERROR] 增量大綱生成失敗，模型未返回標準 JSON 數據。原始文字：\n{safe_text}")
            except Exception:
                pass
            return
            
        # 提取章節列表或單一章節
        chapters_to_insert = []
        if isinstance(parsed, list):
            chapters_to_insert = parsed
        elif isinstance(parsed, dict):
            if "chapters" in parsed and isinstance(parsed["chapters"], list):
                chapters_to_insert = parsed["chapters"]
            elif "chapter" in parsed and isinstance(parsed["chapter"], dict):
                chapters_to_insert = [parsed["chapter"]]
            else:
                # 把 dict 本身當成單個章節
                chapters_to_insert = [parsed]
                
        # 依序插入各章節，動態調整插入位置
        current_insert_after = insert_after_index
        for ch in chapters_to_insert:
            if isinstance(ch, dict):
                insert_plot_chapter(nid, current_insert_after, ch)
                current_insert_after += 1
    
    return run_agent_stream(novel_id, "plot", messages, save_callback)


def run_volume_alignment(novel_id, volume_index):
    """
    JIT 延遲對齊 (Lazy Realignment) - 針對特定篇卷
    結合最新世界觀規律補丁，局部校準該卷內部的章節大綱，完成後消除過期標記。
    """
    from db import get_novel, get_volumes, update_volume_dirty, get_latest_worldbuilding, get_latest_characters, get_latest_plot_chapters, save_plot_chapters
    import json
    
    novel = get_novel(novel_id)
    worldview_patches_str = novel.get("worldview_patches", "[]")
    
    wb = get_latest_worldbuilding(novel_id)
    worldbuilding_str = wb["content"] if wb else "尚無世界觀設定"
    
    char = get_latest_characters(novel_id)
    characters_str = char["json_data"] if char else "尚無角色設定"
    
    plot = get_latest_plot_chapters(novel_id)
    plot_chapters = plot["parsed_data"].get("chapters", []) if plot else []
    
    # 篩選該卷的章節大綱
    volumes = get_volumes(novel_id)
    vol_chapters = [c for c in plot_chapters if db.get_chapter_volume_index(volumes, int(c.get("chapter_index", 0))) == int(volume_index)]
    
    if not vol_chapters:
        def empty_gen():
            yield "data: " + json.dumps({"type": "content", "delta": "此篇卷尚無章節大綱，無需對齊。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return empty_gen()
        
    prompt = f"""你是一位小說大綱對齊大師。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

現在，你的任務是執行**大綱延遲對齊 (Lazy Realignment)**：
因為小說的最新寫作部分引入了新的世界觀規律或神秘設定（即「世界觀補丁」），你需要修復並調整**第 {volume_index} 卷**的章節大綱，使其與最新設定邏輯連貫。

## ⚠️ 最新世界觀設定與世界規律補丁
【核心世界觀】
{worldbuilding_str}

【最新追加世界規律補丁】
{worldview_patches_str}

## 👥 角色聖經
{characters_str}

## 📋 當前第 {volume_index} 卷的原始章節大綱（需要局部修復與調整）
{json.dumps(vol_chapters, ensure_ascii=False, indent=2)}

## 🎯 調整要求
1. 請深度融合最新追加的「世界規律補丁」，精細修正大綱中事件的發生方式、伏筆或角色對話，確保不會與新設定衝突或出現邏輯漏洞。
2. 保持這些章節的核心情節主體與人物動機不變，僅進行必要的細微修正、伏筆埋設與細節補充。
3. 嚴格輸出合法的 JSON 陣列，包含且僅包含這批章節。嚴格包裹在 ```json ... ``` 區塊中。
"""
    messages = [
        {"role": "system", "content": "你是一位頂尖的小說大綱精細調度師。你只輸出嚴格、合法、無多餘寒暄的標準 JSON 數據。"},
        {"role": "user", "content": prompt}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if parsed is None or (isinstance(parsed, dict) and "error" in parsed):
            return
            
        aligned_ch_list = parsed if isinstance(parsed, list) else parsed.get("chapters", [])
        if isinstance(aligned_ch_list, list) and len(aligned_ch_list) > 0:
            # 重新加載確保 JIT 更新安全
            latest_plot = get_latest_plot_chapters(nid)
            all_ch = latest_plot["parsed_data"].get("chapters", []) if latest_plot else []
            
            # 將對齊後的章節縫合回總大綱
            for new_ch in aligned_ch_list:
                ch_idx = new_ch.get("chapter_index")
                if ch_idx:
                    all_ch = [c for c in all_ch if int(c.get("chapter_index", 0)) != int(ch_idx)]
                    all_ch.append(new_ch)
                    
            all_ch.sort(key=lambda x: int(x.get("chapter_index", 0)))
            save_plot_chapters(nid, {"chapters": all_ch})
            
            # 消除該卷的過期狀態！
            update_volume_dirty(nid, int(volume_index), 0)
            
    return run_agent_stream(novel_id, "plot", messages, save_callback)


# ============================================================
# Copilot 增量操作指令解析
# ============================================================

def parse_incremental_command(command_text, current_context):
    """
    解析總監 Copilot 的增量操作指令
    
    Args:
        command_text: 來自 Copilot 的指令文字
        current_context: 當前狀態上下文中文字
    
    Returns:
        dict: 包含 operation_type, target, params 等
    """
    # 解析增量操作類型
    result = {
        "operation_type": "full",  # 預設為全部重新生成
        "target": None,
        "params": {}
    }
    
    cmd_lower = command_text.lower()
    
    # 檢查是否是增量操作
    if "新增" in command_text or "插入" in command_text or "增加" in command_text:
        result["operation_type"] = "incremental_add"
    elif "修改" in command_text or "更新" in command_text or "調整" in command_text:
        result["operation_type"] = "incremental_update"
    elif "局部" in command_text or "部分" in command_text:
        result["operation_type"] = "partial"
    
    # 解析目標
    if "角色" in command_text:
        result["target"] = "character"
        # 嘗試解析角色索引
        import re
        idx_match = re.search(r'第?\s*(\d+)\s*個?角色', command_text)
        if idx_match:
            result["params"]["char_index"] = int(idx_match.group(1)) - 1  # 轉為 0-indexed
    elif "大綱" in command_text or "章節" in command_text:
        result["target"] = "plot"
        # 嘗試解析章節索引
        import re
        idx_match = re.search(r'第?\s*(\d+)\s*章', command_text)
        if idx_match:
            result["params"]["insert_after_index"] = int(idx_match.group(1)) - 1
    elif "世界觀" in command_text or "伏筆" in command_text or "轉折" in command_text or "篇卷" in command_text or "時間軸" in command_text or "時間線" in command_text or "volumes" in cmd_lower:
        result["target"] = "worldbuilding"
    
    # 解析欄位
    if "personality" in cmd_lower or "性格" in command_text:
        result["params"]["field_name"] = "personality"
    elif "motivation" in cmd_lower or "動機" in command_text:
        result["params"]["field_name"] = "motivation"
    elif "arc" in cmd_lower or "弧線" in command_text or "成長" in command_text:
        result["params"]["field_name"] = "arc"
    elif "foreshadowing" in cmd_lower or "伏筆" in command_text:
        result["params"]["field_name"] = "foreshadowing_seeds"
        result["target"] = "worldbuilding"
    elif "turning" in cmd_lower or "轉折" in command_text:
        result["params"]["field_name"] = "key_turning_points"
        result["target"] = "worldbuilding"
    elif "篇卷" in command_text or "時間軸" in command_text or "時間線" in command_text or "volumes" in cmd_lower:
        result["params"]["field_name"] = "volumes"
        result["target"] = "worldbuilding"
    
    return result

# ============================================================
# Helper function
# ============================================================

def clean_json_text(text):
    """
    Cleans raw markdown formatting around a JSON block.
    Extracts the content between the first '{' or '[' and the last '}' or ']'.
    """
    import re
    text = text.strip()
    
    # 1. 優先尋找 Markdown 代碼區塊
    code_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_blocks:
        for block in reversed(code_blocks):
            block_stripped = block.strip()
            if block_stripped.startswith("{") or block_stripped.startswith("["):
                return block_stripped
                
    # 2. 正則匹配最長的 JSON 區塊
    all_braces = re.findall(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if all_braces:
        all_braces.sort(key=len, reverse=True)
        return all_braces[0].strip()
        
    return text

def parse_json_safely(text, default=None):
    """
    Attempts to parse text as JSON. Returns default if parsing fails.
    """
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
        return default or {"error": "Failed to parse JSON", "raw_content": text}


# 引用主 agents.py 的 run_agent_stream
def run_agent_stream(novel_id, agent_name, messages, save_callback=None):
    """
    代理到主 agents.py 的 run_agent_stream
    注意：這個函數會在載入時被替換為實際的實現
    """
    from agents import run_agent_stream as _run_agent_stream
    return _run_agent_stream(novel_id, agent_name, messages, save_callback)
def run_volume_jit_alignment(novel_id, volume_index):
    """
    非同步 JIT 篇卷大綱對齊機制
    """
    import json
    import db
    from llm import call_llm_stream
    from agents import compile_context, run_agent_stream, _normalize_chapter_outlines, _sse_content, _sse_error
    
    # 1. 取得全域上下文
    context = compile_context(novel_id)
    patches = db.get_worldview_patches(novel_id)
    patches_str = json.dumps(patches, ensure_ascii=False, indent=2) if patches else "尚無新世界規律補丁設定。"
    
    # 2. 取得當前卷
    volumes = db.get_volumes(novel_id)
    current_vol = None
    for v in volumes:
        if v["volume_index"] == volume_index:
            current_vol = v
            break
            
    if not current_vol:
        def error_gen():
            yield "data: " + json.dumps({"type": "error", "message": f"找不到第 {volume_index} 篇卷設定。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return error_gen()
        
    # 3. 取得前卷大綱（用以縫合）
    prev_chapters_context = "這是整部小說的開篇第一卷，無前卷大綱銜接參考。"
    if volume_index > 1:
        prev_vol = None
        for v in volumes:
            if v["volume_index"] == volume_index - 1:
                prev_vol = v
                break
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
    
    yield "data: " + json.dumps({
        "type": "content", 
        "delta": f"=== [篇卷大綱 JIT 對齊啟動] ===\n正在針對第 {volume_index} 卷《{current_vol['title']}》進行 {volume_ch_count} 章節微觀大綱 JIT 校準對齊...\n"
    }, ensure_ascii=False) + "\n\n"
    
    prompt = f"""你是一位精細微觀情節對齊大師。你負責將世界觀最新設定、角色 Bible 與特定篇卷大綱完美對齊。
    
{current_volume_details}

【全域世界觀設定】
{context['worldbuilding']}

【動態世界觀補丁/衍生規律】
{patches_str}

【角色 Bible】
{context['characters']}

【全書進度與篇卷大綱定位】
- 當前預估總章節數：共 {total_chapters} 章
- 當前滾動對齊篇卷：第 {volume_index} 卷 (全書預估 {total_volumes} 卷，大綱進度定位約 {int(progress_percentage * 100)}%)
- 敘事階段指示：目前處於【{"開篇 (Setup)" if progress_percentage <= 0.2 else "發展/衝突升級 (Confrontation)" if progress_percentage <= 0.8 else "高潮/收尾 (Resolution)"}】階段。請在此卷的 {volume_ch_count} 章情節中分配並落實相應的伏筆種子（Seeds）與關鍵轉折點，合理調配故事張力。

【當前篇卷設定】
第 {volume_index} 卷：《{current_vol['title']}》
核心概要：{current_vol['summary']}
登場陣營：{current_vol['factions']}

【前卷結尾大綱（銜接參考，請務必流暢承接時間與事件）】
{prev_chapters_context}

現在，請繼續為第 {volume_index} 卷精細規劃並對齊接下來的 {volume_ch_count} 個章節大綱（章節序號必須精確是第 {start_chapter} 章至第 {end_chapter} 章）：

## ⚠️ 核心對齊與格式規範
1. 必須融入所有的「動態世界觀補丁」，讓情節發展與新規則完全一致。
2. 每一章大綱必須包含：章節序號、章節標題、時空座標、情節概要、事件清單、伏筆埋設與回收、懸念鉤子。
3. 嚴禁重複模板化。只輸出一個標準的 JSON 陣列，嚴格包裹在 ```json ... ``` 區塊中。

JSON 陣列格式：
```json
[
  {{
    "chapter_index": {start_chapter},
    "title": "具體且有戲劇張力的標題",
    "time_setting": "時空座標",
    "time_span": "時間跨度",
    "events": [
      {{"scene": "具體場景", "action": "核心動作衝突", "consequence": "帶來的轉折與後果"}}
    ],
    "purpose": "本章情節目的",
    "foreshadowing_plant": [],
    "foreshadowing_payoff": [],
    "characters_active": ["主要活躍角色"],
    "scene": "主場景",
    "emotional_tone": "情緒基調",
    "cliffhanger": "章末懸念"
  }}
]
```
"""
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
        
    node_chapters = _normalize_chapter_outlines(parsed, start_chapter, expected_count=volume_ch_count)
        
    if node_chapters:
        for idx, ch in enumerate(node_chapters):
            ch["chapter_index"] = start_chapter + idx
            
        db.update_volume_outline(novel_id, volume_index, node_chapters)
        yield "data: " + json.dumps({
            "type": "content", 
            "delta": f"\n\n✓ 第 {volume_index} 卷對齊與規劃完成！已成功儲存 {len(node_chapters)} 章大綱。\n"
        }, ensure_ascii=False) + "\n\n"
    else:
        yield _sse_content(f"\n\n⚠️ 第 {volume_index} 卷 JIT 對齊失敗；停止保底佔位，改請總監救援診斷並重新操作。\n")

        rescue_prompt = f"""你是 AI Novel Factory 的首席創意總監與流程救援官。

第 {volume_index} 卷《{current_vol['title']}》的 JIT 篇卷對齊失敗，Plot Planner 沒有產出 {volume_ch_count} 個合法章節。
你不能生成保底、占位、模板章。請診斷失敗原因，並給出能讓 Plot Planner 重新成功的具體救援指令。

【世界觀】
{context['worldbuilding']}

【世界觀補丁】
{patches_str}

【角色 Bible】
{context['characters']}

【篇卷設定】
核心概要：{current_vol['summary']}
登場陣營：{current_vol['factions']}
{current_volume_details}

嚴格輸出 JSON：
{{
  "diagnosis": "失敗原因",
  "planner_directive": "重新規劃第 {start_chapter} 章至第 {end_chapter} 章的具體操作策略",
  "chapters": []
}}

若你能直接救援，`chapters` 可以直接填入 {volume_ch_count} 個合法章節；否則保持空陣列，系統會用 planner_directive 再請 Plot Planner 重試。
"""
        rescue_messages = [
            {"role": "system", "content": "你是嚴格的流程救援總監，只輸出合法 JSON。"},
            {"role": "user", "content": rescue_prompt}
        ]
        rescue_text = ""
        for sse_line in call_llm_stream("copilot", rescue_messages):
            yield sse_line
            if sse_line.startswith("data:"):
                try:
                    data_str = sse_line[5:].strip()
                    if data_str != "[DONE]":
                        data = json.loads(data_str)
                        if data.get("type") == "content":
                            rescue_text += data.get("delta", "")
                except:
                    pass

        parsed_rescue = parse_json_safely(rescue_text)
        if isinstance(parsed_rescue, dict) and "error" in parsed_rescue:
            parsed_rescue = parse_json_safely(clean_json_text(rescue_text))
        node_chapters = _normalize_chapter_outlines(parsed_rescue, start_chapter, expected_count=volume_ch_count)

        if not node_chapters:
            planner_directive = ""
            if isinstance(parsed_rescue, dict):
                planner_directive = parsed_rescue.get("planner_directive", "") or parsed_rescue.get("diagnosis", "")
            planner_directive = planner_directive or rescue_text

            retry_prompt = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你正在執行總監救援指令，重新規劃第 {volume_index} 卷第 {start_chapter} 章至第 {end_chapter} 章。

【總監救援指令】
{planner_directive}

【世界觀】
{context['worldbuilding']}

【世界觀補丁】
{patches_str}

【角色 Bible】
{context['characters']}

【篇卷設定】
第 {volume_index} 卷：《{current_vol['title']}》
核心概要：{current_vol['summary']}
登場陣營：{current_vol['factions']}
{current_volume_details}

請輸出精確 {volume_ch_count} 個非模板化章節大綱。只輸出 JSON 陣列或 {{"chapters": [...]}}。
"""
            retry_messages = [
                {"role": "system", "content": "你是被總監救援指令接管的微觀劇情規劃師，只輸出合法 JSON。"},
                {"role": "user", "content": retry_prompt}
            ]
            retry_text = ""
            for sse_line in call_llm_stream("plot", retry_messages):
                yield sse_line
                if sse_line.startswith("data:"):
                    try:
                        data_str = sse_line[5:].strip()
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
            db.update_volume_outline(novel_id, volume_index, node_chapters)
            yield _sse_content(f"\n\n✓ 總監救援成功：第 {volume_index} 卷已重新生成並保存 {len(node_chapters)} 章合法大綱。\n")
        else:
            yield _sse_error(f"第 {volume_index} 卷總監救援仍未產出合法大綱；已停止保存，避免寫入保底佔位。")
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return
        
    yield "data: " + json.dumps({"type": "done"}) + "\n\n"

