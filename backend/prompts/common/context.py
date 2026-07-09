# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
from backend.schemas import agent_json
from backend import persistence as db
from backend.schemas.agent_json import CHARACTER_BASIC_FIELDS
from backend.prompts.prompt_main import (
    STORY_ARCHITECT_PROMPT,
    STORY_ARCHITECT_GUIDELINES,
    VOLUMES_PLANNER_PROMPT,
    VOLUMES_PLANNER_GUIDELINES,
    VOLUME_SKELETON_PROMPT,
    VOLUME_SKELETON_GUIDELINES,
    CHARACTER_DESIGNER_PROMPT,
    CHARACTER_DESIGNER_GUIDELINES,
    FORESHADOWING_ORCHESTRATOR_PROMPT,
    FORESHADOWING_ORCHESTRATOR_GUIDELINES,
    CHAPTER_WRITER_PROMPT,
    CHAPTER_WRITER_GUIDELINES,
    VOLUME_SKELETON_PROMPT_PLUS,
    CHARACTER_DESIGNER_PROMPT_PLUS
)
from backend.prompts.prompt_detail_modifier import (
    EDITOR_PROMPT,
    INCREMENTAL_CHARACTER_PROMPT,
    INCREMENTAL_CHARACTER_APPEND_PROMPT
)
from backend.prompts.prompt_instructions import (
    CO_PILOT_ORCHESTRATOR_PROMPT,
    DIRECTOR_COMMON_FOOTER
)
from backend.prompts.output_contracts import (
    CONTEXT_REQUEST_JSON_CONTRACT,
    DIRECTOR_DECISION_KEY_CONTRACT,
    DIRECTOR_HARD_VALIDATION_POLICY,
    DIRECTOR_MANDATORY_INSPECTION_POLICY,
    DIRECTOR_TOOL_CALL_CONTRACT,
    STRICT_JSON_KEY_CONTRACT,
    format_json_schema_prompt,
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


def build_agent_context_contract(agent_name, visible_context, generation_boundary, output_boundary):
    """Shared prompt block that tells each agent what it can actually see and where to stop."""
    return f"""

## 本輪可見上下文與生成邊界（{agent_name}）
你只能依據本輪訊息中明確提供的資料工作；不要假裝看得到資料庫、前端狀態、其他 Agent 的完整輸出或未提供的舊版本。

【你可以看見】
{visible_context}

【你的任務邊界】
{generation_boundary}

【輸出限制】
{output_boundary}

若缺少會直接影響正確生成的必要資料，請依「資料不足時的回問總監規則」輸出 context request JSON；不要用猜測補完核心設定、角色關係、卷章大綱或正文事實。
"""


def compact_context_text(value, limit, label="context"):
    """Emergency transport guard; normal detail selection should use structured/paged context."""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            value = str(value)
    if limit is None or limit <= 0 or len(value) <= limit:
        return value

    # Map label to specific tools
    tool_ref = "inspect_content_block"
    params = {}
    if label in ("foreshadowing_seeds", "key_turning_points"):
        tool_ref = "expand_collapsed_json"
        params = {"stage_name": "foreshadowing", "field_name": label}
    elif "上一輪" in label:
        block_name = "input_data" if "input" in label.lower() or "指示" in label.lower() or "user" in label.lower() else "output_data"
        params = {"stage_name": "last_agent_run", "block_name": block_name}
    else:
        # Default fallback
        params = {"stage_name": "當前審核階段名稱"}
        if "角色" in label or label == "characters":
            params["stage_name"] = "characters"
            params["block_name"] = "characters"
        elif "世界觀" in label or label == "worldview":
            params["stage_name"] = "worldview"
        elif "大綱" in label or "骨架" in label:
            params["stage_name"] = "volume_skeleton"
            params["block_name"] = "chapters_outline"
        elif "正文" in label:
            params["stage_name"] = "writer"
            params["block_name"] = "chapter"

    collapse_info = {
        "director_payload_view": "collapsed_json",
        "payload_kind": label,
        "char_count": len(value),
        "message": f"該 {label} 已由後端收合以防止原始截斷。",
        "available_expansion_tool": {
            "tool_name": tool_ref,
            "parameters_template": params,
            "usage_note": (
                f"如需展開已被收合的 {label}，總監必須自行輸出完整決策 envelope；"
                "不得直接把此資料欄位當成回覆。"
            )
        }
    }
    return json.dumps(collapse_info, ensure_ascii=False, indent=2)

def compact_json_data(data, max_list_items=10):
    """
    Recursively process dictionary or list to compact large lists.
    Keeps the first N and last M items of a list (default total N+M = max_list_items),
    and replaces the middle items with a summary indicator to preserve JSON validity.
    """
    if isinstance(data, dict):
        return {k: compact_json_data(v, max_list_items) for k, v in data.items()}
    elif isinstance(data, list):
        total_len = len(data)
        if total_len > max_list_items:
            if max_list_items <= 0:
                head_len = 0
                tail_len = 0
            else:
                head_len = max_list_items // 2
                tail_len = max_list_items - head_len
            head = [compact_json_data(item, max_list_items) for item in data[:head_len]]
            tail = [compact_json_data(item, max_list_items) for item in data[-tail_len:]] if tail_len else []
            omitted = total_len - max_list_items
            
            # Use a consistent structural summary marker so callers can detect compaction reliably.
            summary_item = {
                "...摘要...": (
                    f"資料庫中實際已完整儲存共 {total_len} 筆項目；此處只提供前後預設視圖，"
                    f"不是資料缺失。中間 {omitted} 筆已收合；若需逐項審查，請由總監指定 "
                    "1-based start_index/end_index 呼叫 inspect_content_block 或 expand_collapsed_json。"
                )
            }
            
            return head + [summary_item] + tail
        else:
            return [compact_json_data(item, max_list_items) for item in data]
    else:
        return data


def collapse_json_output_for_director(raw_output, stage_name, preview_count=5):
    """
    對 Director 的 last_run_block Output 進行「一律前N項展示 + 其餘收合」處理。
    無論原始字數多少，只要是 JSON 且含有 list 欄位，就執行收合。
    非 JSON 或無 list 的純文字輸出，保留原文（最多 6000 字元）。

    回傳值：
      - 若成功解析 JSON 且含列表 → 回傳結構化摘要字串（JSON 格式，含展開工具參考）
      - 若純文字或解析失敗 → 回傳原文前 6000 字元
    """
    if not raw_output or not isinstance(raw_output, str):
        return raw_output or ""

    # --- Step 1: 嘗試解析 JSON ---
    parsed = None
    stripped = raw_output.strip()
    # 移除 markdown code fence
    import re as _re
    _fence_match = _re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, flags=_re.IGNORECASE)
    if _fence_match:
        stripped = _fence_match.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except Exception:
        parsed = None

    # --- Step 2: 若無法解析為 JSON，回傳純文字截斷 ---
    if parsed is None:
        truncated = raw_output[:6000]
        suffix = f"\n...[純文字輸出已截斷，共 {len(raw_output)} 字元]..." if len(raw_output) > 6000 else ""
        return truncated + suffix

    # --- Step 3: 欄位對應工具映射 ---
    FIELD_TOOL_MAP = {
        "multi_act_structure": {"tool_name": "expand_collapsed_json", "params": {"stage_name": "worldview", "field_name": "multi_act_structure"}},
        "progressive_character_plan": {"tool_name": "expand_collapsed_json", "params": {"stage_name": "worldview", "field_name": "progressive_character_plan"}},
        "foreshadowing_seeds": {"tool_name": "expand_collapsed_json", "params": {"stage_name": "foreshadowing", "field_name": "foreshadowing_seeds"}},
        "key_turning_points":  {"tool_name": "expand_collapsed_json", "params": {"stage_name": "foreshadowing", "field_name": "key_turning_points"}},
        "characters":          {"tool_name": "inspect_content_block", "params": {"stage_name": "characters",      "block_name": "characters"}},
        "volumes":             {"tool_name": "inspect_content_block", "params": {"stage_name": "volumes",         "block_name": "volumes"}},
        "chapters_outline":    {"tool_name": "inspect_content_block", "params": {"stage_name": "volume_skeleton", "block_name": "chapters_outline"}},
        "chapters":            {"tool_name": "inspect_content_block", "params": {"stage_name": "volume_skeleton", "block_name": "chapters"}},
    }

    def _default_tool(field_name):
        return {"tool_name": "inspect_content_block", "params": {"stage_name": stage_name, "block_name": field_name}}

    def _build_collapse_marker(field_name, total, tool_info):
        next_start = preview_count + 1
        return {
            "...收合標記...": (
                f"⚠️ 此 {field_name} 共 {total} 筆項目；此處僅展示前 {preview_count} 筆供快速審閱，"
                f"已收合第 {next_start}~{total} 筆。這表示資料已存在，不代表只有 {preview_count} 筆。"
            ),
            "_director_note": (
                f"若需逐項審查第 {next_start}~{total} 筆，"
                f"可參考 available_expansion_tool 使用 {tool_info['tool_name']}。"
                "這不是總監回覆格式；總監輸出仍必須是完整決策 envelope。"
            ),
            "available_expansion_tool": {
                "tool_name": tool_info["tool_name"],
                "parameters_template": {
                    **tool_info["params"],
                    "start_index": next_start,
                    "end_index": total
                },
                "usage_note": (
                    "這是可用工具參考，不是總監回覆。若要使用，必須輸出完整 "
                    "`{\"action\":\"TOOL_CALL\",\"tool_call\":...}` envelope。"
                )
            }
        }

    def _collapse_list_field(field_name, lst):
        total = len(lst)
        if total <= preview_count:
            return lst  # 不需要收合
        tool_info = FIELD_TOOL_MAP.get(field_name) or _default_tool(field_name)
        return lst[:preview_count] + [_build_collapse_marker(field_name, total, tool_info)]

    # --- Step 4: 根據頂層型別處理 ---
    if isinstance(parsed, dict):
        result = {}
        has_collapsed = False
        for key, val in parsed.items():
            if isinstance(val, list) and len(val) > preview_count:
                result[key] = _collapse_list_field(key, val)
                has_collapsed = True
            else:
                result[key] = val
        raw_json = json.dumps(result, ensure_ascii=False, indent=2)
        if len(raw_json) > 8000:
            return compact_context_text(raw_json, 8000, "上一輪 Agent output")
        return raw_json

    elif isinstance(parsed, list):
        # 頂層直接是 list（較少見，如舊格式 characters）
        total = len(parsed)
        if total > preview_count:
            tool_info = _default_tool(stage_name)
            marker = _build_collapse_marker(stage_name, total, tool_info)
            result_list = parsed[:preview_count] + [marker]
            raw_json = json.dumps(result_list, ensure_ascii=False, indent=2)
        else:
            raw_json = json.dumps(parsed, ensure_ascii=False, indent=2)
        if len(raw_json) > 8000:
            return compact_context_text(raw_json, 8000, "上一輪 Agent output")
        return raw_json

    else:
        # 純量值（不太可能是 Output，但做保底）
        val_str = str(parsed)
        if len(val_str) > 8000:
            return compact_context_text(val_str, 8000, "上一輪 Agent output")
        return val_str


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

__CONTEXT_REQUEST_JSON_CONTRACT__
只有在資料真的不足以完成任務時才使用；若資料已足夠，必須依原本 schema 直接生成。
""".replace("__CONTEXT_REQUEST_JSON_CONTRACT__", CONTEXT_REQUEST_JSON_CONTRACT)

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
    "writer": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "multi_act_structure", "progressive_character_plan"],
    "editor": ["theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "locations", "macro_outline", "progressive_character_plan"],
    "director": ["title", "theme", "main_conflict", "worldview", "setting", "power_system", "rules", "factions", "timeline", "macro_outline", "progressive_character_plan"],
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
        if not alias:
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


def build_relevant_character_context(characters_data, query_text="", force_full_names=None, include_all_full=False, max_full_characters=12, max_character_tokens=8000):
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

    est_tokens = len(_json_text(result)) / 4
    if est_tokens > max_character_tokens:
        for fi in range(len(result.get("full_characters", []))):
            if est_tokens <= max_character_tokens:
                break
            full_char = result["full_characters"][fi]
            demoted = _relationship_summary(full_char)
            result["full_characters"][fi] = demoted
            name = full_char.get("name", "未命名角色")
            if name in result.get("matched_full_character_names", []):
                result["matched_full_character_names"].remove(name)
            result.setdefault("other_characters_basic_relationships", []).append(demoted)
            result["demotion_note"] = f"部分命中角色因上下文預算限制改列基本關係摘要；如需完整角色卡請回問總監。"
            est_tokens = len(_json_text(result)) / 4

    return result


def build_relevant_character_context_text(characters_data, query_text="", force_full_names=None, include_all_full=False, limit=MAX_DIRECTOR_CHARACTERS_LENGTH):
    selected = build_relevant_character_context(
        characters_data,
        query_text=query_text,
        force_full_names=force_full_names,
        include_all_full=include_all_full,
    )
    # Apply structural JSON compaction to prevent breaking JSON by simple string truncation
    compacted_selected = compact_json_data(selected, max_list_items=10)
    return compact_context_text(_json_text(compacted_selected), limit, "任務相關角色上下文")


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
        # 世界觀評判階段，必須將多幕起伏與角色漸進的完整內容傳給總監，不可進行清單截斷
        if stage == "worldview":
            return compact_context_text(_json_text(parsed), limit, "完整世界觀")
        # Apply structural JSON compaction even for full worldview to preserve JSON structure
        compacted_parsed = compact_json_data(parsed, max_list_items=15)
        return compact_context_text(_json_text(compacted_parsed), limit, "完整世界觀")

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

    # Apply structural JSON compaction to prevent breaking JSON by simple string truncation
    compacted_selected = compact_json_data(selected, max_list_items=10)

    result = {
        "selection_policy": f"依 current_stage={stage} 選入必要世界觀欄位；只有被本次任務命中的額外欄位才追加。長度上限僅作溢位保護。",
        "selected_fields": selected_keys,
        "worldview_context": compacted_selected,
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

def mask_worldview_seeds_and_turns(worldview_text):
    if not worldview_text:
        return worldview_text
    
    try:
        parsed = _parse_jsonish(worldview_text)
        if isinstance(parsed, dict):
            target = parsed
            if "worldview_context" in parsed and isinstance(parsed["worldview_context"], dict):
                target = parsed["worldview_context"]
            if "foreshadowing_seeds" in target:
                target["foreshadowing_seeds"] = "此區塊通過審核不需評判"
            if "key_turning_points" in target:
                target["key_turning_points"] = "此區塊通過審核不需評判"
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

