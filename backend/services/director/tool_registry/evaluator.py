# -*- coding: utf-8 -*-
import json
from typing import List, Dict, Any, Optional

from backend import persistence as db
from backend.common.config import MIN_COMPLETE_CHAPTER_LENGTH, MIN_WRITER_DRAFT_LENGTH
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

def _chapter_climax_stats(chapters: List[dict]) -> Dict[str, Any]:
    """統計卷級骨架中的高潮章，保留舊版只使用 scene_function 的相容性。"""
    climax_indexes: List[int] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter_type = str(chapter.get("chapter_type") or "").strip().lower()
        scene_function = str(chapter.get("scene_function") or "").strip().lower()
        if chapter_type in {"climax", "finale", "高潮", "高潮章", "終局", "終章"} or scene_function in {"climax", "高潮", "終局"}:
            try:
                climax_indexes.append(int(chapter.get("chapter_index")))
            except (TypeError, ValueError):
                continue
    return {
        "total_chapters": len(chapters),
        "climax_count": len(climax_indexes),
        "climax_chapter_indexes": sorted(set(climax_indexes)),
    }

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

        # 新欄位採 optional 相容驗證，避免舊版骨架因缺欄位被退回。
        if "chapter_type" in chapter and not _non_empty_text(chapter.get("chapter_type")):
            _append_limited_issue(issues, f"chapters[{idx}].chapter_type 若提供則不可為空")
        if "must_happen" in chapter and not isinstance(chapter.get("must_happen"), list):
            _append_limited_issue(issues, f"chapters[{idx}].must_happen 若提供則必須是陣列")
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


def _scene_setting_keywords(value: Any) -> set[str]:
    """從 scene_setting 萃取可在正文首段比對的純文字關鍵詞。"""
    import re

    if isinstance(value, dict):
        parts = [_scene_setting_keywords(item) for item in value.values()]
        return set().union(*parts) if parts else set()
    if isinstance(value, (list, tuple, set)):
        parts = [_scene_setting_keywords(item) for item in value]
        return set().union(*parts) if parts else set()

    text = str(value or "").strip().lower()
    if not text:
        return set()
    keywords: set[str] = set()
    for token in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text):
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            if len(token) >= 2:
                keywords.add(token)
        else:
            keywords.add(token)
    return keywords

def _validate_writer_like(parsed: Any, output_content: str, stage_name: str) -> List[str]:
    issues: List[str] = []
    content, data = _content_from_writer_like_output(parsed, output_content)
    # Writer is checked as an editable story draft; Editor owns the complete-chapter floor.
    min_len = MIN_WRITER_DRAFT_LENGTH if stage_name == "writer" else MIN_COMPLETE_CHAPTER_LENGTH

    if not content:
        issues.append("content 不可為空")
        return issues

    from backend.common.refusal_filter import is_refusal_or_disclaimer
    if is_refusal_or_disclaimer(content):
        issues.append("content 包含 AI 拒答或安全免責聲明標記")

    from backend.common.refusal_filter import find_meta_narrative_leaks
    for leak in find_meta_narrative_leaks(content):
        issues.append(f"content 包含元敘事／寫作指令洩漏：{leak}")

    if len(content) < min_len:
        issues.append(f"content 長度不足：至少 {min_len} 字，實際 {len(content)} 字")

    if data:
        # Synopsis is derived and persisted by the chapter pipeline; it's only
        # a required output field for schemas that explicitly include it.
        required_fields = ["novel_id", "chapter_index"]
        if "synopsis" in data:
            required_fields.append("synopsis")
        for field in required_fields:
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

def _validate_chapter_setting_and_continuity(
    content: str,
    outline: Optional[Dict[str, Any]],
    novel_id: str,
    chapter_index: int,
) -> List[str]:
    """檢驗章節正文是否違反大綱之場景地點、時間流向或開篇定型去重禁令"""
    issues: List[str] = []
    if not content or not outline:
        return issues

    first_paragraph = content.strip().split("\n")[0] if content else ""
    first_500 = content[:500]

    # 1. 地點一致性校驗（三層判定：房號/強地標為 critical，純氣氛詞為 warning）
    scene_setting = outline.get("scene_setting") or outline.get("location") or ""
    if scene_setting:
        import re
        scene_text = _text_value(scene_setting)

        # scene_setting 常把主場景與鄰接目的地寫成一整句，例如
        #「地下黑市貨運專列與通往議會大廈的地下卸貨站」。
        # 只把第一個場景錨點當成開篇必須命中的地點，不能要求整句逐字出現。
        if isinstance(scene_setting, dict):
            scene_anchor = scene_setting.get("location") or scene_setting.get("place") or scene_text
        elif isinstance(scene_setting, str):
            scene_parts = [
                part.strip()
                for part in re.split(r"[，,；;。]|以及|與|及|並且|通往|通向|連接到|連往", scene_setting)
                if part.strip()
            ]
            scene_anchor = scene_parts[0] if scene_parts else scene_setting
        else:
            scene_anchor = scene_setting

        # 1.1 優先檢查明確房號、建築編號等強特徵
        room_match = re.search(r'(\d{3,4})\s*[室號房]', scene_text)
        if room_match:
            expected_room = room_match.group(1)
            actual_rooms = re.findall(r'(\d{3,4})\s*[室號房]', first_500)
            if actual_rooms and expected_room not in actual_rooms:
                issues.append(f"【場景地點漂移】大綱指定房號為「{expected_room}室」，正文開篇卻寫作「{actual_rooms[0]}室/房」")

        # 1.2 萃取強關鍵詞 vs 氛圍詞
        STRONG_LOC_SUFFIXES = (
            "室", "房", "館", "站", "殿", "閣", "峰", "山", "寺", "樓",
            "莊", "院", "宮", "城", "港", "洞", "林", "谷", "塔", "府",
            "局", "基地", "大樓", "公司", "辦公室", "會議室", "實驗室",
            "牢房", "地牢", "酒館", "客棧", "別墅", "公寓", "校園", "學院", "教室", "病房", "醫院"
        )
        keywords = _scene_setting_keywords(scene_anchor)
        if keywords:
            strong_keywords = {
                kw for kw in keywords
                if any(kw.endswith(suf) for suf in STRONG_LOC_SUFFIXES) or re.search(r"\d+", kw)
            }
            # 如果大綱含有明確地點名稱或強關鍵詞
            explicit_loc = outline.get("location") if isinstance(outline.get("location"), str) else ""
            if explicit_loc and len(explicit_loc.strip()) >= 2:
                strong_keywords.add(explicit_loc.strip())

            if strong_keywords:
                matched_strong = {kw for kw in strong_keywords if kw in first_500.lower()}
                # 明確地點完全不符時才判定為 critical
                if not matched_strong and not any(kw in first_paragraph.lower() for kw in strong_keywords):
                    issues.append(
                        f"【場景地點漂移】大綱指定場景核心地點/地標「{', '.join(list(strong_keywords)[:2])}」未在開篇呈現，疑似場景漂移"
                    )
            else:
                # 主場景錨點已出現在開篇時，鄰接地點、目的地或附加氛圍不應造成退回。
                matched_anchor = {kw for kw in keywords if kw in first_500.lower()}
                if not matched_anchor:
                    # 無法辨識明確地標時，才用完整描述檢查氛圍提示。
                    if isinstance(scene_setting, str):
                        scene_parts = [
                            part.strip()
                            for part in re.split(r"[，,；;。]|以及|與|及|並且|通往|通向|連接到|連往", scene_setting)
                            if part.strip()
                        ]
                    else:
                        scene_parts = [scene_setting]
                    all_keywords = set().union(*(_scene_setting_keywords(part) for part in scene_parts)) if scene_parts else set()
                    matched_all = {kw for kw in all_keywords if kw in first_500.lower()}
                    matched_para = {kw for kw in all_keywords if kw in first_paragraph.lower()}
                    if not matched_all:
                        issues.append(
                            "【場景氛圍提醒】大綱場景氛圍描繪未在正文開篇呈現，建議潤色時適度補充環境感官描寫"
                        )
                    elif all_keywords and len(matched_para) / len(all_keywords) < 0.3:
                        issues.append(
                            "【場景細節提醒】大綱場景長描述部分元素未在首段呈現，建議潤色時增強環境細節"
                        )

    # 2. 時間流向與開篇去重校驗
    time_setting = outline.get("time_setting") or ""
    if chapter_index > 1 and novel_id:
        try:
            prev_ch = db.get_chapter(novel_id, chapter_index - 1)
            if prev_ch and prev_ch.get("content"):
                prev_text = prev_ch["content"].strip()
                prev_first_line = prev_text.split("\n")[0].strip() if prev_text else ""

                if len(first_paragraph) >= 15 and len(prev_first_line) >= 15:
                    if first_paragraph[:25] == prev_first_line[:25]:
                        issues.append(f"【開篇定型模板重複】本章開篇「{first_paragraph[:25]}...」與前章開頭完全重複，違反開篇去重禁令")

                if any(kw in time_setting for kw in ("下午", "傍晚", "第二天", "數小時", "深夜")):
                    if any(conn in first_paragraph for conn in ("才剛平息", "上一秒", "剛推開桌上那塊", "剛把桌上那塊泡發")):
                        issues.append(f"【時間連續性矛盾】大綱標明時間跨度為「{time_setting}」，正文開篇卻無縫秒接前章微觀動作")

                # 3. 雙完結／全書終章結構混亂校驗
                if "全書完" in prev_text or "全書收官" in prev_text or "全書終章" in prev_text:
                    cliff = (outline.get("cliffhanger") or outline.get("scene_goal") or "")
                    if "全書完" in cliff or "全書收官" in cliff or "完結" in cliff:
                        issues.append("【雙完結結構矛盾】前一章已標註全書完結，本章大綱或正文再次宣告全書完結收官，造成篇章結構衝突")
                    # 時間倒退校驗（前章已是未來或數月/數年後，本章又重回清晨紮營）
                    prev_time = ""
                    try:
                        from backend.services import narrative_memory
                        prev_outline = narrative_memory.get_chapter_outline(novel_id, chapter_index - 1) or {}
                        prev_time = prev_outline.get("time_setting") or ""
                    except Exception:
                        pass
                    if ("數月" in prev_time or "數年" in prev_time or "三千年" in prev_time) and ("清晨" in time_setting or "元年" in time_setting):
                        issues.append(f"【時序倒流矛盾】前章時間設定為「{prev_time}」，本章又倒退至「{time_setting}」，造成敘事時間線混亂")
        except Exception:
            pass

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

def evaluate_output(
    stage_name: str,
    output_content: Any = "",
    novel_id: str = "",
    chapter_index: Optional[int] = None,
    quality_gate: bool = False,
) -> Dict[str, Any]:
    """
    [Tool 2] 評斷代理人的輸出結果
    透過 APPROVAL_CRITERIA_REGISTRY 進行硬性校驗
    """
    criteria = APPROVAL_CRITERIA_REGISTRY.get(stage_name)
    if not criteria:
        return {"passed": True, "message": "無該階段標準，視為通過", "issues": []}

    issues = []
    narrative_audit = None
    if isinstance(output_content, dict):
        parsed = output_content
        raw_text = parsed.get("content") or parsed.get("text") or ""
        output_content = raw_text
    else:
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
        content, data = _content_from_writer_like_output(parsed, output_content)
        ch_idx = chapter_index or data.get("chapter_index") or 1
        try:
            ch_idx = int(ch_idx)
        except Exception:
            ch_idx = 1
        outline = None
        if novel_id:
            vols = db.get_volumes(novel_id)
            for v in vols:
                ch_list = v.get("chapters_outline") or []
                if isinstance(ch_list, str):
                    try:
                        ch_list = json.loads(ch_list)
                    except Exception:
                        ch_list = []
                for c in ch_list:
                    if isinstance(c, dict) and c.get("chapter_index") == ch_idx:
                        outline = c
                        break
                if outline:
                    break

            # 進行時空與連續性設定校驗 (Setting Continuity Check)
            setting_issues = _validate_chapter_setting_and_continuity(content, outline, novel_id, ch_idx)
            issues.extend(setting_issues)

            # 進行長程敘事因果審計
            try:
                from backend.services.narrative.narrative_auditor import NarrativeAuditor
                audit_res = NarrativeAuditor.audit_chapter_prose(
                    novel_id=novel_id,
                    chapter_index=ch_idx,
                    prose_text=content,
                    current_outline=outline,
                    candidate_conflict_sig=outline.get("conflict_signature_hint") if outline else None,
                )
                narrative_audit = audit_res
                if audit_res.get("overall_action") == "CRITICAL":
                    for f in audit_res.get("findings", []):
                        if f.get("severity") == "critical":
                            issues.append(f"【敘事診斷紅線 ({f['dimension']})】{f['evidence']}：{f['recommendation']}")
            except Exception:
                pass

        # Formulaic style patterns are a hard gate only after editing. At the
        # Writer draft stage they remain actionable feedback for Editor, avoiding
        # rejecting a chapter before the pipeline has had a chance to revise it.
        if quality_gate or stage_name == "editor":
            try:
                from backend.services.narrative.narrative_auditor import extract_banned_hits
                banned_hits = extract_banned_hits(content)
                if banned_hits:
                    issues.append(
                        f"【套路句檢查】正文含 {len(banned_hits)} 個公式化開篇、收尾或重複動作命中"
                    )
                for hit in banned_hits[:10]:
                    label = hit.get("pattern_label") or "套路句"
                    sample = (hit.get("matched_text") or hit.get("matched_sentence") or "").strip()
                    issues.append(f"【套路句檢查】{label}" + (f"：{sample[:60]}" if sample else ""))
            except Exception:
                pass

    criteria_prompt = format_criteria_for_prompt(stage_name)
    has_critical_drift = any(
        i.startswith("【場景地點漂移】") or i.startswith("【時間連續性矛盾】") or i.startswith("【開篇定型模板重複】") or i.startswith("【雙完結結構矛盾】") or i.startswith("【時序倒流矛盾】") or i.startswith("【敘事診斷紅線")
        for i in issues
    )

    # 系統性重點修正分類：將問題區分為 P0 (因果/結構/元敘事洩漏), P1 (時空/開篇/套路), P2 (修辭/語法)
    p0_issues = []
    p1_issues = []
    p2_issues = []
    for iss in issues:
        if iss.startswith("【敘事診斷紅線") or iss.startswith("【雙完結結構矛盾】") or iss.startswith("【時序倒流矛盾】") or "因果" in iss or "知情邊界" in iss or "能力代價" in iss or "任務" in iss or "元敘事" in iss or "拒答" in iss or "長度不足" in iss:
            p0_issues.append(iss)
        elif iss.startswith("【場景地點漂移】") or iss.startswith("【時間連續性矛盾】") or iss.startswith("【開篇定型模板重複】") or "套路句" in iss:
            p1_issues.append(iss)
        else:
            p2_issues.append(iss)

    # 生成總監重點修正工單 (FocusFixPlan)：每輪明確只修一個主目標，避免打地鼠與空轉
    focus_fix_plan = None
    if p0_issues:
        focus_fix_plan = {
            "priority": "P0_CRITICAL",
            "target_agent": "writer",
            "primary_issue": p0_issues[0],
            "actionable_directive": f"【P0 核心因果/邏輯修復】：請重新推演並落實情節因果邏輯。\n問題：{p0_issues[0]}\n方針：嚴格遵循當前章節元素契約與因果邊界，嚴禁純名詞替換。",
        }
    elif p1_issues:
        focus_fix_plan = {
            "priority": "P1_MAJOR",
            "target_agent": "editor",
            "primary_issue": p1_issues[0],
            "actionable_directive": f"【P1 時空/開篇/套路手術】：定點清除問題段落與套路句式。\n問題：{p1_issues[0]}\n方針：由 Editor 進行局部微創手術，替換開篇視角或定點刪改套路句，保持其餘情節不變。",
        }
    elif p2_issues:
        focus_fix_plan = {
            "priority": "P2_MINOR",
            "target_agent": "editor",
            "primary_issue": p2_issues[0],
            "actionable_directive": f"【P2 語句與節奏調理】：潤色詞句與呼吸節奏。\n問題：{p2_issues[0]}\n方針：由 Editor 優化語法調理，增強文學質感與流暢度。",
        }

    # Atmosphere/detail suggestions are advisory: they may improve prose, but
    # should never hold an otherwise valid chapter in a rewrite loop.
    blocking_issues = [
        issue for issue in issues
        if not issue.startswith(("【場景氛圍提醒】", "【場景細節提醒】"))
    ]
    result = {
        "passed": len(blocking_issues) == 0,
        "critical_drift": has_critical_drift,
        "action": "REVISE" if (has_critical_drift or p0_issues or p1_issues) else ("PASS" if len(issues) == 0 else "WARNING"),
        "message": "通過" if len(issues) == 0 else "; ".join(issues),
        "issues": issues,
        "p0_issues": p0_issues,
        "p1_issues": p1_issues,
        "p2_issues": p2_issues,
        "focus_fix_plan": focus_fix_plan,
        "criteria_reference": criteria_prompt,
    }
    if stage_name == "volume_skeleton":
        result["climax_chapter_stats"] = _chapter_climax_stats(_as_skeleton_chapters(parsed))
    if narrative_audit:
        result["narrative_audit"] = narrative_audit
    return result
