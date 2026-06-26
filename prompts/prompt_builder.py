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
    FORESHADOWING_ORCHESTRATOR_PROMPT,
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
MAX_WORLDVIEW_SUMMARY_LENGTH = 36000
MAX_MACRO_OUTLINE_LENGTH = 12000
MAX_DIRECTOR_WORLDVIEW_LENGTH = 42000
MAX_DIRECTOR_CHARACTERS_LENGTH = 36000
MAX_DIRECTOR_PLOT_LENGTH = 52000
MAX_DIRECTOR_PROSE_LENGTH = 32000
MAX_DIRECTOR_REPORT_LENGTH = 30000
MAX_GOLD_RULES_CONTEXT_LENGTH = 16000

# --- 角色基本設定輔助函數 ---
# 定義角色只需要傳入的基本欄位，過濾掉冗長的背景故事等欄位
# 核心欄位：name 和 personality 是必留的，其他可以過濾
# CHARACTER_BASIC_FIELDS 定義在 agent_json.py 中，供各模組統一引用

MAX_CHARACTERS_SUMMARY_LENGTH = 26000


def compact_context_text(value, limit, label="context"):
    """Keep both head and tail so long prompts retain setup and latest details."""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            value = str(value)
    if limit is None or limit <= 0 or len(value) <= limit:
        return value
    marker = f"\n\n...[{label} 已因上下文長度限制省略 {len(value) - limit} 字，保留開頭與結尾]...\n\n"
    head_len = max(1, (limit - len(marker)) * 2 // 3)
    tail_len = max(1, limit - len(marker) - head_len)
    return value[:head_len] + marker + value[-tail_len:]


def _parse_jsonish(text):
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if "```" in stripped:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, flags=re.IGNORECASE)
        if match:
            stripped = match.group(1).strip()
    try:
        return json.loads(stripped)
    except Exception:
        return None


CONTEXT_REQUEST_RULE = """
## 資料不足時的回問總監規則
你收到的是系統依當前任務挑選出的必要資料，不一定是全庫資料。若你判斷「缺少必要角色完整設定、世界觀欄位、卷章大綱、伏筆分配、使用者意圖或其他硬性資料」會導致你只能臆造，請停止生成，不要硬編。

此時請只輸出以下 JSON，讓系統與總監補齊資料後再生成：
```json
{
  "_needs_director_context": true,
  "context_request": "請總監補充哪些資料，以及為什麼缺這些資料會阻斷本次生成。",
  "missing_data": ["缺少的資料項目 1", "缺少的資料項目 2"],
  "why_it_blocks_generation": "若直接生成會造成的人設、世界觀或流程風險。"
}
```
只有在資料真的不足以完成任務時才使用；若資料已足夠，必須依原本 schema 直接生成。
"""

DIRECTOR_CONTEXT_REQUEST_RULE = """
## 上下文不足時的總監回問規則
系統會依目前階段挑選最相關的角色與世界觀資料。若你發現本次審查/下令缺少「已存在但未被提供」的必要資料，或需要總監/使用者補充關鍵決策後才能避免臆造，請使用 `WAIT_USER`，並讓 `reason` 以 `[REQUEST_DIRECTOR_CONTEXT]` 開頭，清楚列出缺少資料與需要補充的內容。

注意：若缺少的是前置階段尚未生成的作品資料，仍遵守黃金流程，使用 `CONTINUE` 或回退到對應 target 讓系統生成，不要把一般的未生成狀態誤判成 `WAIT_USER`。
"""

WORLDVIEW_FIELD_LABELS = {
    "title": "作品標題",
    "genre": "類型",
    "style": "風格",
    "theme": "核心主題",
    "main_conflict": "核心衝突",
    "worldview": "世界觀設定",
    "setting": "舞台設定",
    "power_system": "力量系統",
    "rules": "世界規則",
    "factions": "勢力/組織",
    "locations": "重要地點",
    "timeline": "時間線",
    "macro_outline": "整體故事大綱",
    "multi_act_structure": "多幕結構",
    "progressive_character_plan": "角色漸進規劃",
    "foreshadowing_seeds": "伏筆種子",
    "key_turning_points": "關鍵轉折點",
}

WORLDVIEW_FIELDS_BY_STAGE = {
    "worldview": None,
    "characters": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "progressive_character_plan"],
    "foreshadowing": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "multi_act_structure", "progressive_character_plan"],
    "volumes": ["theme", "main_conflict", "macro_outline", "multi_act_structure", "worldview", "setting", "power_system", "factions"],
    "volume_skeleton": ["theme", "main_conflict", "macro_outline", "multi_act_structure", "worldview", "setting", "power_system", "factions", "locations"],
    "writer": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "progressive_character_plan"],
    "editor": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "progressive_character_plan"],
    "copilot": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "multi_act_structure", "progressive_character_plan"],
}

RELATION_SUMMARY_FIELDS = [
    "name", "role", "entry_phase", "faction", "affiliation", "relationships",
    "relationship_matrix", "relation_map", "connections", "character_relationships",
    "relationship_network"
]


def _json_text(value, *, indent=2):
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=indent)
    except Exception:
        return str(value)


def _context_query_text(*parts):
    rendered = []
    for part in parts:
        if part is None:
            continue
        rendered.append(_json_text(part))
    return "\n".join(rendered)


def _normalize_characters_list(characters_data):
    parsed = _parse_jsonish(characters_data)
    if isinstance(parsed, dict):
        chars = parsed.get("characters")
        if isinstance(chars, list):
            return [c for c in chars if isinstance(c, dict)]
        return [parsed]
    if isinstance(parsed, list):
        return [c for c in parsed if isinstance(c, dict)]
    return []


def _character_aliases(char):
    aliases = []
    for key in ("name", "alias", "aliases", "nickname", "nicknames", "also_known_as"):
        value = char.get(key)
        if isinstance(value, str):
            for part in value.replace("，", ",").replace("、", ",").split(","):
                part = part.strip()
                if part:
                    aliases.append(part)
        elif isinstance(value, list):
            aliases.extend(str(item).strip() for item in value if str(item).strip())
    seen = set()
    result = []
    for alias in aliases:
        if alias and alias not in seen:
            seen.add(alias)
            result.append(alias)
    return result


def _name_matches_query(aliases, query_text):
    if not query_text:
        return False
    for alias in aliases:
        if not alias or len(alias) == 1:
            continue
        if alias in query_text:
            return True
    return False


def _relationship_summary(char):
    summary = {}
    for field in RELATION_SUMMARY_FIELDS:
        if field in char and char[field] not in (None, "", [], {}):
            summary[field] = char[field]
    if "name" not in summary and char.get("name"):
        summary["name"] = char.get("name")
    return summary or {"name": char.get("name", "未命名角色")}


def build_relevant_character_context(characters_data, query_text="", force_full_names=None, include_all_full=False, max_full_characters=12):
    """Select full character cards only for characters named in the task context."""
    chars = _normalize_characters_list(characters_data)
    if not chars:
        return characters_data or "尚無角色設定"

    force_full_names = {str(name).strip() for name in (force_full_names or []) if str(name).strip()}
    matched = []
    summaries = []
    query_text = _json_text(query_text)

    for idx, char in enumerate(chars):
        aliases = _character_aliases(char)
        name = char.get("name", f"角色{idx + 1}")
        forced = any(name == n or n in aliases for n in force_full_names)
        is_match = include_all_full or forced or _name_matches_query(aliases, query_text)
        if is_match:
            first_pos = min([query_text.find(alias) for alias in aliases if alias and query_text.find(alias) >= 0] or [10**9])
            matched.append((first_pos, idx, char))
        else:
            summaries.append(_relationship_summary(char))

    matched.sort(key=lambda item: (item[0], item[1]))
    full_chars = [item[2] for item in matched[:max_full_characters]]
    overflow = [item[2] for item in matched[max_full_characters:]]
    summaries.extend(_relationship_summary(char) for char in overflow)

    result = {
        "selection_policy": "大綱/指令/正文/總監上下文中明確提到的角色提供完整角色卡；其餘角色只提供名稱、定位與基本關係，避免無關人設干擾。",
        "matched_full_character_names": [char.get("name", "未命名角色") for char in full_chars],
        "full_characters": full_chars,
        "other_characters_basic_relationships": summaries,
    }
    if overflow:
        result["overflow_note"] = f"另有 {len(overflow)} 位命中角色因單次上下文過大改列基本關係摘要；如本次必須使用，請回問總監補充完整角色卡。"
    return result


def build_relevant_character_context_text(characters_data, query_text="", force_full_names=None, include_all_full=False, limit=MAX_DIRECTOR_CHARACTERS_LENGTH):
    selected = build_relevant_character_context(
        characters_data,
        query_text=query_text,
        force_full_names=force_full_names,
        include_all_full=include_all_full,
    )
    return compact_context_text(_json_text(selected), limit, "任務相關角色上下文")


def select_worldview_context(worldview_text, current_stage="copilot", query_text="", force_full=False, limit=MAX_DIRECTOR_WORLDVIEW_LENGTH):
    """Select worldview fields by stage first; use length limits only as an emergency guard."""
    if not worldview_text:
        return "（尚無世界觀設定）"
    parsed = _parse_jsonish(worldview_text)
    if not isinstance(parsed, dict):
        return compact_context_text(worldview_text, limit, "世界觀上下文")

    stage = current_stage or "copilot"
    field_order = WORLDVIEW_FIELDS_BY_STAGE.get(stage, WORLDVIEW_FIELDS_BY_STAGE["copilot"])
    if force_full or field_order is None:
        return compact_context_text(_json_text(parsed), limit, "完整世界觀")

    query_text = _json_text(query_text)
    selected_keys = []
    for key in field_order:
        if key in parsed and parsed[key] not in (None, "", [], {}):
            selected_keys.append(key)

    for key, value in parsed.items():
        if key in selected_keys or value in (None, "", [], {}):
            continue
        label = WORLDVIEW_FIELD_LABELS.get(key, key)
        if key in query_text or label in query_text:
            selected_keys.append(key)

    selected = {}
    for key in selected_keys:
        value = parsed.get(key)
        selected[key] = value if isinstance(value, (dict, list)) else str(value)

    result = {
        "selection_policy": f"依 current_stage={stage} 選入必要世界觀欄位；只有被本次任務命中的額外欄位才追加。長度上限僅作溢位保護。",
        "selected_fields": selected_keys,
        "worldview_context": selected,
    }
    return compact_context_text(_json_text(result), limit, "任務相關世界觀上下文")


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
            parsed = _parse_jsonish(characters_data)
            if parsed is None:
                return characters_data
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
            parsed = _parse_jsonish(characters_data)
            if parsed is None:
                return []
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
        parsed = _parse_jsonish(worldview_text)
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
                    if key == "macro_outline":
                        val = compact_context_text(val, MAX_MACRO_OUTLINE_LENGTH, title)
                    summary_parts.append(f"{title}\n{val}")
                
            if summary_parts:
                return compact_context_text("\n\n".join(summary_parts), MAX_WORLDVIEW_SUMMARY_LENGTH, "世界觀摘要")
    except Exception:
        pass
        
    return compact_context_text(worldview_text, MAX_WORLDVIEW_SUMMARY_LENGTH, "世界觀摘要")

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
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n"
    
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

def build_foreshadowing_messages(worldview_text, characters_json, user_prompt=None):
    """伏筆與轉折編織師提示詞拼接"""
    schema_snippet = "\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this schema. Wrap in ```json ... ``` codeblock]\n"
    from agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json
    schema_snippet += json.dumps(FORESHADOWING_OUTPUT_SCHEMA, ensure_ascii=False, indent=2)
    system_prompt = f"{FORESHADOWING_ORCHESTRATOR_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【角色 Bible 與人設】
{characters_json}

【額外伏筆/轉折設計指令】
{user_prompt or "請根據世界設定與角色背景，設計一整套豐富的伏筆種子與關鍵轉折點。"}

【不可違反的輸出契約】
1. 最外層 JSON 必須只有一個物件，且只能包含兩個頂層鍵：`foreshadowing_seeds` 與 `key_turning_points`。
2. `foreshadowing_seeds` 必須是陣列，至少 50 個；`key_turning_points` 必須是陣列，至少 50 個；少於此數量即為失敗輸出。
3. 每個 `foreshadowing_seeds` 項目只能使用這些欄位：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`。
4. 每個 `key_turning_points` 項目只能使用這些欄位：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。
5. `id` 必須是 JSON number / integer，從 1 開始連續編號；禁止填 `FS001`、`Seed-001`、`TP001`、`Turn-001`、中文標號或任何文字。
6. 所有文字內容只能填入名稱、描述、提示、影響、代價、主題連結等文字欄位；禁止把情節文字、標號規則或說明塞入 `id`、`index`、`number` 類欄位。
7. 禁止輸出 `volume_1`、`volume_2`、`act_1` 等作為頂層鍵；卷/幕/章節只能寫入文字欄位的內容裡。
8. 此階段只生成全書伏筆與關鍵轉折藍圖，不需要章節正文、卷骨架，也不可要求 writer/editor 先執行。
9. 每個 seed 必須具備可埋設的具體載體、表層偽裝與未來回收方向；不得用同義改寫湊數。
10. 每個 turning point 必須能造成局勢、關係或角色弧線的實質改變；不得用普通事件湊數。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx):
    """篇卷規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("volumes")
    system_prompt = f"{VOLUMES_PLANNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n"
    
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
    system_prompt = f"{VOLUME_SKELETON_PROMPT.format(volume_index=volume_index, start_ch=start_ch, end_ch=end_ch, vol_chapter_count=vol_chapter_count)}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n"
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務】
- 當前篇卷序號：第 {volume_index} 卷
- 篇卷標題：{current_vol['title']}
- 篇卷概要：{current_vol['summary']}
- 本次輸出章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {vol_chapter_count} 章）
請務必只輸出此範圍內的章節骨架；不得輸出範圍外章節，不得重寫同卷其他已存在章節。

{surrounding_context}
{precalc_clues}

【allocated_tasks 硬性填寫規則】
- 你不得自行挑選、推測、複製或新增任何伏筆 Seed / turning point 到未指定章節。
- 只有上方清單明確列出的章節，才可在 allocated_tasks 對應陣列填入該任務。
- 未列出任務的章節必須輸出：foreshadowing_plants: [], foreshadowing_payoffs: [], turning_points: []。
- 若同一 Seed 看似同時需要埋設與回收，視為錯誤；請以章節清單中的單一操作為準。
【使用者額外提示詞 (Prompt)】
{user_prompt or "請為本卷精心設計簡易骨架大綱。"}

請只為本次指定章節範圍生成符合 JSON 結構的 chapters_skeleton 清單。輸出章數必須等於上方指定範圍的章數，chapter_index 必須連續且不可缺漏。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_chapter_writer_messages(worldview_text, characters_bible, current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, custom_style, chapter_index, user_prompt=None):
    """正文作家寫作提示詞拼接"""
    system_prompt = CHAPTER_WRITER_PROMPT.format(writing_style=custom_style) + "\n" + CONTEXT_REQUEST_RULE
    
    context_query = _context_query_text(current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, user_prompt)
    characters_bible_filtered = build_relevant_character_context(
        characters_bible,
        query_text=context_query,
        force_full_names=(current_outline or {}).get("characters_active") if isinstance(current_outline, dict) else None,
    )
    
    extra_prompt_block = ""
    if user_prompt and str(user_prompt).strip():
        extra_prompt_block = f"""
【本章額外創作指令】
{str(user_prompt).strip()}
"""

    user_content = f"""【世界觀背景】
{worldview_text}

【角色 Bible 聖經】(命中角色完整設定；其他角色名稱與基本關係)
{json.dumps(characters_bible_filtered, ensure_ascii=False, indent=2)}

【當前章節 (第 {chapter_index} 章) 大綱】
{json.dumps(current_outline, ensure_ascii=False, indent=2)}

{surrounding_plot}
{vol_outline_context}
{clue_payoff_details}
{extra_prompt_block}

請根據以上豐富的上下文細節，展開本章正文寫作；正文目標字數為 1500 至 2000 字左右，不要寫成摘要或短章。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_editor_agent_messages(chapter_index, edit_instructions, original_prose):
    """編輯姬提示詞拼接"""
    system_prompt = EDITOR_PROMPT + "\n" + CONTEXT_REQUEST_RULE
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


def build_copilot_chat_messages(novel_id, worldview_text, characters_text, plot_text, history_context, user_message, validation_report=None, gold_rules_context=None):
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
    
    # Select task-relevant context first; length limits are only overflow guards.
    context_query = _context_query_text(user_message, plot_text, history_context)
    worldview_summary = select_worldview_context(worldview_text, "copilot", query_text=context_query)
    gold_rules_context = compact_context_text(gold_rules_context, MAX_GOLD_RULES_CONTEXT_LENGTH, "創作金律")
    
    characters_summary = build_relevant_character_context_text(characters_text, query_text=context_query)
    
    plot_summary = compact_context_text(simplify_plot_data_for_copilot(plot_text), MAX_DIRECTOR_PLOT_LENGTH, "大綱")
    gold_rules_block = f"\n【既有會議討論聖經 / 創作金律（若存在，需作為總監判斷參考）】\n{gold_rules_context}\n" if gold_rules_context else ""
    
    user_content = f"""【當前專案實際設定與大綱內容】
- 【世界觀主題與設定】：
{worldview_summary}

- 【角色 Bible 聖經（基本人設）】：
{characters_summary}

- 【全書篇卷與大綱（簡化版）】：
{plot_summary}

{gold_rules_block}
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
        parsed = _parse_jsonish(worldview_text)
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
    director_context_block=None,
    gold_rules_context=None
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
    import db
    novel = db.get_novel(novel_id)
    raw_worldview_text = worldview_text
    raw_characters_text = characters_text
    context_query = _context_query_text(plot_text, written_chapters_text, user_prompt, character_review_hint, character_review_target_content, director_context_block)
    worldview_text = select_worldview_context(raw_worldview_text, current_stage, query_text=context_query, force_full=(current_stage == "worldview"))
    characters_text = build_relevant_character_context_text(
        raw_characters_text,
        query_text=context_query,
        include_all_full=(current_stage == "characters"),
    )
    plot_text = compact_context_text(plot_text, MAX_DIRECTOR_PLOT_LENGTH, "大綱/卷骨架")
    written_chapters_text = compact_context_text(written_chapters_text, MAX_DIRECTOR_PROSE_LENGTH, "正文")
    validation_report = compact_context_text(validation_report, MAX_DIRECTOR_REPORT_LENGTH, "校驗報告")
    gold_rules_context = compact_context_text(gold_rules_context, MAX_GOLD_RULES_CONTEXT_LENGTH, "創作金律")

    pipeline_prompt = compact_context_text((novel.get("pipeline_prompt") or "").strip() if novel else "", 12000, "原始需求")
    user_prompt_clean = compact_context_text((user_prompt or "").strip(), 12000, "當前指示")
    is_only_bg = (not user_prompt_clean) or (user_prompt_clean == pipeline_prompt)

    # Prepare prompt blocks
    bg_prompt_block = f"""【使用者建書初期原始需求（僅作為整體背景與大綱風格參考，非當前修改指令）】
{pipeline_prompt}"""

    if is_only_bg:
        active_instruction_block = ""
        worldview_user_prompt_section = bg_prompt_block
        default_user_prompt_section = bg_prompt_block
    else:
        active_instruction_block = f"""【當前步驟修改指示 / 系統錯誤自癒回報（請優先滿足此要求）】
{user_prompt_clean}"""
        worldview_user_prompt_section = f"{active_instruction_block}\n\n{bg_prompt_block}"
        default_user_prompt_section = f"{active_instruction_block}\n\n{bg_prompt_block}"

    # 取得該階段的通過標準
    from agent_json import format_criteria_for_prompt
    stage_criteria = format_criteria_for_prompt(current_stage)
    
    # 取得世界觀的 macro_outline
    macro_outline = ""
    if raw_worldview_text:
        try:
            parsed = _parse_jsonish(raw_worldview_text)
            macro_outline = parsed.get("macro_outline", "") if isinstance(parsed, dict) else ""
        except:
            # 嘗試從文本提取
            if "【整體故事大綱】" in str(raw_worldview_text):
                parts = str(raw_worldview_text).split("【整體故事大綱】")
                if len(parts) > 1:
                    macro_outline = parts[1].strip()
    macro_outline = compact_context_text(macro_outline, MAX_MACRO_OUTLINE_LENGTH, "整體故事大綱")
    if character_review_target_content:
        character_review_target_content = compact_context_text(character_review_target_content, 12000, "目標角色")
    if character_review_hint:
        character_review_hint = compact_context_text(character_review_hint, 8000, "角色修改提示")
    if director_context_block:
        director_context_block = compact_context_text(director_context_block, 16000, "總監補充上下文")
                    
    # 總監評斷世界觀時需要完整傳入，而其他階段已經通過審核，將其內部的伏筆與轉折欄位改為 "此區塊通過審核不需評判"
    if current_stage != "worldview":
        worldview_text = mask_worldview_seeds_and_turns(worldview_text)

    # 根據 current_stage 構建不同的審查內容
    if current_stage == "worldview":
        # 世界觀階段：只傳世界觀完整內容 + 評斷提示詞
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前世界觀的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（世界觀架構師）。
2. 對比使用者的原始意圖，檢查世界觀是否完整且具備深度，是否忠實體現了使用者的原始大綱與輸入走向。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""{worldview_user_prompt_section}
 
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
        
        user_content = f"""{default_user_prompt_section}
 
【世界觀背景】
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
        user_content = f"""{default_user_prompt_section}
 
【世界觀的整體故事大綱 (macro_outline)】
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
        user_content = f"""{default_user_prompt_section}
 
【世界觀的整體故事大綱 (macro_outline)】
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
        characters_filtered = build_relevant_character_context(raw_characters_text, query_text=context_query)
        user_content = f"""{default_user_prompt_section}
 
【世界觀背景】
{worldview_text}
 
【角色 Bible 聖經（命中角色完整設定；其他角色名稱與基本關係）】
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

        user_content = f"""{default_user_prompt_section}
 
【世界觀背景】
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
        user_content = f"""{default_user_prompt_section}
 
【當前各板塊數據】
- 世界觀設定：{worldview_text[:1500] if worldview_text else "（空）"}
- 角色設定：{characters_text[:1500] if characters_text else "（空）"}
- 大綱設定：{plot_text[:1500] if plot_text else "（空）"}
- 正文：{written_chapters_text if written_chapters_text else "（空）"}
 
請進行深度評估，決定下一步行動！
"""
    
    if gold_rules_context:
        system_prompt += f"""

## 既有會議討論聖經 / 創作金律
以下內容來自本作品先前輸出的 retrospective gold rules。它是總監下指令時的參考規則，應用於判斷風格、避坑與流程建議；若與系統底層剛性校驗報告衝突，仍以 Python 校驗報告為準。
{gold_rules_context}
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

    system_prompt += f"\n\n{DIRECTOR_CONTEXT_REQUEST_RULE}\n"
    system_prompt += f"\n\n## 系統底層剛性校驗報告（Python 計算絕對事實，請以此為準）\n{validation_report}\n"
    
    if director_context_block:
        user_content += f"\n\n{director_context_block}"

    # 統一在 user_content 尾端附加額外的說明
    if not is_only_bg:
        if "【當前步驟修改指示" not in user_content:
            user_content += f"\n\n{active_instruction_block}"
    else:
        if "【使用者建書初期原始需求" not in user_content:
            user_content += f"\n\n{bg_prompt_block}"
    
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
    from agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json
    
    if target_section == "foreshadowing_seeds":
        schema = {"foreshadowing_seeds": FORESHADOWING_OUTPUT_SCHEMA["foreshadowing_seeds"]}
        schema_snippet = f"\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this schema. Wrap in ```json ... ``` codeblock]\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    elif target_section == "key_turning_points":
        schema = {"key_turning_points": FORESHADOWING_OUTPUT_SCHEMA["key_turning_points"]}
        schema_snippet = f"\n[CRITICAL REQUIREMENT: Output strictly in JSON format matching this schema. Wrap in ```json ... ``` codeblock]\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    else:
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






