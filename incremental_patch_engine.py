# -*- coding: utf-8 -*-
import json
import re
import sys
import db

ALLOWED_CHARACTER_FIELDS = {"name", "identity", "personality", "appearance", "background", "arc", "relationships"}

def clean_json_text(text):
    """
    Cleans raw markdown formatting around a JSON block.
    Extracts the content between the first '{' or '[' and the last '}' or ']'.
    """
    if not text:
        return ""
    if not isinstance(text, str):
        return text
        
    text = text.strip()
    
    # 0.5. If the text looks like a braceless key-value block, wrap it with {}
    if text and not text.startswith("{") and not text.startswith("["):
        if re.match(r'^\s*"\w+"\s*:', text) or re.match(r'^\s*\'\w+\'\s*:', text):
            text = "{" + text + "}"
            
    # 1. Look for markdown code blocks
    code_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    candidate = text
    if code_blocks:
        for block in reversed(code_blocks):
            block_stripped = block.strip()
            # If the code block is braceless, wrap it with {}
            if block_stripped and not block_stripped.startswith("{") and not block_stripped.startswith("["):
                if re.match(r'^\s*"\w+"\s*:', block_stripped) or re.match(r'^\s*\'\w+\'\s*:', block_stripped):
                    block_stripped = "{" + block_stripped + "}"
            if block_stripped.startswith("{") or block_stripped.startswith("["):
                candidate = block_stripped
                break
    else:
        # 2. Extract braces block
        all_braces = re.findall(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if all_braces:
            all_braces.sort(key=len, reverse=True)
            candidate = all_braces[0].strip()
            
    # 如果已經是合法 JSON，直接回傳，防止 naive regex 進行錯誤替換（如字串內含冒號）
    try:
        json.loads(candidate)
        return candidate
    except Exception:
        pass
        
    # 若 JSON 解析失敗，才進行 naive 補引號嘗試
    repaired = re.sub(r':\s*([^"\s\{\[\d\-][^"\n,]*)"(?=\s*[,\}])', r': "\1"', candidate)
    repaired = re.sub(r':\s*"([^"\n,]+)(?=\s*[,\}])', r': "\1"', repaired)
    
    return repaired

def parse_incremental_response(text):
    """
    From LLM response, extract JSON and load it. Returns None if it fails.
    """
    if not text:
        return None
    if isinstance(text, (dict, list)):
        return text
        
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
        print(f"[WARN] parse_incremental_response JSON load failed: {e}")
        return None

def validate_incremental_payload(target_section, payload, action="PATCH", extra_params=None):
    """
    Validates the structure of the incoming payload.
    Returns (is_valid: bool, error_msg: str)
    """
    if payload is None:
        return False, "Payload is None"
        
    if target_section == "worldbuilding":
        if not isinstance(payload, dict):
            return False, f"Worldbuilding payload must be a dict, got {type(payload)}"
        allowed_wb_keys = {
            "theme", "main_conflict", "worldview", "macro_outline",
            "multi_act_structure", "progressive_character_plan",
            "foreshadowing_seeds", "key_turning_points", "volumes"
        }
        for k in payload.keys():
            if k not in allowed_wb_keys:
                return False, f"Unauthorized worldbuilding key: '{k}'"
        return True, ""
        
    elif target_section in ["foreshadowing_seeds", "key_turning_points"]:
        # Should be list or string
        if isinstance(payload, dict):
            items = payload.get(target_section, [])
        else:
            items = payload
        if not isinstance(items, list):
            items = [items]
        for it in items:
            if not isinstance(it, str):
                return False, f"Each item in {target_section} must be a string, got {type(it)}"
        return True, ""
        
    elif target_section in ["multi_act_structure", "progressive_character_plan"]:
        data = payload.get(target_section, payload) if isinstance(payload, dict) else payload
        if not isinstance(data, (list, dict)):
            return False, f"{target_section} must be list or dict, got {type(data)}"
        return True, ""
        
    elif target_section == "volumes":
        data = payload.get("volumes", payload) if isinstance(payload, dict) else payload
        if not isinstance(data, list):
            return False, f"Volumes must be a list, got {type(data)}"
        for v in data:
            if not isinstance(v, dict):
                return False, f"Each volume must be a dict, got {type(v)}"
            if "volume_index" not in v:
                return False, "Each volume must have 'volume_index'"
            try:
                int(v["volume_index"])
            except (ValueError, TypeError):
                return False, f"volume_index must be an integer, got '{v.get('volume_index')}'"
        return True, ""
        
    elif target_section == "characters":
        data = payload.get("characters", payload) if isinstance(payload, dict) else payload
        if action == "APPEND":
            if not isinstance(data, list):
                if isinstance(data, dict):
                    data = [data]
                else:
                    return False, f"Characters append payload must be list or dict, got {type(payload)}"
            for c in data:
                if not isinstance(c, dict):
                    return False, f"Each character must be a dict, got {type(c)}"
                if "name" not in c or not c["name"]:
                    return False, "Each appended character must have a non-empty 'name' field"
            return True, ""
        elif action == "PATCH":
            if extra_params and "field_name" in extra_params:
                field_name = extra_params["field_name"]
                if field_name not in ALLOWED_CHARACTER_FIELDS:
                    return False, f"Field '{field_name}' is not in character fields whitelist"
            if isinstance(data, list):
                if len(data) > 0:
                    c = data[0]
                    if not isinstance(c, dict):
                        return False, "Character must be a dict"
            elif isinstance(data, dict):
                pass
            else:
                return False, "Character payload must be dict or list"
            return True, ""
            
    elif target_section in ["plot", "chapters"]:
        data = payload.get("chapters", payload) if isinstance(payload, dict) else payload
        if action == "INSERT":
            if not isinstance(data, list):
                if isinstance(data, dict):
                    data = [data]
                else:
                    return False, "INSERT plot payload must be list or dict"
            for ch in data:
                if not isinstance(ch, dict):
                    return False, "Each chapter must be a dict"
                if "title" not in ch or not ch["title"]:
                    return False, "Each inserted chapter must have a non-empty 'title'"
            return True, ""
        elif action == "PATCH":
            if not isinstance(data, list):
                if isinstance(data, dict):
                    data = [data]
                else:
                    return False, "PATCH plot payload must be list or dict"
            for ch in data:
                if not isinstance(ch, dict):
                    return False, "Each chapter must be a dict"
                if "chapter_index" not in ch:
                    return False, "Each patched chapter must have a 'chapter_index'"
            return True, ""
            
    return True, ""

def merge_incremental_payload(novel_id, target_section, action, payload, extra_params=None):
    """
    Merges in-memory the payload into the existing dataset from DB.
    Returns the merged object, or None if failed.
    """
    if target_section in ["theme", "main_conflict", "worldview", "macro_outline", "foreshadowing_seeds", "key_turning_points", "multi_act_structure", "progressive_character_plan", "volumes", "worldbuilding"]:
        wb = db.get_latest_worldbuilding(novel_id)
        existing_content = wb["content"] if wb else ""
        current_json = db.parse_worldview_to_json(existing_content)
        
        # If target_section is "worldbuilding", update all provided keys
        if target_section == "worldbuilding":
            current_json = smart_merge_worldbuilding(current_json, payload)
            return current_json
            
        elif target_section in ["foreshadowing_seeds", "key_turning_points"]:
            new_items = payload if isinstance(payload, list) else payload.get(target_section, [])
            if not isinstance(new_items, list):
                new_items = [new_items]
            if target_section not in current_json or not isinstance(current_json[target_section], list):
                current_json[target_section] = []
            for x in new_items:
                if isinstance(x, str) and x not in current_json[target_section]:
                    current_json[target_section].append(x)
            return current_json
            
        elif target_section == "volumes":
            existing_vols = {int(vol["volume_index"]): vol for vol in current_json.get("volumes", []) if "volume_index" in vol}
            new_vols = payload.get("volumes", payload) if isinstance(payload, dict) else payload
            if isinstance(new_vols, list):
                for vol in new_vols:
                    if "volume_index" in vol:
                        v_idx = int(vol["volume_index"])
                        if v_idx in existing_vols:
                            existing_vols[v_idx].update(vol)
                        else:
                            existing_vols[v_idx] = vol
                current_json["volumes"] = [existing_vols[idx] for idx in sorted(existing_vols.keys())]
            return current_json
            
        elif target_section in ["multi_act_structure", "progressive_character_plan"]:
            v = payload.get(target_section, payload) if isinstance(payload, dict) else payload
            if isinstance(v, list):
                current_json[target_section] = v
            elif isinstance(v, dict):
                if target_section == "multi_act_structure":
                    current_json[target_section] = [
                        {"title": "第一幕 (Setup)", "content": v.get("act1_setup", v.get("act1", ""))},
                        {"title": "第二幕 (Confrontation)", "content": v.get("act2_confrontation", v.get("act2", ""))},
                        {"title": "第三幕 (Resolution)", "content": v.get("act3_resolution", v.get("act3", ""))}
                    ]
                else:
                    current_json[target_section] = [
                        {"title": "第一波開篇 (Wave 1)", "content": v.get("wave_1_opening", "")},
                        {"title": "第二波發展 (Wave 2)", "content": v.get("wave_2_development", "")},
                        {"title": "第三波高潮 (Wave 3)", "content": v.get("wave_3_climax", "")}
                    ]
            return current_json
            
        else:
            # General worldbuilding field
            val = payload.get(target_section, payload) if isinstance(payload, dict) else payload
            current_json[target_section] = val
            return current_json
            
    elif target_section == "characters":
        char_data = db.get_latest_characters(novel_id)
        current_chars = char_data["parsed_data"] if (char_data and "parsed_data" in char_data) else {"characters": []}
        if "characters" not in current_chars:
            current_chars["characters"] = []
            
        if action == "APPEND":
            new_c = payload.get("characters", payload) if isinstance(payload, dict) else payload
            if isinstance(new_c, dict):
                new_c = [new_c]
            if isinstance(new_c, list):
                current_chars["characters"].extend(new_c)
            return current_chars
            
        elif action == "PATCH":
            if extra_params and "char_index" in extra_params:
                c_idx = int(extra_params["char_index"])
                if c_idx < len(current_chars["characters"]):
                    if "field_name" in extra_params:
                        fname = extra_params["field_name"]
                        new_val = payload.get(fname, payload) if isinstance(payload, dict) else payload
                        current_chars["characters"][c_idx][fname] = new_val
                    else:
                        new_char = payload.get("characters", [payload])[0] if isinstance(payload, dict) else (payload[0] if isinstance(payload, list) else payload)
                        current_chars["characters"][c_idx] = new_char
                return current_chars
            else:
                # Whole characters replace (e.g. revision)
                new_list = payload.get("characters", payload) if isinstance(payload, dict) else payload
                if isinstance(new_list, list):
                    current_chars["characters"] = new_list
                return current_chars
                
    elif target_section in ["plot", "chapters"]:
        plot_data = db.get_stitched_plot(novel_id) or {"chapters": []}
        chapters = plot_data.get("chapters", [])
        
        if action == "INSERT":
            insert_after = int(extra_params.get("insert_after_index", 0)) if extra_params else 0
            insert_pos = -1
            if insert_after <= 0:
                insert_pos = 0
            else:
                for idx, ch in enumerate(chapters):
                    try:
                        if int(ch.get("chapter_index", 0)) == insert_after:
                            insert_pos = idx + 1
                            break
                    except:
                        pass
                        
            new_chaps = payload.get("chapters", payload) if isinstance(payload, dict) else payload
            if not isinstance(new_chaps, list):
                new_chaps = [new_chaps]
                
            for ch in new_chaps:
                ch_copy = ch.copy()
                if insert_pos == -1:
                    ch_copy["chapter_index"] = len(chapters) + 1
                    chapters.append(ch_copy)
                else:
                    ch_copy["chapter_index"] = insert_pos + 1
                    chapters.insert(insert_pos, ch_copy)
                    insert_pos += 1
                    
            # Re-index
            for idx, ch in enumerate(chapters):
                ch["chapter_index"] = idx + 1
                
            plot_data["chapters"] = chapters
            return plot_data
            
        elif action == "PATCH":
            new_chaps = payload.get("chapters", payload) if isinstance(payload, dict) else payload
            if isinstance(new_chaps, list):
                for ch in new_chaps:
                    if "chapter_index" in ch:
                        c_idx = int(ch["chapter_index"])
                        for idx, exist_ch in enumerate(chapters):
                            try:
                                if int(exist_ch.get("chapter_index", 0)) == c_idx:
                                    chapters[idx].update(ch)
                                    break
                            except:
                                pass
            plot_data["chapters"] = chapters
            return plot_data
            
    return None

def post_merge_validation(merged_data, target_section, original_data=None):
    """
    Validates the merged dataset for semantic consistency.
    Returns (is_valid: bool, errors: list)
    """
    errors = []
    
    if target_section in ["theme", "main_conflict", "worldview", "macro_outline", "foreshadowing_seeds", "key_turning_points", "multi_act_structure", "progressive_character_plan", "volumes", "worldbuilding"]:
        # Verify worldbuilding keys
        for key in ["theme", "main_conflict", "worldview", "macro_outline", "multi_act_structure", "progressive_character_plan", "foreshadowing_seeds", "key_turning_points"]:
            if key not in merged_data:
                errors.append(f"Key '{key}' vanished from worldbuilding")
                
        # Verify structure
        if "multi_act_structure" in merged_data:
            if not isinstance(merged_data["multi_act_structure"], list):
                errors.append("multi_act_structure must be a list")
            else:
                for idx, act in enumerate(merged_data["multi_act_structure"]):
                    if not isinstance(act, dict) or "title" not in act:
                        errors.append(f"Act {idx} in multi_act_structure is invalid")
                        
        if "progressive_character_plan" in merged_data:
            if not isinstance(merged_data["progressive_character_plan"], list):
                errors.append("progressive_character_plan must be a list")
            else:
                for idx, plan in enumerate(merged_data["progressive_character_plan"]):
                    if not isinstance(plan, dict) or "title" not in plan:
                        errors.append(f"Plan {idx} in progressive_character_plan is invalid")
                        
        if "foreshadowing_seeds" in merged_data:
            if not isinstance(merged_data["foreshadowing_seeds"], list):
                errors.append("foreshadowing_seeds must be a list")
            else:
                for idx, seed in enumerate(merged_data["foreshadowing_seeds"]):
                    if not isinstance(seed, str):
                        errors.append(f"foreshadowing_seed at {idx} is not a string")
                        
        if "key_turning_points" in merged_data:
            if not isinstance(merged_data["key_turning_points"], list):
                errors.append("key_turning_points must be a list")
            else:
                for idx, pt in enumerate(merged_data["key_turning_points"]):
                    if not isinstance(pt, str):
                        errors.append(f"key_turning_point at {idx} is not a string")
                        
        if "volumes" in merged_data:
            vols = merged_data["volumes"]
            if not isinstance(vols, list):
                errors.append("volumes must be a list")
            else:
                indices = []
                for idx, vol in enumerate(vols):
                    if not isinstance(vol, dict) or "volume_index" not in vol:
                        errors.append(f"Volume at {idx} is invalid")
                    else:
                        try:
                            indices.append(int(vol["volume_index"]))
                        except:
                            errors.append(f"Volume at {idx} has non-integer index")
                if indices:
                    indices.sort()
                    # Check continuous starting from 1
                    if indices[0] != 1:
                        errors.append(f"volumes must start from index 1, got {indices[0]}")
                    for i in range(len(indices) - 1):
                        if indices[i+1] - indices[i] != 1:
                            errors.append(f"volumes index is disconnected: {indices[i]} -> {indices[i+1]}")
                            
    elif target_section == "characters":
        if not isinstance(merged_data, dict) or "characters" not in merged_data:
            errors.append("Characters merged data must be dict with 'characters' key")
        else:
            chars = merged_data["characters"]
            if not isinstance(chars, list):
                errors.append("characters must be a list")
            else:
                for idx, c in enumerate(chars):
                    if not isinstance(c, dict):
                        errors.append(f"Character at {idx} is not a dict")
                    elif "name" not in c or not c["name"]:
                        errors.append(f"Character at {idx} is missing name")
                
                # Check that no unique, non-placeholder characters are dropped by comparing core names
                if original_data:
                    orig_chars = original_data.get("characters", [])
                    
                    placeholder_names = {
                        "新登場的次要角色", "待補充", "暫無", "placeholder", "新角色", "路人", 
                        "客棧老闆", "符合人設說話風格", "todo", "新登場次要角色"
                    }
                    
                    def get_core_name(name_str):
                        if not name_str:
                            return ""
                        import re
                        name_str = re.sub(r'[\(（].*?[\)）]', '', name_str)
                        for separator in ['-', '–', '—', '_', ':', '：', ' ', '\t']:
                            if separator in name_str:
                                parts = name_str.split(separator)
                                if parts[0].strip():
                                    name_str = parts[0]
                        return name_str.strip().lower()
                    
                    # Compute sets of core names
                    orig_cores = set()
                    for oc in orig_chars:
                        if isinstance(oc, dict):
                            oc_name = oc.get("name", "").strip()
                            if oc_name and not any(p in oc_name.lower() or oc_name.lower() in p for p in placeholder_names):
                                core = get_core_name(oc_name)
                                if core:
                                    orig_cores.add(core)
                                    
                    new_cores = set()
                    for nc in chars:
                        if isinstance(nc, dict):
                            nc_name = nc.get("name", "").strip()
                            if nc_name:
                                core = get_core_name(nc_name)
                                if core:
                                    new_cores.add(core)
                                    
                    # Check for missing core names
                    missing_cores = orig_cores - new_cores
                    if missing_cores:
                        errors.append(f"Merged characters are missing core characters from the original setup: {list(missing_cores)}")
                        
    elif target_section in ["plot", "chapters"]:
        if not isinstance(merged_data, dict) or "chapters" not in merged_data:
            errors.append("Plot merged data must be dict with 'chapters' key")
        else:
            chaps = merged_data["chapters"]
            if not isinstance(chaps, list):
                errors.append("chapters must be a list")
            else:
                indices = []
                for idx, ch in enumerate(chaps):
                    if not isinstance(ch, dict):
                        errors.append(f"Chapter at {idx} is not a dict")
                    elif "chapter_index" not in ch:
                        errors.append(f"Chapter at {idx} is missing chapter_index")
                    else:
                        try:
                            indices.append(int(ch["chapter_index"]))
                        except:
                            errors.append(f"Chapter at {idx} has non-integer chapter_index")
                if indices:
                    indices_sorted = sorted(indices)
                    if indices_sorted[0] != 1:
                        errors.append(f"chapter_index must start from 1, got {indices_sorted[0]}")
                    for i in range(len(indices_sorted) - 1):
                        if indices_sorted[i+1] - indices_sorted[i] != 1:
                            errors.append(f"chapter_index is disconnected: {indices_sorted[i]} -> {indices_sorted[i+1]}")
                            
    return len(errors) == 0, errors


def filter_and_sanitize_content(target_section, data):
    """
    【高品質防禦過濾器】
    遞迴掃描資料結構中的所有字串欄位，檢測並阻斷含有低品質佔位符或重複文字的內容。
    回傳 (is_ok: bool, error_msg: str)
    """
    if data is None:
        return True, ""
        
    banned_placeholders = [
        "todo", "暫無", "待補充", "請在此填入", "請填入", 
        "lorem ipsum", "暫定標題", "待定", "placeholder", "佔位", "占位"
    ]
    
    banned_boilerplates = [
        "命運波折之章", "推進核心衝突", "推動大綱情節發展", 
        "主角面臨新考驗", "留下懸念引發期待"
    ]
    
    # 遞迴尋找與檢查字串
    def scan_and_check(node, path=""):
        if isinstance(node, str):
            val_lower = node.lower()
            # 1. 檢查佔位符
            for bp in banned_placeholders:
                if bp in val_lower:
                    return False, f"檢測到低品質佔位符 '{bp}' 位於欄位 {path}: \"{node}\""
            # 2. 檢查預設模板廢話
            for bb in banned_boilerplates:
                if bb in val_lower:
                    return False, f"檢測到預設大綱模板套用廢話 '{bb}' 位於欄位 {path}: \"{node}\""
            # 3. 檢查字數是否極端過短 (若是大綱或正文的實質敘述欄位)
            if any(k in path.lower() for k in ["summary", "event", "purpose", "cliffhanger", "scene"]):
                # 如果字數過短，比如小於 5 個字且含有保底嫌疑
                if len(node.strip()) < 5:
                    return False, f"欄位 {path} 的描述字數過短 (\"{node}\")，請提供具體實質內容。"
                    
        elif isinstance(node, dict):
            for k, v in node.items():
                ok, err = scan_and_check(v, f"{path}.{k}" if path else k)
                if not ok:
                    return False, err
                    
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                ok, err = scan_and_check(item, f"{path}[{idx}]")
                if not ok:
                    return False, err
                    
        return True, ""
        
    # 執行過濾掃描
    ok, err_msg = scan_and_check(data)
    if not ok:
        return False, err_msg
        
    # 4. 針對大綱 (plot/chapters) 進行特別的重複性篩選
    if target_section in ["plot", "chapters"] and isinstance(data, dict):
        chaps = data.get("chapters", [])
        if isinstance(chaps, list) and len(chaps) >= 3:
            titles = [c.get("title", "") for c in chaps if isinstance(c, dict) and c.get("title")]
            for i in range(len(titles) - 2):
                if titles[i] == titles[i+1] == titles[i+2]:
                    return False, f"檢測到情節語意退化：連續三章大綱標題重覆 (\"{titles[i]}\")，已被自動過濾層攔截。"
                    
    return True, ""

def validate_and_merge_incremental_patch(novel_id, target_section, action, payload, extra_params=None):
    """
    Complete pipeline: Parse -> Validate Payload -> Merge -> Post-Validate -> Save to DB.
    Returns (success: bool, version: int | None, error_msg: str | None)
    """
    # 1. Parse payload if it is string
    parsed_payload = parse_incremental_response(payload) if isinstance(payload, str) else payload
    if parsed_payload is None:
        return False, None, "Failed to parse JSON response payload"
        
    # 🚨 高品質前置過濾防禦
    is_ok_content, filter_err = filter_and_sanitize_content(target_section, parsed_payload)
    if not is_ok_content:
        return False, None, f"[品質攔截] {filter_err}"
        
    # 2. Validate payload format
    is_valid_payload, err_msg = validate_incremental_payload(target_section, parsed_payload, action, extra_params)
    if not is_valid_payload:
        return False, None, f"Payload validation failed: {err_msg}"
        
    # Get original data for length preservation check
    original_data = None
    if target_section == "characters":
        char_data = db.get_latest_characters(novel_id)
        original_data = char_data["parsed_data"] if (char_data and "parsed_data" in char_data) else {"characters": []}
    elif target_section in ["theme", "main_conflict", "worldview", "macro_outline", "foreshadowing_seeds", "key_turning_points", "multi_act_structure", "progressive_character_plan", "volumes", "worldbuilding"]:
        wb = db.get_latest_worldbuilding(novel_id)
        original_data = db.parse_worldview_to_json(wb["content"] if wb else "")
        
    # 3. Merge payload into existing data
    merged_data = merge_incremental_payload(novel_id, target_section, action, parsed_payload, extra_params)
    if merged_data is None:
        return False, None, "Merge operation failed"
        
    # 4. Post-merge validation
    is_valid_merge, errors = post_merge_validation(merged_data, target_section, original_data)
    if not is_valid_merge:
        return False, None, f"Post-merge validation failed: {', '.join(errors)}"
        
    # 🚨 高品質合併後最終過濾防禦
    is_ok_merged, filter_merged_err = filter_and_sanitize_content(target_section, merged_data)
    if not is_ok_merged:
        return False, None, f"[品質攔截-合併後] {filter_merged_err}"
        
    # 5. Save to database
    try:
        if target_section in ["theme", "main_conflict", "worldview", "macro_outline", "foreshadowing_seeds", "key_turning_points", "multi_act_structure", "progressive_character_plan", "volumes", "worldbuilding"]:
            version = db.save_worldbuilding(novel_id, json.dumps(merged_data, ensure_ascii=False, indent=2))
            
            # Special sync: if volumes were merged, sync to volumes table
            if target_section == "volumes" or (target_section == "worldbuilding" and "volumes" in parsed_payload):
                new_vols = merged_data.get("volumes", [])
                if new_vols:
                    db.save_volumes(novel_id, new_vols)
            return True, version, None
            
        elif target_section == "characters":
            version = db.save_characters(novel_id, merged_data)
            return True, version, None
            
        elif target_section in ["plot", "chapters"]:
            # Note: We use skip_volume_sync=True to prevent automatic volume sync from overriding micro outlines
            version = db.save_plot_chapters(novel_id, merged_data, skip_volume_sync=True)
            return True, version, None
            
    except Exception as e:
        return False, None, f"Database write failed: {str(e)}"
        
    return False, None, f"Unknown target section: {target_section}"

def smart_merge_worldbuilding(current_json, new_json_data):
    """
    Intelligently merges new worldbuilding patch data into existing worldbuilding data.
    Never overwrites a populated field with an empty string, empty list, or placeholder.
    """
    merged = current_json.copy()
    for k, v in new_json_data.items():
        if k in ["theme", "main_conflict", "worldview", "macro_outline"]:
            if isinstance(v, str):
                v_strip = v.strip()
                is_new_valid = len(v_strip) > 0 and v_strip not in ["尚無內容", "✏️", "無", "none", "null"]
                curr_val = current_json.get(k, "")
                is_curr_empty = not curr_val or curr_val.strip() in ["尚無內容", "✏️", "無", "none", "null", ""]
                if is_new_valid or is_curr_empty:
                    merged[k] = v
        
        elif k in ["multi_act_structure", "progressive_character_plan"]:
            # If new value is dict, convert it to list first
            new_v = v
            if isinstance(v, dict):
                if k == "multi_act_structure":
                    new_v = [
                        {"title": "第一幕 (Setup)", "content": v.get("act1_setup", v.get("act1", ""))},
                        {"title": "第二幕 (Confrontation)", "content": v.get("act2_confrontation", v.get("act2", ""))},
                        {"title": "第三幕 (Resolution)", "content": v.get("act3_resolution", v.get("act3", ""))}
                    ]
                else:
                    new_v = [
                        {"title": "第一波開篇 (Wave 1)", "content": v.get("wave_1_opening", "")},
                        {"title": "第二波發展 (Wave 2)", "content": v.get("wave_2_development", "")},
                        {"title": "第三波高潮 (Wave 3)", "content": v.get("wave_3_climax", "")}
                    ]
            
            if isinstance(new_v, list) and len(new_v) > 0:
                # Check if the new list has actual non-empty content
                new_has_content = any(
                    isinstance(item, dict) and item.get("content") and item.get("content").strip() not in ["尚無內容", "✏️", "無", ""]
                    for item in new_v
                )
                curr_list = current_json.get(k, [])
                curr_has_content = False
                if isinstance(curr_list, list):
                    curr_has_content = any(
                        isinstance(item, dict) and item.get("content") and item.get("content").strip() not in ["尚無內容", "✏️", "無", ""]
                        for item in curr_list
                    )
                
                if new_has_content or not curr_has_content:
                    if isinstance(curr_list, list) and len(curr_list) == len(new_v):
                        merged_list = []
                        for i in range(len(new_v)):
                            c_item = curr_list[i] if isinstance(curr_list[i], dict) else {}
                            n_item = new_v[i] if isinstance(new_v[i], dict) else {}
                            m_item = c_item.copy()
                            n_content = n_item.get("content", "").strip()
                            if n_content and n_content not in ["尚無內容", "✏️", "無"]:
                                m_item["content"] = n_item.get("content")
                            if n_item.get("title"):
                                m_item["title"] = n_item.get("title")
                            merged_list.append(m_item)
                        merged[k] = merged_list
                    else:
                        merged[k] = new_v
            
        elif k in ["foreshadowing_seeds", "key_turning_points"]:
            if isinstance(v, list) and len(v) > 0:
                curr_list = current_json.get(k, [])
                if isinstance(curr_list, list):
                    merged_list = list(curr_list)
                    for x in v:
                        if isinstance(x, str) and x.strip() and x not in merged_list:
                            merged_list.append(x)
                    merged[k] = merged_list
                else:
                    merged[k] = v
                    
        elif k == "volumes":
            if isinstance(v, list) and len(v) > 0:
                existing_vols = {int(vol["volume_index"]): vol for vol in current_json.get("volumes", []) if isinstance(vol, dict) and "volume_index" in vol}
                for vol in v:
                    if isinstance(vol, dict) and "volume_index" in vol:
                        v_idx = int(vol["volume_index"])
                        if v_idx in existing_vols:
                            for vk, vv in vol.items():
                                if vv is not None and vv != "" and vv != []:
                                    existing_vols[v_idx][vk] = vv
                        else:
                            existing_vols[v_idx] = vol
                merged["volumes"] = [existing_vols[idx] for idx in sorted(existing_vols.keys())]
                
        else:
            if v is not None and v != "" and v != [] and v != {}:
                merged[k] = v
    return merged

def safe_worldbuilding_save(novel_id, new_json_data, source="unknown"):
    """
    Specialized safe saver for worldbuilding database modifications.
    Reads current -> merges -> post-validates -> writes.
    Returns (success: bool, version: int | None, error_msg: str | None)
    """
    if isinstance(new_json_data, str):
        parsed = parse_incremental_response(new_json_data)
        if parsed is None:
            print(f"[ERROR] safe_worldbuilding_save: failed to parse JSON from source={source}")
            return False, None, "Invalid JSON string"
        new_json_data = parsed
        
    if not isinstance(new_json_data, dict):
        print(f"[ERROR] safe_worldbuilding_save: data must be dict, got {type(new_json_data)} from source={source}")
        return False, None, f"Expected dict, got {type(new_json_data)}"
        
    # 🚨 高品質前置過濾防禦
    is_ok_content, filter_err = filter_and_sanitize_content("worldbuilding", new_json_data)
    if not is_ok_content:
        print(f"[ERROR] safe_worldbuilding_save: content quality check failed. Error: {filter_err}")
        return False, None, f"[品質攔截] {filter_err}"
        
    # Read current
    wb = db.get_latest_worldbuilding(novel_id)
    current_json = db.parse_worldview_to_json(wb["content"] if wb else "")
    
    # Merge: use smart merge instead of simple update
    merged = smart_merge_worldbuilding(current_json, new_json_data)
    
    # Post-validate
    is_valid, errors = post_merge_validation(merged, "worldbuilding")
    if not is_valid:
        print(f"[ERROR] safe_worldbuilding_save: validation failed from source={source}. Errors: {errors}")
        return False, None, f"Validation errors: {errors}"
        
    # 🚨 高品質合併後最終過濾防禦
    is_ok_merged, filter_merged_err = filter_and_sanitize_content("worldbuilding", merged)
    if not is_ok_merged:
        print(f"[ERROR] safe_worldbuilding_save: merged content quality check failed. Error: {filter_merged_err}")
        return False, None, f"[品質攔截-合併後] {filter_merged_err}"
        
    # Save
    try:
        version = db.save_worldbuilding(novel_id, json.dumps(merged, ensure_ascii=False, indent=2))
        print(f"[SUCCESS] safe_worldbuilding_save: successfully saved worldbuilding (version={version}) from source={source}")
        return True, version, None
    except Exception as e:
        print(f"[ERROR] safe_worldbuilding_save: failed to save to database from source={source}. Error: {e}")
        return False, None, str(e)

