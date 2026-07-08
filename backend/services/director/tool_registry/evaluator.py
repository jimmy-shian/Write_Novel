# -*- coding: utf-8 -*-
import json
from typing import List, Dict, Any

from backend import persistence as db
from backend.schemas.agent_json import APPROVAL_CRITERIA_REGISTRY, format_criteria_for_prompt
from backend.schemas.validation import (
    foreshadowing_quantity_error,
    foreshadowing_schema_error,
    volume_plan_validation_error,
)
from backend.common.config import MIN_VOLUME_COUNT, MAX_VOLUME_COUNT
from backend.models.parsers import extract_json_block

def _non_empty_text(value: Any, min_len: int = 1) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) >= min_len
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, (list, dict)):
        return bool(value)
    return len(str(value).strip()) >= min_len

def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False).strip()
    except Exception:
        return str(value).strip()

def _append_limited_issue(issues: List[str], message: str, limit: int = 20) -> None:
    if len(issues) < limit:
        issues.append(message)

def _as_characters_list(parsed: Any) -> List[dict]:
    if isinstance(parsed, dict):
        chars = parsed.get("characters")
        if isinstance(chars, list):
            return chars
    if isinstance(parsed, list):
        return parsed
    return []

def _is_primary_protagonist(character, index):
    if index == 0:
        return True
    role = str(character.get("role", "")).lower()
    tags = character.get("tags", []) or character.get("labels", [])
    if isinstance(tags, str):
        tags = [tags]
    tag_text = " ".join(str(tag).lower() for tag in tags)
    return any(mark in role or mark in tag_text for mark in ("主角", "protagonist", "男主", "女主"))

def _validate_characters(parsed: Any, novel_id: str = "") -> List[str]:
    issues: List[str] = []
    characters = _as_characters_list(parsed)
    if not characters:
        return ["未輸出 characters 陣列"]

    required_protagonist = [
        "name", "role", "entry_phase", "personality", "want", "need",
        "fatal_flaw", "want_need_conflict", "secret", "motivation",
        "arc", "speech_style", "background", "relationships",
        "relationship_matrix",
    ]
    required_minor = ["name", "role", "entry_phase"]
    placeholder_names = {"待補充", "暫無", "placeholder", "新角色", "路人", "角色名稱"}

    for idx, char in enumerate(characters):
        if not isinstance(char, dict):
            _append_limited_issue(issues, f"characters[{idx}] 必須是物件")
            continue
        
        name = _text_value(char.get("name"))
        if not name or name.lower() in placeholder_names or any(token in name for token in ("CEO", "研究員", "士兵", "路人")):
            _append_limited_issue(issues, f"characters[{idx}].name 必須是具體姓名或代號，不可為空或使用職位、占位名稱")

        is_proto = _is_primary_protagonist(char, idx)
        check_fields = required_protagonist if is_proto else required_minor
        
        for field in check_fields:
            if not _non_empty_text(char.get(field)):
                _append_limited_issue(issues, f"characters[{idx}].{field} 不可為空" + ("（主角必填）" if is_proto else ""))

        if is_proto:
            for field, min_len in (
                ("want", 20),
                ("need", 20),
                ("fatal_flaw", 15),
                ("want_need_conflict", 30),
                ("secret", 20),
                ("arc", 30),
                ("speech_style", 15),
            ):
                if len(_text_value(char.get(field))) < min_len:
                    _append_limited_issue(issues, f"characters[{idx}].{field} 內容過短（主角必填，需至少 {min_len} 字）")
            if not isinstance(char.get("relationships"), list):
                _append_limited_issue(issues, f"characters[{idx}].relationships 必須是陣列")
            if not isinstance(char.get("relationship_matrix"), list):
                _append_limited_issue(issues, f"characters[{idx}].relationship_matrix 必須是陣列")

    return issues

def _as_volumes_list(parsed: Any) -> List[dict]:
    if isinstance(parsed, dict):
        vols = parsed.get("volumes")
        if isinstance(vols, list):
            return vols
    if isinstance(parsed, list):
        return parsed
    return []

def _as_skeleton_chapters(parsed: Any) -> List[dict]:
    if isinstance(parsed, dict):
        for key in ("chapters_skeleton", "chapters_outline", "chapters"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
        vols = parsed.get("volumes")
        if isinstance(vols, list):
            chapters: List[dict] = []
            for vol in vols:
                if isinstance(vol, dict):
                    value = vol.get("chapters_skeleton") or vol.get("chapters_outline") or vol.get("chapters")
                    if isinstance(value, list):
                        chapters.extend(value)
            return chapters
    if isinstance(parsed, list):
        return parsed
    return []

def _validate_volume_skeleton(parsed: Any) -> List[str]:
    issues: List[str] = []
    chapters = _as_skeleton_chapters(parsed)
    if not chapters:
        return ["未輸出 chapters_skeleton / chapters_outline 陣列"]

    required = [
        "chapter_index", "chapter_title", "chapter_summary", "events",
        "time_setting", "scene_setting", "characters_active",
        "emotional_tone", "cliffhanger", "allocated_tasks",
    ]
    indexes: List[int] = []

    for idx, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            _append_limited_issue(issues, f"chapters[{idx}] 必須是物件")
            continue
        for field in required:
            if not _non_empty_text(chapter.get(field)):
                _append_limited_issue(issues, f"chapters[{idx}].{field} 不可為空")
        try:
            indexes.append(int(chapter.get("chapter_index")))
        except Exception:
            _append_limited_issue(issues, f"chapters[{idx}].chapter_index 必須是整數")

        events = chapter.get("events")
        if not isinstance(events, list):
            _append_limited_issue(issues, f"chapters[{idx}].events 必須是陣列")
        elif len(events) > 2:
            _append_limited_issue(issues, f"chapters[{idx}].events 應保持輕量，不可超過 2 個核心事件")
        else:
            for event_idx, event in enumerate(events):
                if not isinstance(event, dict):
                    _append_limited_issue(issues, f"chapters[{idx}].events[{event_idx}] 必須是物件")
                    continue
                for field in ("scene_index", "location", "characters", "content"):
                    if not _non_empty_text(event.get(field)):
                        _append_limited_issue(issues, f"chapters[{idx}].events[{event_idx}].{field} 不可為空")
                content = _text_value(event.get("content"))
                if len(content) > 80:
                    _append_limited_issue(issues, f"chapters[{idx}].events[{event_idx}].content 過長；骨架只需短句")

        allocated = chapter.get("allocated_tasks")
        if not isinstance(allocated, dict):
            _append_limited_issue(issues, f"chapters[{idx}].allocated_tasks 必須是物件")
        else:
            for field in ("foreshadowing_plants", "foreshadowing_payoffs", "turning_points"):
                if field not in allocated or not isinstance(allocated.get(field), list):
                    _append_limited_issue(issues, f"chapters[{idx}].allocated_tasks.{field} 必須是陣列")

    if indexes:
        if len(indexes) != len(set(indexes)):
            _append_limited_issue(issues, "chapter_index 不可重複")
        sorted_indexes = sorted(indexes)
        expected = list(range(sorted_indexes[0], sorted_indexes[-1] + 1))
        if sorted_indexes != expected:
            _append_limited_issue(issues, "chapter_index 必須連續，不可缺漏")

    return issues

def _content_from_writer_like_output(parsed: Any, output_content: str) -> tuple[str, dict]:
    if isinstance(parsed, dict) and parsed:
        content = parsed.get("content") or parsed.get("text") or ""
        return _text_value(content), parsed
    text = output_content or ""
    if "[START_OF_PROSE]" in text:
        text = text.split("[START_OF_PROSE]", 1)[1]
    return text.strip(), {}

def _validate_writer_like(parsed: Any, output_content: str, stage_name: str) -> List[str]:
    issues: List[str] = []
    content, data = _content_from_writer_like_output(parsed, output_content)
    min_len = 1500 if stage_name == "writer" else 1000

    if not content:
        issues.append("content 不可為空")
        return issues
    if len(content) < min_len:
        issues.append(f"content 長度不足：至少 {min_len} 字，實際 {len(content)} 字")

    if data:
        for field in ("novel_id", "chapter_index", "synopsis"):
            if not _non_empty_text(data.get(field)):
                _append_limited_issue(issues, f"{field} 不可為空")
        if data.get("chapter_index") is not None:
            try:
                int(data.get("chapter_index"))
            except Exception:
                _append_limited_issue(issues, "chapter_index 必須是整數")

    blocked_markers = ("[正文開始]", "請在此", "待補充", "lorem ipsum", "placeholder")
    lowered = content.lower()
    for marker in blocked_markers:
        if marker.lower() in lowered:
            _append_limited_issue(issues, f"content 含占位或系統標記：{marker}")

    return issues

def _latest_stage_output_for_evaluation(stage_name: str, novel_id: str) -> str:
    stage = (stage_name or "").strip()
    if not novel_id:
        return ""
    if stage in ("worldview", "foreshadowing"):
        wb = db.get_latest_worldbuilding(novel_id)
        return wb["content"] if wb else ""
    if stage == "characters":
        char = db.get_latest_characters(novel_id)
        if not char:
            return ""
        return char.get("json_data") or json.dumps(char.get("parsed_data") or {}, ensure_ascii=False)
    if stage in ("volumes", "volume_skeleton"):
        return json.dumps({"volumes": db.get_volumes(novel_id)}, ensure_ascii=False, indent=2)
    if stage in ("writer", "editor"):
        chapter = db.get_latest_chapter(novel_id, 1)
        return chapter.get("content", "") if chapter else ""
    return ""

def evaluate_output(stage_name: str, output_content: str = "", novel_id: str = "") -> Dict[str, Any]:
    """
    [Tool 2] 評斷代理人的輸出結果
    透過 APPROVAL_CRITERIA_REGISTRY 進行硬性校驗
    """
    criteria = APPROVAL_CRITERIA_REGISTRY.get(stage_name)
    if not criteria:
        return {"passed": True, "message": "無該階段標準，視為通過", "issues": []}

    issues = []
    output_content = output_content or _latest_stage_output_for_evaluation(stage_name, novel_id)
    parsed = extract_json_block(output_content)

    if stage_name == "foreshadowing":
        if isinstance(parsed, dict):
            seeds = parsed.get("foreshadowing_seeds") or parsed.get("seeds") or parsed.get("foreshadowings") or []
            turns = parsed.get("key_turning_points") or parsed.get("turning_points") or parsed.get("twists") or []
        else:
            seeds = []
            turns = []
        if isinstance(seeds, dict):
            seeds = [seeds]
        if isinstance(turns, dict):
            turns = [turns]
        if not isinstance(seeds, list):
            seeds = []
        if not isinstance(turns, list):
            turns = []
        q_err = foreshadowing_quantity_error(seeds, turns)
        if q_err:
            issues.append(q_err)
        s_err = foreshadowing_schema_error(seeds, turns)
        if s_err:
            issues.append(s_err)

    elif stage_name == "volumes":
        vols = _as_volumes_list(parsed)
        v_err = volume_plan_validation_error(vols, mode="generate")
        if v_err:
            issues.append(v_err)
        else:
            volume_indexes = []
            for i, vol in enumerate(vols):
                if not isinstance(vol, dict):
                    _append_limited_issue(issues, f"volumes[{i}] 必須是物件")
                    continue
                for field in ("volume_index", "title", "summary", "chapter_count", "factions", "time_timeline", "sequence_context", "applicable_rules"):
                    if not _non_empty_text(vol.get(field)):
                        _append_limited_issue(issues, f"volumes[{i}].{field} 不可為空")
                try:
                    volume_indexes.append(int(vol.get("volume_index")))
                except Exception:
                    _append_limited_issue(issues, f"volumes[{i}].volume_index 必須是整數")
            if volume_indexes:
                expected = list(range(1, len(volume_indexes) + 1))
                if sorted(volume_indexes) != expected and MIN_VOLUME_COUNT <= len(vols) <= MAX_VOLUME_COUNT:
                    _append_limited_issue(issues, "volume_index 必須從 1 開始連續")

    elif stage_name == "worldview":
        if isinstance(parsed, dict):
            required = ["theme", "main_conflict", "worldview", "macro_outline"]
            for field in required:
                if not parsed.get(field):
                    issues.append(f"缺少必填欄位: {field}")
        else:
            issues.append("worldview 輸出必須是 JSON object")

    elif stage_name == "characters":
        issues.extend(_validate_characters(parsed, novel_id=novel_id))

    elif stage_name == "volume_skeleton":
        issues.extend(_validate_volume_skeleton(parsed))

    elif stage_name in ("writer", "editor"):
        issues.extend(_validate_writer_like(parsed, output_content, stage_name))

    criteria_prompt = format_criteria_for_prompt(stage_name)

    return {
        "passed": len(issues) == 0,
        "message": "通過" if len(issues) == 0 else "; ".join(issues),
        "issues": issues,
        "criteria_reference": criteria_prompt,
    }
