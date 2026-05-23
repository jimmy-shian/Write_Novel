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

## 核心原則
1. **局部修改**：只生成/修改指定的特定部分，不重新生成全部內容。
2. **保持一致**：新增內容必須與現有世界觀設定保持邏輯一致性。
3. **精煉輸出**：只輸出用戶要求的內容，不輸出多餘解釋。

## 任務類型
根據 target_section 不同，專注於生成對應的內容：
- "foreshadowing_seeds"：生成新的伏筆種子（3-5個），每個包含早期埋設與後期收束方式。
- "three_act_structure"：生成/修改三幕式結構。
- "progressive_character_plan"：生成/修改角色漸進規劃策略。
- "key_turning_points"：生成/修改關鍵轉折點。

## 輸出絕對限制（反格式污染）
1. 你是一個精準的後端 API 數據節點。嚴禁包含任何如「好的，這是我為您修改的設定...」等寒暄、過渡、解釋性旁白。
2. 你【只能且必須】回傳一個格式完全合法、可被 Python json.loads() 直接解析的標準 JSON 物件。
3. 必須嚴格包裹在 ```json ... ``` 區塊中。

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
        target_section: 要生成的部分，如 "foreshadowing_seeds", "three_act_structure"
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
                
        elif target_section == "three_act_structure":
            act_data = parsed.get("three_act_structure", parsed)
            if isinstance(act_data, list):
                current_json["three_act_structure"] = act_data
            elif isinstance(act_data, dict):
                current_json["three_act_structure"] = [
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
# INCREMENTAL PLOT (增量劇情大綱)
# ============================================================

INCREMENTAL_PLOT_PROMPT = """你是劇情規劃大師，專精於對現有章節大綱進行局部增強與擴充。

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
    elif "世界觀" in command_text or "伏筆" in command_text or "轉折" in command_text:
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
    
    return result

# ============================================================
# Helper function
# ============================================================

def parse_json_safely(text, default=None):
    """安全解析 JSON"""
    import re
    text = text.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except:
        return default or {"error": "Failed to parse JSON", "raw_content": text}

# 引用主 agents.py 的 run_agent_stream
def run_agent_stream(novel_id, agent_name, messages, save_callback=None):
    """
    代理到主 agents.py 的 run_agent_stream
    注意：這個函數會在載入時被替換為實際的實現
    """
    from agents import run_agent_stream as _run_agent_stream
    return _run_agent_stream(novel_id, agent_name, messages, save_callback)