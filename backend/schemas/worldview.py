# -*- coding: utf-8 -*-
"""Worldview parsing and schema validation helpers.

This module is intentionally storage-free. It normalizes LLM/text worldview
content into the JSON shape used by the rest of the backend.
"""

import json
import re

from backend.schemas.agent_json import WORLDVIEW_REQUIRED_FIELDS, WORLDVIEW_RECOMMENDED_FIELDS


DEFAULT_WORLDVIEW_STRUCTURE = {
    "theme": "",
    "main_conflict": "",
    "worldview": "",
    "macro_outline": "",
    "multi_act_structure": [
        {"title": "第一幕 (Setup)", "content": ""},
        {"title": "第二幕 (Confrontation)", "content": ""},
        {"title": "第三幕 (Resolution)", "content": ""},
    ],
    "progressive_character_plan": [
        {"title": "第一波開篇 (Wave 1)", "content": ""},
        {"title": "第二波發展 (Wave 2)", "content": ""},
        {"title": "第三波高潮 (Wave 3)", "content": ""},
    ],
    "foreshadowing_seeds": [],
    "key_turning_points": [],
}


def _default_worldview():
    return json.loads(json.dumps(DEFAULT_WORLDVIEW_STRUCTURE, ensure_ascii=False))


def _normalize_list_items(value, default_items, fallback_label):
    normalized = []
    if isinstance(value, list):
        for idx, item in enumerate(value):
            if isinstance(item, dict):
                normalized.append({
                    "title": item.get("title", f"{fallback_label} #{idx + 1}"),
                    "content": item.get("content", ""),
                })
            else:
                normalized.append({
                    "title": f"{fallback_label} #{idx + 1}",
                    "content": str(item),
                })
        return normalized
    if isinstance(value, dict):
        return None
    return default_items


def _extract_jsonish_text(content):
    content_stripped = content.strip()
    if "```" not in content_stripped:
        return content_stripped
    cleaned = re.sub(r"<think>.*?</think>", "", content_stripped, flags=re.DOTALL).strip()
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1:
        return cleaned[first_brace:last_brace + 1].strip()
    return content_stripped


def parse_worldview_to_json(content):
    if not content:
        return _default_worldview()

    if isinstance(content, dict):
        parsed = content
        content_text = json.dumps(content, ensure_ascii=False)
    else:
        content_text = str(content)
        if "\n\n【全域" in content_text:
            content_text = content_text.split("\n\n【全域")[0]
        content_stripped = _extract_jsonish_text(content_text)
        if content_stripped.startswith("{") and content_stripped.endswith("}"):
            try:
                parsed = json.loads(content_stripped)
            except Exception as exc:
                print(f"[WARN] parse_worldview_to_json JSON load failed: {exc}. Falling back to text parser.")
                parsed = None
        else:
            parsed = None

    if isinstance(parsed, dict):
        default = _default_worldview()
        ta = parsed.get("multi_act_structure", [])
        normalized_ta = _normalize_list_items(ta, default["multi_act_structure"], "項目")
        if normalized_ta is None:
            normalized_ta = [
                {"title": "第一幕 (Setup)", "content": ta.get("act1_setup", ta.get("act1", ""))},
                {"title": "第二幕 (Confrontation)", "content": ta.get("act2_confrontation", ta.get("act2", ""))},
                {"title": "第三幕 (Resolution)", "content": ta.get("act3_resolution", ta.get("act3", ""))},
            ]

        cp = parsed.get("progressive_character_plan", [])
        normalized_cp = _normalize_list_items(cp, default["progressive_character_plan"], "階段")
        if normalized_cp is None:
            normalized_cp = [
                {"title": "第一波開篇 (Wave 1)", "content": cp.get("wave_1_opening", "")},
                {"title": "第二波發展 (Wave 2)", "content": cp.get("wave_2_development", "")},
                {"title": "第三波高潮 (Wave 3)", "content": cp.get("wave_3_climax", "")},
            ]

        result_obj = parsed.copy()
        result_obj.update({
            "theme": parsed.get("theme", ""),
            "main_conflict": parsed.get("main_conflict", ""),
            "worldview": parsed.get("worldview", ""),
            "macro_outline": parsed.get("macro_outline", ""),
            "multi_act_structure": normalized_ta,
            "progressive_character_plan": normalized_cp,
            "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []) if isinstance(parsed.get("foreshadowing_seeds"), list) else [],
            "key_turning_points": parsed.get("key_turning_points", []) if isinstance(parsed.get("key_turning_points"), list) else [],
        })
        return result_obj

    return parse_worldview_sections(content_text)


def parse_worldview_sections(content):
    result = _default_worldview()
    headers = [
        "【核心主題】",
        "【核心衝突】",
        "【世界觀設定】",
        "【整體故事大綱】",
        "【多幕式結構】",
        "【角色漸進規劃策略】",
        "【伏筆種子】",
        "【關鍵轉折點】",
    ]

    pos = []
    for header in headers:
        idx = content.find(header)
        if idx != -1:
            pos.append((idx, header))
    pos.sort()

    sections = {}
    for idx, (_, header) in enumerate(pos):
        start_idx = pos[idx][0] + len(header)
        end_idx = pos[idx + 1][0] if idx + 1 < len(pos) else len(content)
        sections[header] = content[start_idx:end_idx].strip()

    result["theme"] = sections.get("【核心主題】", result["theme"])
    result["main_conflict"] = sections.get("【核心衝突】", result["main_conflict"])
    result["worldview"] = sections.get("【世界觀設定】", result["worldview"])
    result["macro_outline"] = sections.get("【整體故事大綱】", result["macro_outline"])

    if "【多幕式結構】" in sections:
        parsed_ta = _parse_bulleted_section(sections["【多幕式結構】"], "項目")
        if parsed_ta:
            result["multi_act_structure"] = parsed_ta

    if "【角色漸進規劃策略】" in sections:
        parsed_cp = _parse_bulleted_section(sections["【角色漸進規劃策略】"], "階段")
        if parsed_cp:
            result["progressive_character_plan"] = parsed_cp

    if "【伏筆種子】" in sections:
        result["foreshadowing_seeds"] = _parse_line_list(sections["【伏筆種子】"])

    if "【關鍵轉折點】" in sections:
        result["key_turning_points"] = _parse_line_list(sections["【關鍵轉折點】"])

    return result


def _parse_bulleted_section(text, fallback_label):
    parsed = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        clean_line = line[1:].strip() if line.startswith(("-", "•", "*")) else line
        if "：" in clean_line or ":" in clean_line:
            sep = "：" if "：" in clean_line else ":"
            title, content_text = clean_line.split(sep, 1)
            parsed.append({"title": title.strip(), "content": content_text.strip()})
        else:
            parsed.append({"title": f"{fallback_label} #{len(parsed) + 1}", "content": clean_line})
    return parsed


def _parse_line_list(text):
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(("•", "-", "*")):
            line = line[1:].strip()
        if line:
            items.append(line)
    return items


def validate_worldview_schema(content):
    errors = []
    warnings = []
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = parse_worldview_to_json(content)
        except Exception:
            parsed = None

    if not isinstance(parsed, dict):
        text_lower = content.lower() if isinstance(content, str) else ""
        title_match = any(k in text_lower for k in ["title", "標題", "書名", "主題", "theme"])
        if not title_match:
            errors.append("無法解析為結構化世界觀，且未包含必要識別欄位")
        return len(errors) == 0, errors, warnings

    for field in WORLDVIEW_REQUIRED_FIELDS:
        if field not in parsed or parsed[field] in (None, "", [], {}):
            errors.append(f"缺少必要欄位: {field}")
    for field in WORLDVIEW_RECOMMENDED_FIELDS:
        if field not in parsed or parsed[field] in (None, "", [], {}):
            warnings.append(f"建議補充欄位: {field}")
    return len(errors) == 0, errors, warnings
