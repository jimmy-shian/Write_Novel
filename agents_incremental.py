"""
增量生成 Agent 函數 - 細粒度編輯功能
這些函數允許對 JSON 的子項目進行單獨修改，而不是全部重新生成
"""

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
    update_character_single_field
)
from llm import call_llm_stream

# ============================================================
# INCREMENTAL WORLDVIEW (增量世界觀生成)
# ============================================================

INCREMENTAL_ARCHITECT_PROMPT = """你是故事架構師，專精於對現有世界觀進行局部增強與擴充。

## 核心原則
1. **局部修改**：只生成/修改指定的特定部分，不重新生成全部內容
2. **保持一致**：新增內容必須與現有世界觀設定保持邏輯一致性
3. **精煉輸出**：只輸出用戶要求的內容，不輸出多餘解釋

## 任務類型
根據 target_section 不同，專注於生成對應的內容：
- "foreshadowing_seeds"：生成新的伏筆種子（3-5個），每個包含早期埋設與後期收束方式
- "three_act_structure"：生成/修改三幕式結構
- "progressive_character_plan"：生成/修改角色漸進規劃策略
- "key_turning_points"：生成/修改關鍵轉折點

## 現有世界觀（局部上下文）
{existing_worldbuilding}

## 用戶要求
target_section: {target_section}
user_hint: {user_hint}

## 輸出要求
只輸出符合 target_section 的內容，不要輸出其他部分。
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
        if target_section == "foreshadowing_seeds":
            # 增量添加伏筆種子
            parsed = parse_json_safely(text)
            if isinstance(parsed, list):
                for seed in parsed:
                    if isinstance(seed, str):
                        append_foreshadowing(nid, seed)
                    elif isinstance(seed, dict):
                        # 如果是物件格式，轉換為字串
                        append_foreshadowing(nid, str(seed))
            elif isinstance(parsed, str):
                append_foreshadowing(nid, parsed)
        elif target_section == "three_act_structure":
            # 更新整個世界觀中的三幕式結構部分
            parsed = parse_json_safely(text)
            if "three_act_structure" in parsed or "act1" in parsed or "act2" in parsed:
                # 直接替換三幕式結構
                new_content = f"【三幕式結構】\n"
                if "three_act_structure" in parsed:
                    ts = parsed["three_act_structure"]
                    new_content += f"  第一幕（Setup）：{ts.get('act1_setup', ts.get('act1', ''))}\n"
                    new_content += f"  第二幕（Confrontation）：{ts.get('act2_confrontation', ts.get('act2', ''))}\n"
                    new_content += f"  第三幕（Resolution）：{ts.get('act3_resolution', ts.get('act3', ''))}\n"
                else:
                    new_content += f"  第一幕（Setup）：{parsed.get('act1_setup', parsed.get('act1', ''))}\n"
                    new_content += f"  第二幕（Confrontation）：{parsed.get('act2_confrontation', parsed.get('act2', ''))}\n"
                    new_content += f"  第三幕（Resolution）：{parsed.get('act3_resolution', parsed.get('act3', ''))}\n"
                
                # 簡單替換現有內容中的三幕式結構部分
                if wb and wb["content"]:
                    content = wb["content"]
                    import re
                    # 替換三幕式結構部分
                    pattern = r'【三幕式結構】.*?(?=\n\n【|\Z)'
                    if re.search(pattern, content, re.DOTALL):
                        content = re.sub(pattern, new_content.strip(), content, flags=re.DOTALL)
                    else:
                        content = content + "\n\n" + new_content
                    save_worldbuilding(nid, content)
    
    return run_agent_stream(novel_id, "architect", messages, save_callback)

# ============================================================
# INCREMENTAL CHARACTER (增量角色生成)
# ============================================================

INCREMENTAL_CHARACTER_PROMPT = """你是角色設計大師，專精於對現有角色設定進行局部增強與修改。

## 核心原則
1. **局部修改**：可以只修改特定角色的特定欄位，不重新生成全部
2. **保持一致**：新增/修改的角色必須與現有世界觀和劇情保持一致
3. **深度刻畫**：即使是局部修改，也要確保心理深度

## 任務類型
- target_char_index 為 None：要新增一個新角色
- target_char_index 有值：要修改現有角色
- field_name 有值：只修改該角色的特定欄位（如 personality, motivation, arc）
- field_name 為 None：修改整個角色或新增角色

## 現有角色聖經（局部上下文）
{existing_characters}

## 現有世界觀（參考）
{existing_worldbuilding}

## 用戶要求
{user_hint}

## 輸出要求
只輸出修改後的角色 JSON 格式，不要輸出其他解釋。
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
        if "characters" in parsed and parsed["characters"]:
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
1. **插入式生成**：可以在指定位置插入新的章節大綱，不破壞現有結構
2. **保持連貫**：新章節必須與前後章節保持時間線和情節的邏輯連貫
3. **橋樑功能**：新章節要起到銜接前後內容的作用

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

## 輸出要求
只輸出新的章節大綱 JSON，不要輸出其他解釋。
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
        if isinstance(parsed, list):
            for new_chapter in parsed:
                if isinstance(new_chapter, dict) and "chapter_index" not in new_chapter:
                    # 計算正確的 chapter_index
                    plot_data = get_latest_plot_chapters(nid)
                    if plot_data and "parsed_data" in plot_data:
                        current_len = len(plot_data["parsed_data"].get("chapters", []))
                        new_chapter["chapter_index"] = current_len + 1
                    else:
                        new_chapter["chapter_index"] = 1
                # 插入到指定位置
                insert_plot_chapter(nid, insert_after_index, new_chapter)
        elif isinstance(parsed, dict) and "chapter_index" in parsed:
            # 單個章節
            insert_plot_chapter(nid, insert_after_index, parsed)
    
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
    elif "世界觀" in command_text or "伏筆" in command_text:
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