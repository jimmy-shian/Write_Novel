# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
from backend.schemas import agent_json
from backend import db
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
        "tool_call_instruction": {
            "action": "TOOL_CALL",
            "tool_call": {
                "tool_name": tool_ref,
                "parameters": params
            },
            "reason": f"展開已被收合的 {label}，以進行品質審核。"
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
                    f"資料庫中實際已完整儲存共 {total_len} 筆項目；此處只提供預設視圖，"
                    f"收合中間 {omitted} 筆。若需逐項審查，請由總監指定 start_index/end_index "
                    "呼叫 inspect_content_block 或 expand_collapsed_json。"
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
      - 若成功解析 JSON 且含列表 → 回傳結構化摘要字串（JSON 格式，含工具指令）
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
        return {
            "...收合標記...": (
                f"⚠️ 此 {field_name} 共 {total} 筆項目；此處僅展示前 {preview_count} 筆供快速審閱，"
                f"已收合其餘 {total - preview_count} 筆。"
            ),
            "_director_note": (
                f"若需逐項審查第 {preview_count + 1}~{total} 筆，"
                f"請呼叫工具：{tool_info['tool_name']}，"
                f"params={json.dumps({**tool_info['params'], 'start_index': preview_count, 'end_index': total - 1}, ensure_ascii=False)}"
            ),
            "tool_call_instruction": {
                "action": "TOOL_CALL",
                "tool_call": {
                    "tool_name": tool_info["tool_name"],
                    "parameters": {
                        **tool_info["params"],
                        "start_index": preview_count,
                        "end_index": total - 1
                    }
                },
                "reason": f"展開 {field_name} 第 {preview_count + 1}~{total} 項以進行完整品質審核。"
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
        if has_collapsed:
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            # 沒有需要收合的 list → 原始 JSON，但限 8000 字元
            raw_json = json.dumps(parsed, ensure_ascii=False, indent=2)
            return raw_json[:8000] + ("\n...[JSON 已截斷]..." if len(raw_json) > 8000 else "")

    elif isinstance(parsed, list):
        # 頂層直接是 list（較少見，如舊格式 characters）
        total = len(parsed)
        if total > preview_count:
            tool_info = _default_tool(stage_name)
            marker = _build_collapse_marker(stage_name, total, tool_info)
            result_list = parsed[:preview_count] + [marker]
            return json.dumps(result_list, ensure_ascii=False, indent=2)
        else:
            return json.dumps(parsed, ensure_ascii=False, indent=2)

    else:
        # 純量值（不太可能是 Output，但做保底）
        return str(parsed)[:6000]


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
__STRICT_JSON_KEY_CONTRACT__
```json
{
  "_needs_director_context": true,
  "context_request": "請總監補充哪些資料，以及為什麼缺這些資料會阻斷本次生成。",
  "missing_data": ["缺少的資料項目 1", "缺少的資料項目 2"],
  "why_it_blocks_generation": "若直接生成會造成的人設、世界觀或流程風險。"
}
```
只有在資料真的不足以完成任務時才使用；若資料已足夠，必須依原本 schema 直接生成。
""".replace("__STRICT_JSON_KEY_CONTRACT__", STRICT_JSON_KEY_CONTRACT)

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

def get_json_schema_prompt_snippet(schema_name):
    """Return canonical output schema + approval criteria from agent_json.py."""
    stage_map = {
        "worldview": "worldview",
        "worldview_core": "worldview_core",
        "multi_act_structure": "multi_act_structure",
        "progressive_character_plan": "progressive_character_plan",
        "foreshadowing": "foreshadowing",
        "character": "characters",
        "characters": "characters",
        "volumes": "volumes",
        "skeleton": "volume_skeleton",
        "volume_skeleton": "volume_skeleton",
        "writer": "writer",
        "editor": "editor",
    }
    criteria_stage_map = {
        "worldview_core": "worldview",
        "multi_act_structure": "worldview",
        "progressive_character_plan": "worldview",
        "skeleton": "volume_skeleton",
        "character": "characters",
    }
    stage_name = stage_map.get(schema_name, schema_name)
    criteria_stage = criteria_stage_map.get(schema_name, stage_name)
    return (
        f"{STRICT_JSON_KEY_CONTRACT}\n"
        f"{agent_json.format_output_schema_for_prompt(stage_name, label=schema_name)}\n"
        f"{agent_json.format_criteria_for_prompt(criteria_stage)}"
    )


def build_story_architect_messages(genre, style, user_prompt):
    """世界觀架構師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("worldview")
    system_prompt = f"{STORY_ARCHITECT_PROMPT}\n\n{schema_snippet}\n\n{STORY_ARCHITECT_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Story Architect / 世界觀架構師",
        "- 類型、風格基調、作者原始創作需求。\n- 若是重跑或局部調整，會在使用者內容中明確提供指定要求。",
        "只建立世界觀、核心衝突、全書宏觀大綱、多幕結構與角色登場策略；不要生成角色 Bible、卷列表、章節骨架或正文。",
        "輸出必須是完整 worldview JSON；不得在 JSON 外加入解釋；不得把伏筆種子與關鍵轉折點當成本階段主要產物。"
    )
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

def build_worldview_core_messages(genre, style, user_prompt):
    """僅生成世界觀核心設定（theme, main_conflict, worldview, macro_outline）的提示詞"""
    from backend.prompts.prompt_main import STORY_ARCHITECT_PROMPT, STORY_ARCHITECT_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("worldview_core")
    system_prompt = f"{STORY_ARCHITECT_PROMPT}\n\n{schema_snippet}\n\n{STORY_ARCHITECT_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Story Architect Core / 核心世界觀架構師",
        "- 類型、風格基調、作者原始創作需求。\n- 本階段尚未有多幕結構、角色策略、角色 Bible、篇卷與正文。",
        "只生成 theme、main_conflict、worldview、macro_outline 四個核心欄位，為後續子階段提供基底。",
        "輸出只能是核心世界觀 JSON；不要生成 multi_act_structure、progressive_character_plan、characters、volumes 或 chapters。"
    )
    
    user_content = f"""【使用者創作需求與設定】
類型：{genre}
風格基調：{style}
詳細故事描述/要求：{user_prompt}

請根據以上設定，僅生成核心世界觀（theme、main_conflict、worldview、macro_outline）的 JSON 設定。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_multi_act_structure_messages(worldview_core_json, user_prompt):
    """基於核心世界觀，獨立生成多幕式起伏結構的提示詞"""
    from backend.prompts.prompt_main import MULTI_ACT_STRUCTURE_PROMPT, MULTI_ACT_STRUCTURE_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("multi_act_structure")
    system_prompt = f"{MULTI_ACT_STRUCTURE_PROMPT}\n\n{schema_snippet}\n\n{MULTI_ACT_STRUCTURE_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Drama Structure Specialist / 多幕式結構師",
        "- 已生成的核心世界觀 JSON。\n- 作者原始要求只作為風格與方向參考。",
        "只規劃 multi_act_structure，描述全書起伏、危機遞進與幕次功能。",
        "輸出只能包含 multi_act_structure；不要改寫核心世界觀，不要生成角色 Bible、伏筆清單、篇卷或章節。"
    )
    
    user_content = f"""【已確定的核心世界觀設定】
{worldview_core_json}

【使用者原始要求（參考）】
{user_prompt}

請根據上述已確定的核心設定，獨立規劃並生成大長篇故事的「多幕式起伏結構（multi_act_structure）」。
幕次 title 必須嚴格統一為『第一幕 (自擬階段名稱)』、『第二幕 (自擬階段名稱)』等格式，使用中文數字編號，不允許使用『1.』、『1-01』、『Setup』、『Act 1』等標號。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_progressive_character_plan_messages(worldview_core_json, multi_act_json, user_prompt):
    """基於核心世界觀與多幕式結構，獨立生成角色漸進登場規劃策略的提示詞"""
    from backend.prompts.prompt_main import PROGRESSIVE_CHARACTER_PLAN_PROMPT, PROGRESSIVE_CHARACTER_PLAN_GUIDELINES
    schema_snippet = get_json_schema_prompt_snippet("progressive_character_plan")
    system_prompt = f"{PROGRESSIVE_CHARACTER_PLAN_PROMPT}\n\n{schema_snippet}\n\n{PROGRESSIVE_CHARACTER_PLAN_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Character Progression Planner / 角色登場策略規劃師",
        "- 已生成的核心世界觀 JSON。\n- 已生成的 multi_act_structure。\n- 作者原始要求只作為風格與方向參考。",
        "只規劃 progressive_character_plan，說明各波次需要哪些角色功能與登場節奏。",
        "輸出只能包含 progressive_character_plan；不要生成完整角色卡，不要憑空定稿所有角色細節。"
    )
    
    user_content = f"""【已確定的核心世界觀設定】
{worldview_core_json}

【已確定的多幕式劇情結構】
{multi_act_json}

【使用者原始要求（參考）】
{user_prompt}

請根據上述設定，獨立規劃並生成群像劇的「角色漸進登場規劃策略（progressive_character_plan）」。
波次 title 必須嚴格統一為『第一波 (自擬登場群體或主題)』、『第二波 (自擬登場群體或主題)』等格式，使用中文數字編號，不允許出現『1.』、『1-0XX』、『Wave 1』等標號。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index):
    """角色設計師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("character")
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{CHARACTER_DESIGNER_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Character Designer / 角色設計師",
        "- 經後端挑選的世界觀背景，必須包含或摘要呈現 factions / 勢力設定與 progressive_character_plan / 角色登場策略。\n- generate 模式：通常只有世界觀，沒有現有角色；這是建立角色聖經與關係網的第一次定稿。\n- expand/modify 模式：會提供現有角色聖經與總監提示；modify 可能提供被修改角色完整內容。",
        "根據可見世界觀設計或修補角色 Bible。角色要服務於世界觀衝突、勢力格局、登場策略與作者需求；不得用空世界觀硬編角色。",
        "輸出完整合法的 characters JSON。generate 必須建立核心角色表、勢力歸屬、角色之間的關聯與可供卷/骨架/writer 使用的生成設定；expand/modify 應保留既有角色並補充或修正，避免刪除無關角色。"
    )
    
    if mode == "generate":
        user_content = f"""【世界觀背景】
{worldview_text}

【使用者要求】
{user_prompt or "請根據世界觀，為我們設計核心角色與配角群像。"}

請為本作品生成符合結構的角色 Bible JSON 設定。
硬性要求：
1. 必須讀取並落實世界觀中的 `factions` / 勢力設定，為主要角色標明所屬勢力、利益立場、與其他勢力的衝突或合作關係。
2. 必須讀取並落實 `progressive_character_plan` / 角色登場策略，讓角色功能、首次登場階段與群像節奏對齊。
3. 必須建立可供後續 volumes、volume_skeleton、writer 使用的角色關係資料，例如 relationships / relationship_matrix / role / faction / entry_phase 等 schema 允許欄位。
4. 不要只列人物簡介；每位核心角色都要有可寫作的動機、弱點、成長弧線、聲音/行為特徵與關係張力。
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

請根據總監提示，追加新角色。
[極重要要求]：
請只生成本次需要「新增/追加」的角色清單，並回傳格式完全合法的 characters JSON（例如 `{{ "characters": [...] }}`），列表中應「僅」包含本次新增的角色，千萬不要重寫、輸出或複製任何未修改的既有角色。
擴增角色時仍必須遵守世界觀勢力設定；新角色的 faction、登場功能與關係網必須能回接既有角色聖經，不能只新增孤立人物。
"""
    else:  # modify
        target_char_content = ""
        if target_char_index is not None:
            try:
                parsed_chars = json.loads(existing_chars_json)
                chars_list = parsed_chars.get("characters", [])
                norm_idx = db.normalize_char_index(int(target_char_index), len(chars_list), source='character_designer')
                target_char_content = f"\n【被修改角色的完整內容 (Index {norm_idx})】\n{json.dumps(chars_list[norm_idx], ensure_ascii=False, indent=2)}"
            except IndexError:
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

請將以上修改與該角色的完整內容融會貫通。
[極重要要求]：
請只生成「受修改後」的角色清單，並回傳格式完全合法的 characters JSON（例如 `{{ "characters": [...] }}`），列表中應「僅」包含本次被修改的角色的全新設定，千萬不要複製或重寫其他無關、未修改的角色。
修改時保留角色既有關係網與勢力一致性；若總監要求補關係或勢力，請同步修正 relationships / relationship_matrix 等相關欄位。
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_foreshadowing_messages(worldview_text, characters_json, user_prompt=None, target_field=None):
    """伏筆與轉折編織師提示詞拼接

    target_field: None = 兩者都生成（全量，每類至少50條）
                  "foreshadowing_seeds"   = 只生成伏筆種子（至少50條）
                  "key_turning_points"    = 只生成關鍵轉折點（至少50條）
    分批模式可顯著減少單次 JSON 長度，降低解析錯誤機率。
    """
    from backend.schemas.agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json

    if target_field == "foreshadowing_seeds":
        schema = {"foreshadowing_seeds": FORESHADOWING_OUTPUT_SCHEMA["foreshadowing_seeds"]}
        target_instruction = (
            "【本次只生成 foreshadowing_seeds】\n"
            "1. 最外層 JSON 只能有一個頂層鍵：`foreshadowing_seeds`（陣列）。\n"
            "2. 必須至少 50 個；少於此數量即為失敗輸出。\n"
            "3. 每個項目只能使用：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`。\n"
            "4. `id` 必須是整數，從 1 開始連續編號。\n"
            "5. 禁止輸出 key_turning_points 或任何其他頂層鍵。\n"
            "6. 每個 seed 必須具備可埋設的具體載體、表層偽裝與未來回收方向；不得用同義改寫湊數。"
        )
    elif target_field == "key_turning_points":
        schema = {"key_turning_points": FORESHADOWING_OUTPUT_SCHEMA["key_turning_points"]}
        target_instruction = (
            "【本次只生成 key_turning_points】\n"
            "1. 最外層 JSON 只能有一個頂層鍵：`key_turning_points`（陣列）。\n"
            "2. 必須至少 50 個；少於此數量即為失敗輸出。\n"
            "3. 每個項目只能使用：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。\n"
            "4. `id` 必須是整數，從 1 開始連續編號。\n"
            "5. 禁止輸出 foreshadowing_seeds 或任何其他頂層鍵。\n"
            "6. 每個 turning point 必須能造成局勢、關係或角色弧線的實質改變；不得用普通事件湊數。"
        )
    else:
        schema = FORESHADOWING_OUTPUT_SCHEMA
        target_instruction = (
            "【不可違反的輸出契約】\n"
            "1. 最外層 JSON 必須只有一個物件，且只能包含兩個頂層鍵：`foreshadowing_seeds` 與 `key_turning_points`。\n"
            "2. `foreshadowing_seeds` 必須是陣列，至少 50 個；`key_turning_points` 必須是陣列，至少 50 個；少於此數量即為失敗輸出。\n"
            "3. 每個 `foreshadowing_seeds` 項目只能使用這些欄位：`id`, `name`, `description`, `setup_hint`, `payoff_hint`, `related_characters`, `thematic_link`。\n"
            "4. 每個 `key_turning_points` 項目只能使用這些欄位：`id`, `turning_point_name`, `description`, `trigger_condition`, `structural_impact`, `emotional_stakes`, `related_characters`。\n"
            "5. `id` 必須是 JSON number / integer，從 1 開始連續編號；禁止填 `FS001`、`Seed-001`、`TP001`、`Turn-001`、中文標號或任何文字。\n"
            "6. 所有文字內容只能填入名稱、描述、提示、影響、代價、主題連結等文字欄位；禁止把情節文字、標號規則或說明塞入 `id`、`index`、`number` 類欄位。\n"
            "7. 禁止輸出 `volume_1`、`volume_2`、`act_1` 等作為頂層鍵；卷/幕/章節只能寫入文字欄位的內容裡。\n"
            "8. 此階段只生成全書伏筆與關鍵轉折藍圖，不需要章節正文、卷骨架，也不可要求 writer/editor 先執行。\n"
            "9. 每個 seed 必須具備可埋設的具體載體、表層偽裝與未來回收方向；不得用同義改寫湊數。\n"
            "10. 每個 turning point 必須能造成局勢、關係或角色弧線的實質改變；不得用普通事件湊數。"
        )

    schema_snippet = (
        format_json_schema_prompt(schema, label="this foreshadowing schema from backend/schemas/agent_json.py")
        + "\n"
        + agent_json.format_criteria_for_prompt("foreshadowing")
    )
    system_prompt = f"{FORESHADOWING_ORCHESTRATOR_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{target_instruction}\n\n{FORESHADOWING_ORCHESTRATOR_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Foreshadowing Orchestrator / 伏筆與轉折編織師",
        "- 經後端挑選的世界觀背景。\n- 角色 Bible 或角色摘要。\n- 總監可能透過 [BATCH: foreshadowing_seeds] 或 [BATCH: key_turning_points] 指定本批目標。",
        "只設計全書伏筆種子與關鍵轉折藍圖，供後續篇卷和章節分配使用。",
        "嚴格遵守本批 target_field 的頂層鍵；分批時不得混入另一類資料，不得輸出卷別鍵、章節正文或解釋文字。"
    )

    default_task = "請根據世界設定與角色背景，設計豐富的伏筆種子與關鍵轉折點。"
    user_content = (
        "【世界觀背景】\n" + worldview_text + "\n\n"
        "【角色 Bible 與人設】\n" + characters_json + "\n\n"
        "【額外設計指令】\n" + (user_prompt or default_task) + "\n\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx):
    """篇卷規劃師提示詞拼接"""
    schema_snippet = get_json_schema_prompt_snippet("volumes")
    system_prompt = f"{VOLUMES_PLANNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUMES_PLANNER_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volumes Planner / 篇卷規劃師",
        "- 經後端挑選的世界觀、macro_outline、多幕結構與必要設定。\n- patch 模式會提供目標卷前後卷概要與總監提示。",
        "只規劃全書卷列表或指定卷修補，讓每卷承接世界觀主軸與多幕起伏。",
        "輸出 volumes JSON；不要生成章節骨架、正文或角色卡。patch 模式只回傳指定卷，不要重寫其他卷。"
    )
    
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
    system_prompt = f"{VOLUME_SKELETON_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUME_SKELETON_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volume Skeleton Planner / 卷章節骨架規劃師",
        "- 經後端挑選的世界觀背景。\n- 指定卷的標題、概要、時間線、序列上下文、適用規則與完整章節範圍。\n- 相鄰卷/章節脈絡與 Python 預計算的逐章 allocated_tasks 表。",
        "一次生成本卷完整輕量章節骨架，並把預計算任務填入對應章節；不得自行切段或只輸出局部缺章。",
        "輸出 chapters_skeleton JSON；chapter_index 必須完整連續覆蓋指定整卷範圍。每章只寫短骨架，不得生成詳細大綱或正文。"
    )
    volume_context = {
        "volume_index": volume_index,
        "title": current_vol.get("title"),
        "summary": current_vol.get("summary"),
        "chapter_range": [start_ch, end_ch],
        "chapter_count": vol_chapter_count,
        "factions": current_vol.get("factions"),
        "time_timeline": current_vol.get("time_timeline"),
        "sequence_context": current_vol.get("sequence_context"),
        "applicable_rules": current_vol.get("applicable_rules"),
    }
    
    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務：整卷一次生成】
{json.dumps(volume_context, ensure_ascii=False, indent=2)}

請務必一次輸出第 {start_ch} 章至第 {end_ch} 章的完整「輕量章節骨架」（共 {vol_chapter_count} 章）。
不得切成多段，不得只輸出局部章節，不得要求總監補「本卷章節範圍」或「allocated_tasks」：這些資料已在本訊息中完整提供。
輸出完整性優先於細節量：每章請短，不要詳細。

{surrounding_context}
{precalc_clues}

【allocated_tasks 硬性填寫規則】
- 你不得自行挑選、推測、複製或新增任何伏筆 Seed / turning point 到未指定章節。
- 每一章都必須依「本卷逐章伏筆/轉折硬性操作表」填寫 allocated_tasks。
- 表中空陣列的章節必須輸出：foreshadowing_plants: [], foreshadowing_payoffs: [], turning_points: []。
- 若同一 Seed 看似同時需要埋設與回收，視為錯誤；請以章節清單中的單一操作為準。
- 若某章有 plant/payoff/turning point，該任務不能只放在 allocated_tasks；chapter_summary 或 events[0].content 必須用短句點出其劇情落點。

【每章輕量輸出格式限制】
- 不要寫正文、對白、心理描寫、詳細動作、感官描述、完整場景調度。
- 每章只需要點出：本章承接/推進、任務落點、時間、地點、活躍角色、相關勢力。
- events 僅 1 個核心事件物件；content 用「行動 -> 結果」短句，35 字內。
- chapter_summary 35-70 字；cliffhanger 30 字內；scene_setting/time_setting 都用短語。
- characters_active 只列本章真正活躍角色，通常 1-4 名。
- 若某章牽涉勢力，請放在 scene_setting、events.content 或 chapter_summary 的短句中；不要另寫長篇勢力說明。

【單章輸出長度範例（只示意格式，不可照抄內容）】
{{
  "chapter_index": {start_ch},
  "chapter_title": "月台異訊",
  "chapter_summary": "主角追查末班車異常，首次接觸乘客手冊線索，將危機推向車廂深處。",
  "time_setting": "深夜末班前",
  "scene_setting": "舊站月台",
  "events": [{{"scene_index": 1, "location": "舊站月台", "characters": ["主角"], "content": "追查異訊 -> 取得手冊線索"}}],
  "characters_active": ["主角"],
  "emotional_tone": "懸疑",
  "cliffhanger": "車門在無人處自行開啟。",
  "allocated_tasks": {{"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}}
}}

【勢力與角色一致性規則】
- 勢力/組織的定義、立場、利益、制度背景以【世界觀背景】中的 factions / 世界觀設定為準；本卷 factions 只是本卷活躍勢力子集，不得重新發明或改寫勢力設定。
- 若章節需要使用既有命名角色，characters_active 必須使用既有角色名冊中的名稱。
- 若劇情確實需要新增命名角色，可以在骨架中提出，但總監審核時必須先補角色卡再進入正文；不得把缺角色卡的命名角色當作已完備角色使用。

【使用者額外提示詞 (Prompt)】
{user_prompt or "請為本卷生成完整、連貫、短句化的輕量章節骨架。"}

請生成符合 JSON 結構的 chapters_skeleton 清單。輸出章數必須等於 {vol_chapter_count}，chapter_index 必須從 {start_ch} 到 {end_ch} 連續且不可缺漏。不要因追求細節導致輸出中斷。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volume_skeleton_completion_messages(
    worldview_text, volume_index, current_vol, start_ch, end_ch, batch_count,
    surrounding_context, precalc_clues, user_prompt, prior_segment_json
):
    """
    卷骨架「分段補全」提示詞拼接（completion 模式）。
    把已生成的前段章節成果（prior_segment_json 字串）放在 messages 中作為
    「已完成段落」，要求 LLM 只接續輸出剩餘章節 (start_ch ~ end_ch) 的骨架，
    銜接前段已有標題、情節、allocated_tasks，避免前後斷層。

    messages 結構刻意在最後放置一條 role=assistant 的「前段成果節錄」前綴，
    讓模型以續寫方式產出後半，達成真正的 completion 補全。
    """
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUME_SKELETON_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volume Skeleton Completion / 卷骨架補全師",
        "- 經後端挑選的世界觀背景。\n- 指定卷的標題、概要、已完成前段章節與本次補全範圍。\n- Python 預計算的 allocated_tasks。",
        "只接續前段，補全本次指定章節範圍；不得重寫已完成章節。",
        "輸出只包含補全範圍的 chapters_skeleton 元素；必須延續前段脈絡並保持 JSON 可解析。"
    )

    user_content = f"""【世界觀背景】
{worldview_text}

【當前特定篇卷任務 — 分段補全 (Completion)】
- 當前篇卷序號：第 {volume_index} 卷
- 篇卷標題：{current_vol['title']}
- 篇卷概要：{current_vol['summary']}
- 已完成前段：第 {start_ch - 1} 章及之前（請勿重寫此前段章節）
- 本次需補全章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {batch_count} 章）
請務必只輸出此補全範圍內的章節骨架；不得輸出範圍外章節，不得重寫前段已存在章節。

{surrounding_context}
{precalc_clues}

【前段已生成之章節骨架（務必延續其標題命名風格、情節脈絡、伏筆分配）】
{prior_segment_json}

以下為本次需補全章節的 allocated_tasks 硬性填寫規則：
- 你不得自行挑選、推測、複製或新增任何伏筆 Seed / turning point 到未指定章節。
- 只有上方清單明確列出的章節，才可在 allocated_tasks 對應陣列填入該任務。
- 未列出任務的章節必須輸出：foreshadowing_plants: [], foreshadowing_payoffs: [], turning_points: []。
- 補全章節須與前段情節自然銜接：延續前段 cliffhanger 的解決、角色行為因果、時間線連貫。

【使用者額外提示詞 (Prompt)】
{user_prompt or "請接續前段內容，為本卷剩餘章節補全骨架大綱。"}

請以 completion（續寫）方式，只輸出第 {start_ch} 章至第 {end_ch} 章的 chapters_skeleton JSON 陣列。輸出章數必須等於 {batch_count}，chapter_index 必須連續且不可缺漏。
"""
    # 為促成真正的 completion，把前段成果作為 assistant 前綴（role=assistant），
    # 讓模型以「自己先前已開始產出此 JSON」的續寫方式補完剩餘章節。
    # 注意：以下字串刻意不以 f-string 撰寫，避免 JSON 花括號被當成 f-string 表達式。
    assistant_intro = (
        "以下是第 " + str(volume_index) + " 卷前段已生成的章節骨架（請勿重複輸出，僅作為脈絡）：\n"
        "```json\n" + prior_segment_json + "\n```\n\n"
        "我現在接續輸出第 " + str(start_ch) + " 章至第 " + str(end_ch) + " 章的 chapters_skeleton：\n"
        "```json\n"
        '{"volume_index": ' + str(volume_index) + ', "chapters_skeleton": ['
    )
    assistant_follow = (
        "請接著上面已開始的 JSON 直接輸出 chapters_skeleton 陣列中的章節元素"
        "（第 " + str(start_ch) + " ~ " + str(end_ch) + " 章），"
        "然後以 ]}} 結束。只輸出尚未補完的章節，不要重複前段章節。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_intro},
        {"role": "user", "content": assistant_follow},
    ]
    return messages

def build_chapter_writer_messages(worldview_text, characters_bible, current_outline, surrounding_plot, vol_outline_context, clue_payoff_details, custom_style, chapter_index, user_prompt=None):
    """正文作家寫作提示詞拼接"""
    system_prompt = CHAPTER_WRITER_PROMPT + "\n" + CONTEXT_REQUEST_RULE + "\n\n" + CHAPTER_WRITER_GUIDELINES
    system_prompt += build_agent_context_contract(
        "Chapter Writer / 正文作家",
        "- 經後端挑選的世界觀背景，包含 factions / 勢力設定。\n- 本章大綱、前後章節脈絡、本卷概要、本卷活躍勢力與規則。\n- 本章命中的角色完整卡與其他角色基本關係。\n- 本章與附近章節的伏筆/轉折分配。",
        "只撰寫指定 chapter_index 的正式正文，嚴格落實本章大綱、已分配任務、角色卡與世界觀勢力設定。",
        "正式正文前必須輸出 [START_OF_PROSE]；不要改寫世界觀、角色 Bible、卷章大綱，不要輸出 JSON。"
    )
    
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

【勢力與角色一致性硬性規則】
- 勢力/組織描寫以世界觀 factions、世界觀背景與當前卷設定為準；不得臨時改寫勢力立場、制度、資源、敵友關係或名稱。
- 本卷 factions 代表本章可活躍的勢力範圍；若正文需要引入其他勢力，必須與世界觀既有設定相容，不能憑空新增制度背景。
- 本章命名角色必須依角色 Bible 行動、說話與做決策；若缺少角色卡，應回報上下文不足，不要硬寫。

請根據以上豐富的上下文細節，展開本章正文寫作；正文目標字數為 1500 至 2000 字左右，不要寫成摘要或短章。
【寫作風格基調】
{custom_style}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_editor_agent_messages(chapter_index, edit_instructions, original_prose):
    """編輯姬提示詞拼接"""
    system_prompt = EDITOR_PROMPT + "\n" + CONTEXT_REQUEST_RULE
    system_prompt += build_agent_context_contract(
        "Editor / 正文編輯",
        "- 指定章節的原始正文。\n- 精修指示或總監修改重點。",
        "只潤色、修補與提升指定章節正文；保留原章節核心事件、人物意圖與既有連續性。",
        "直接輸出精修後完整正文；不要輸出評語、JSON、世界觀修改或角色設定修改。"
    )
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
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or "未命名章節",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or "（尚無摘要說明）"
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
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or "未命名章節",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or "（尚無摘要說明）"
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
    
    from backend.services.diagnostics import diagnose_all_phases
    diags = diagnose_all_phases(novel_id)
    
    system_prompt = CO_PILOT_ORCHESTRATOR_PROMPT
    
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
- 已完稿正文：{diags["written_chapters"]}

【系統底層結構完整性與邏輯校驗報告】
{validation_report}

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
    """總監決策評判提示詞
    
    根據不同階段傳入對應的審查內容：
    - worldview: 完整世界觀內容 + 評斷提示詞
    - characters: 完整角色列表
    - volumes: 完整卷列表 + 世界觀的 macro_outline
    - volume_skeleton: 完整骨架(每2卷一組) + 世界觀的 macro_outline
    - writer: 該章的完整內容(正文+大綱+角色聖經+伏筆)
    - editor: 該章的完整潤色內容
    """
    from backend.services.diagnostics import diagnose_all_phases
    from backend import db
    diags = diagnose_all_phases(novel_id)
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
    from backend.schemas.agent_json import format_criteria_for_prompt
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

    director_input_policy = f"""

## Director 輸入與展開政策
1. 本輪輸入可能包含「硬指標計數」與「預設視圖」。硬指標由 Python 校驗報告直接計算；預設視圖只用於定位，不可把未展開項目當成已審查。
2. 對上一個 Agent 輸出先用 `TOOL_CALL evaluate_output` 做硬性檢查；該工具統一檢查 worldview、foreshadowing、characters、volumes、volume_skeleton、writer、editor。
3. 只要本階段包含長列表、完整角色表、卷骨架或正文，放行前都必須用工具展開檢閱內容品質；不能只因 Python 硬性校驗通過就 `CONTINUE`。
4. 若遇到前端回報的 system_event（錯誤、阻斷、索引缺失、執行失敗），請把它當作事實封包，根據 validation_report 與工具檢視結果決定下一步；前端不負責判斷流程。

{DIRECTOR_HARD_VALIDATION_POLICY}

{DIRECTOR_TOOL_CALL_CONTRACT}

{DIRECTOR_MANDATORY_INSPECTION_POLICY}
"""
                    
    # 總監評斷世界觀與進行伏筆審查時需要完整傳入，而其他階段已經通過審核，將其內部的伏筆與轉折欄位改為 "此區塊通過審核不需評判"
    if current_stage not in ("worldview", "foreshadowing"):
        worldview_text = mask_worldview_seeds_and_turns(worldview_text)

    # 根據 current_stage 構建不同的審查內容
    if current_stage == "worldview":
        # 世界觀階段：只傳世界觀完整內容 + 評斷提示詞
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前世界觀的創作質量，並決定下一步的最佳動作。
 
【審查原則與柔軟語調指南】
1. 當前階段是「current_stage = {current_stage}」（世界觀架構師）。
2. 請用溫和、細心且富有建設性的主編語氣提供反饋。不要使用冰冷或過於強硬的否定字眼，多用「建議您」、「如果能...會更加精彩」等口氣引導作者。
3. **【拆解評判要求】** 你必須單獨評估並在反饋中給出以下三個獨立區塊的詳細評判意見：
   - **核心世界觀設定**（主題深度、多陣營衝突、宏觀大綱）。
   - **🎭多幕式劇情起伏結構**（劇情起伏與功能）。
   - **👥角色漸進登場規劃策略**（人物登場波次與群像鋪陳）。
4. **【格式與 ID 的絕對強硬要求】** 
   - 幕次標題必須嚴格遵循『第一幕 (自擬階段名稱)』、『第二幕 (自擬階段名稱)』等標準命名格式。
   - 角色波次標題必須嚴格遵循『第一波 (自擬登場群體或主題)』、『第二波 (自擬登場群體或主題)』等標準命名格式。
   - **絕對禁止**出現『1.』、『1-01』、『1-0XX』等不一致或隨意的標號，這會影響後續與系統其他部分溝通參數的統一！
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""{worldview_user_prompt_section}
 
【完整世界觀設定（包含核心、多幕起伏結構與角色漸進規劃）】
{worldview_text}
 
請根據標準評估核心世界觀設定、多幕式結構、角色漸進登場規劃，並輸出下一步。
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
 
請根據標準評估並輸出下一步。
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
 
請根據標準評估並輸出下一步。
"""
    
    elif current_stage == "volume_skeleton":
        # 骨架階段：完整骨架 + 世界觀的 macro_outline + Python 分配表
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前卷骨架的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（篇卷骨架規劃師）。
2. 檢查骨架是否和該卷標題、概要、時間線、序列上下文與適用規則一致。
3. 檢查各章是否依「Python 預計算本卷伏筆/轉折分配表」自然埋設、回收或承載 turning point；沒有分配任務的章節不可要求硬塞伏筆。
4. 通過標準：劇情能完整根據該卷伏筆/轉折分配自然鋪陳與回收，章節之間沒有內容跳痛，角色行為與卷設定不衝突，即可放行。
5. 骨架階段只需輕量脈絡，不負責正文細節。若每章已點出承接/推進、時間、地點、活躍角色/勢力與 allocated_tasks 落點，不得因細節量少或場景未展開而退回；正文展開交給 writer。
6. 合理的非線性時間敘事可以接受，例如穿越、回憶、夢境、異界時間差或其他劇情設定明確支持的時間跳躍；不要只因時間不是線性遞進就退回。
7. 若需要繼續生成缺失卷，必須輸出 `CONTINUE` + `target: "volume_skeleton"` + 明確 `volume_index`，且 `agent_prompt` 必須要求一次生成該卷完整「輕量」章節骨架；不得輸出 SEGMENT_GENERATE、SEGMENT_COMPLETE 或要求分段生成。
8. 若骨架使用了角色 Bible 中不存在的命名角色，優先輸出 `INCREMENTAL_APPEND_CHARACTER` 補角色卡；補卡完成後再回到該卷骨架或原章節，不得跳到下一卷。
9. 勢力/組織設定以世界觀 factions 為準；若骨架中的勢力立場、制度、目標與世界觀不一致，指出具體不一致並要求修正，不要讓下游臨時改寫勢力設定。
 
{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""{default_user_prompt_section}
 
【世界觀的整體故事大綱 (macro_outline)】
{macro_outline}
 
【完整卷骨架列表（完整設定）】
{plot_text}
 
請根據標準評估並輸出下一步。
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
6. 但若正文或章節大綱使用了角色 Bible 中不存在的命名角色，必須先 `INCREMENTAL_APPEND_CHARACTER` 追加角色卡，再回到本章 writer；不得讓 writer 硬寫無角色卡人物。
7. 勢力/組織描寫必須以世界觀 factions 與當前卷 factions 為準；若正文把勢力立場、制度、敵友關係寫錯，應退回 writer 修正或回 worldview 修正源資料。

{stage_criteria}

{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""{default_user_prompt_section}

【世界觀背景】
{worldview_text}

【角色 Bible 聖經（命中角色完整設定；其他角色名稱與基本關係）】
{characters_text}

【當前章節大綱】
{plot_text}

【本章正文（完整內容）】
{written_chapters_text}

請根據標準評估並輸出下一步。
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
 
請根據標準評估並輸出下一步。
"""
    
    elif current_stage == "foreshadowing":
        # 伏筆審查階段
        system_prompt = f"""你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前伏筆與轉折點的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（伏筆與轉折編織師）。
2. 請核對「世界觀背景」以及「剛性校驗報告」。
3. 確認伏筆種子（foreshadowing_seeds）是否包含必要欄位，且數量是否達到 50 個。
4. 確認關鍵轉折點（key_turning_points）是否包含必要欄位，且數量是否達到 50 個。
5. **重要審查指引（分步展開審查）**：
   - 審查應分步進行（例如先確認伏筆種子，再確認轉折點）。
   - 你可以使用 `expand_collapsed_json` 工具來分頁展開查看資料庫中的完整伏筆列表。
   - 例如，你可以呼叫 `expand_collapsed_json` 展開 1~10，在下一輪呼叫展開 11~20，依此類推。
   - **檢查-1, 2, 3 的步驟狀態**：你必須在反饋中寫清楚目前是針對「Step 1: 伏筆種子 1-10 審查」、「Step 2: 伏筆種子 11-20 審查」還是「Step 3: 轉折點審查」等。
   - 如果某部分不合格，你可以使用 `supplement_content` 工具進行部分修改與補強。
   - 只有當伏筆種子與轉折點皆確認合格且數量足夠後，才能下達 `CONTINUE` 進入 `characters` 階段。

{stage_criteria}
 
{DIRECTOR_COMMON_FOOTER}
"""
        user_content = f"""{default_user_prompt_section}
 
【完整世界觀背景】
{worldview_text}
 
請根據標準評估並輸出下一步。
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
- 世界觀設定：{worldview_text if worldview_text else "（空）"}
- 角色設定：{characters_text if characters_text else "（空）"}
- 大綱設定：{plot_text if plot_text else "（空）"}
- 正文：{written_chapters_text if written_chapters_text else "（空）"}
 
請根據標準評估並輸出下一步。
"""
    
    system_prompt += director_input_policy

    if gold_rules_context:
        user_content += f"""

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
            user_content += f"\n\n💡【系統寫作計畫指引】：若本次審核放行並準備繼續正文寫作，系統建請下一章前往：第 {suggested_next_chapter} 章（這可能是一般的順序下一章，或是為了補齊斷檔/缺漏的章節）。請在輸出 JSON 決策時，優先將 `chapter_index` 設為 {suggested_next_chapter}，並將 `target` 設為 `writer`。\n"
        elif current_stage == "volume_skeleton":
            user_content += f"\n\n💡【系統寫作計畫指引】：若剛性校驗報告確認【所有卷】的骨架皆已完全生成且無缺漏，準備放行進入正文寫作階段時，系統建請從第 {suggested_next_chapter} 章開始寫作。請在決策放行且 target 為 writer 時，將 `chapter_index` 設為 {suggested_next_chapter}。\n"

    system_prompt += f"\n\n{DIRECTOR_CONTEXT_REQUEST_RULE}\n"
    
    last_run_block = ""
    last_run = db.get_last_agent_run(novel_id)
    if last_run:
        _last_input = last_run.get('input_data', '') or ''
        _last_output = last_run.get('output_data', '') or ''
        _last_stage = last_run.get('agent_name', '')
        _user_content_summary = ''
        try:
            _input_msgs = json.loads(_last_input) if _last_input else []
            if isinstance(_input_msgs, list):
                _user_parts = []
                for _m in _input_msgs:
                    if isinstance(_m, dict) and _m.get('role') == 'user':
                        _c = compact_context_text(_m.get('content') or '', 8000, "上一輪 Agent user input")
                        _user_parts.append(_c)
                _user_content_summary = '\n---\n'.join(_user_parts) if _user_parts else '(無 user 訊息)'
            else:
                _user_content_summary = compact_context_text(str(_input_msgs), 8000, "上一輪 Agent input")
        except Exception:
            _user_content_summary = compact_context_text(_last_input, 8000, "上一輪 Agent input")
        # 清理思考過程標記 (不放入思考)
        import re
        clean_last_output = re.sub(r"<think>.*?</think>", "", _last_output, flags=re.DOTALL).strip()
        # 一律使用收合函數：JSON list 欄位「前5項展示 + 其餘收合 + 工具指令」
        # 純文字輸出時自動 fallback 截斷 6000 字元
        _output_summary = collapse_json_output_for_director(
            clean_last_output,
            stage_name=_last_stage,
            preview_count=5
        )

        last_run_block = f"""

【上一個運行的 Agent 執行記錄 (Last Agent Run)】
- 階段名稱 (Stage)：{_last_stage}
- 該 Agent 接收到的使用者指示摘要 (User Content)：
{_user_content_summary}

- 該 Agent 產生的原始輸出內容 (Output)：
{_output_summary}
"""
        system_prompt += """
## ⚠️ 【上一個運行的 Agent 審核核對指令】 (🔥 核心職責)
你在進行本次評審時，請特別核對使用者內容中的【上一個運行的 Agent 執行記錄 (Last Agent Run)】。
1. 對比上個 Agent 接收到的輸入與指示，評審該 Agent 產生的原始輸出是否正確且完整地完成了要求。
2. 總監的判斷不應自己重組要求。如果該 Agent 的輸出已經正確完成了生成，沒有嚴重缺失，請放行前進。
3. 若該 Agent 的輸出有缺失、格式錯誤、欄位缺失或不足量，請在 JSON 決策中將其退回至該 Agent，並在 `reason` 與 `hint` 中明確指出其原始輸出的不足之處，供其重新生成。
"""

    system_prompt += """

## 檢查報告解讀規則
1. 「待生成」「待補」「佇列」「缺少章節」代表流程進度尚未完成，不等於上一輪 Agent 內容品質不合格。
2. 只有格式無法解析、必填欄位缺失、章節索引錯誤、allocated_tasks 與 Python 分配表不一致、角色/勢力設定明顯衝突，才屬於需要退回修正的內容問題。
3. 若報告同時列出多個未完成卷，請依報告中的「下一步建議」或最早未完整卷前進；不要因後續卷完全缺失而跳過較早的缺章卷。
4. 若上一輪輸出本身合格但全書仍有缺卷/缺章，請用 CONTINUE 派發下一個正確生成目標，不要把流程未完成寫成內容不合格或中止理由。
"""

    user_content += f"""

## 系統底層結構/進度檢查報告（Python 計算事實，請以此為準）
{validation_report}
"""
    
    if director_context_block:
        user_content += f"\n\n{director_context_block}"
        
    if last_run_block:
        user_content += f"\n\n{last_run_block}"

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
    system_prompt = f"""你是一位極度嚴格的小說創作總監。你剛剛調閱了完整的詳細板塊數據。
請在仔細審閱調閱數據後，給出最深刻、最犀利的洞察反饋，並決定下一步的實質決策 action (如 CONTINUE, GO_BACK_TO_SKELETON_EXPANSION, MODIFY_CURRENT_CHAPTER 等)。

請直接輸出【審閱反饋】，並在最後輸出 JSON 指令區塊。

{DIRECTOR_DECISION_KEY_CONTRACT}
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
    from backend.schemas.agent_json import FORESHADOWING_OUTPUT_SCHEMA
    import json
    
    if target_section == "foreshadowing_seeds":
        schema = {"foreshadowing_seeds": FORESHADOWING_OUTPUT_SCHEMA["foreshadowing_seeds"]}
        schema_snippet = format_json_schema_prompt(schema, label="this foreshadowing_seeds schema")
    elif target_section == "key_turning_points":
        schema = {"key_turning_points": FORESHADOWING_OUTPUT_SCHEMA["key_turning_points"]}
        schema_snippet = format_json_schema_prompt(schema, label="this key_turning_points schema")
    else:
        schema_snippet = get_json_schema_prompt_snippet("worldview")
        
    system_prompt = f"""你是一位精準的世界觀增量修正師。請根據用戶的修改要求，對現有的世界觀進行精準的局部修改或增量追加。
你只需要回傳【本次有新增或被修改的 {target_section}】的內容 JSON 區塊即可，後端會自動完成替換與合併。

{schema_snippet}
"""
    system_prompt += build_agent_context_contract(
        "Incremental Architect / 世界觀增量修正師",
        "- 現有世界觀全文或摘要。\n- 指定 target_section。\n- 使用者或總監的局部修改要求。",
        "只修改 target_section 對應內容；不要重建整個世界觀，除非 target_section 本身就是完整核心世界觀。",
        "只輸出本次新增或被修改的 JSON 區塊，讓後端合併；不要輸出解釋文字。"
    )
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
    schema_snippet = format_json_schema_prompt(patch_schema, label="this incremental character patch schema")
    
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
    system_prompt += build_agent_context_contract(
        "Incremental Character / 角色增量修正師",
        "- 現有世界觀摘要。\n- 現有角色聖經。\n- 若為修改，會提供目標角色或欄位；若為追加，會提供追加要求。",
        "只修補指定角色欄位、指定角色卡，或追加新角色；不要重寫整個角色庫。",
        "輸出增量 patch JSON。未修改欄位省略，避免覆蓋既有角色資料。"
    )
    
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
    schema_snippet = format_json_schema_prompt(patch_schema, label="this incremental skeleton patch schema")
    system_prompt = VOLUME_SKELETON_PROMPT_PLUS.format(hints=user_hint) + f"\n\n{schema_snippet}"
    system_prompt += build_agent_context_contract(
        "Incremental Skeleton / 卷骨架增量修正師",
        "- 世界觀摘要。\n- 指定卷索引。\n- 現有該卷章節骨架。\n- 總監或使用者的局部修改要求。",
        "只修補指定卷中被要求修改或補全的章節。",
        "輸出 chapters_skeleton patch JSON；每個回傳章節必須含 chapter_index。未修改章節不要回傳。"
    )
    
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


def build_missing_character_designer_messages(worldview_summary, existing_chars_json, new_char_name, chapter_outline):
    """
    為首次登場的缺失角色生成獨立設計提示詞訊息列表。
    此函數負責將角色設計 system prompt 與 user prompt 組裝為 LLM messages，
    按照嚴格 JSON Schema 要求生成新角色卡。
    """
    schema = {
        "name": "",
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

    # 僅提取現有角色的名稱與角色定位，節省 Token 並防範衝突
    existing_names_str = "暫無角色"
    if existing_chars_json:
        try:
            names = extract_character_names_list(existing_chars_json)
            if names:
                existing_names_str = ", ".join(names)
        except Exception:
            pass

    system_prompt = f"""你是一位頂尖的角色設計大師（Character Designer）。
請根據世界觀背景與新角色首次登場的章節骨架，為新登場的角色【{new_char_name}】設計一個具備深度與心理層次的角色卡設定。

⚠️【剛性約束項目】：
1. 輸出格式必須嚴格是 JSON，符合以下角色 Schema：
{STRICT_JSON_KEY_CONTRACT}
{json.dumps(schema, ensure_ascii=False, indent=2)}
2. name 欄位必須是角色的具體姓名【{new_char_name}】，絕對禁止填寫無關名稱。
3. 角色的人設、動機 (motivation)、致命缺陷 (fatal_flaw)、發聲風格 (speech_style) 必須與章節大綱的情境完全契合，且不可與現有的其他角色衝突。
"""
    system_prompt += build_agent_context_contract(
        "Missing Character Designer / 缺失角色補卡師",
        "- 世界觀背景大綱。\n- 既有角色名稱與定位清單。\n- 新角色首次登場的章節大綱。",
        "只為指定新角色生成一張可併入角色庫的角色卡，服務於其首次登場章節。",
        "輸出單一角色 JSON；name 必須等於指定新角色名稱，不得順手新增其他角色。"
    )
    user_content = f"""【世界觀背景大綱】
{worldview_summary}

【現有已登場角色清單 (避免人設重複或名稱衝突)】
{existing_names_str}

【新角色【{new_char_name}】登場的第 {chapter_outline.get('chapter_index')} 章大綱】
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

請為新角色【{new_char_name}】生成高品質的完整角色 JSON 卡片。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


def build_director_sub_agent_messages(
    agent_name: str,
    task_description: str,
    context: dict,
    retry_hint: str = None,
    retry_count: int = 1
) -> list:
    """
    為總監呼叫子代理人構建提示詞訊息
    """
    system_prompt = f"""你是一位負責執行具體寫作任務的專業子代理人（Sub-Agent: {agent_name}）。
你的任務是根據總監 Agent 下達的指令，完成特定章節或設定的生成/修改。

⚠️【剛性約束項目】：
1. 輸出格式必須嚴格是 JSON，使用 ```json ... ``` 包裹。
2. 必須完全遵守上下文中的世界觀設定與角色人設，禁止胡編亂造。
{STRICT_JSON_KEY_CONTRACT}
"""
    system_prompt += build_agent_context_contract(
        f"Director Sub-Agent / 總監子代理人 {agent_name}",
        "- 總監指派之生成任務。\n- 總監提供的 context 物件。\n- 可能包含上次錯誤與重試提示。",
        "只完成總監 task_description 指定的工作；不要自行擴大任務範圍。",
        "輸出 JSON，且必須能被後端解析。若 context 不足以完成，回傳 context request JSON。"
    )
    user_content = f"""【總監指派之生成任務】
{task_description}

【參考上下文 context】
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
    if retry_hint:
        user_content += f"\n\n【系統錯誤自癒回報 - 第 {retry_count} 次重試】\n上次生成失敗原因：{retry_hint}\n請針對此錯誤修正後重新輸出 JSON。"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


def build_supplement_messages(
    stage_name: str,
    original_output: str,
    evaluation_feedback: str,
    novel_id: str
) -> list:
    """
    為不合格的輸出進行補強生成或局部修正
    """
    system_prompt = f"""你是一位資深的內容編輯（Content Editor）。
你的任務是根據總監對當前階段【{stage_name}】的評判回饋，對先前生成的內容進行補強、修復與生成。

⚠️【剛性約束項目】：
1. 輸出格式必須嚴格是 JSON，使用 ```json ... ``` 包裹。
2. 請只針對缺失的欄位或不合格的部分進行增刪補強，確保最終輸出的 JSON 結構正確且內容符合評估要求。
{STRICT_JSON_KEY_CONTRACT}
"""
    system_prompt += build_agent_context_contract(
        "Supplement Content / 內容補強修正師",
        "- 原先生成內容。\n- 總監指出的不合格回饋與具體問題。\n- stage_name 決定應符合哪個階段 schema。",
        "只補強或修復不合格部分，保留原內容中已合格的設定與結構。",
        "輸出修正後完整且合法的 JSON；不要輸出與 schema 無關的說明。"
    )
    user_content = f"""【原先生成的內容】
{original_output}

【總監評估之不合格回饋與問題】
{evaluation_feedback}

請根據以上回饋，修正並補強上述內容，重新生成一份完整且合格的 JSON 輸出。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


