"""Character generation handler."""

from __future__ import annotations

import json

from backend import persistence as db

from backend.generation.routing.schema import GenerationTaskRequest
from backend.agents.character_designer.runner import run_character_designer
from backend.agents.incremental.runner import run_incremental_character_designer


def _resolve_mode(task: GenerationTaskRequest) -> str:
    if task.task_type == "generate":
        return "generate"
    if task.options.overwrite or task.task_type in {"regenerate", "patch", "refine", "batch_generate"}:
        return "expand"
    if task.scope in {"selection", "chapter", "section"}:
        return "expand"
    return "generate"


from backend.generation.handlers import resolve_handler_prompt


def run_characters_task(task: GenerationTaskRequest, context=None):
    prompt = resolve_handler_prompt(task, default_instruction="請設計立體豐富的主角、主要配角與反派角色設定")

    wb = db.get_latest_worldbuilding(task.novel_id)
    worldview_content = wb["content"] if wb else ""
    worldview_diag = ""
    if worldview_content:
        try:
            parsed_worldview = db.parse_worldview_to_json(worldview_content)
            if not all(parsed_worldview.get(key) for key in ("theme", "main_conflict", "worldview", "macro_outline")):
                worldview_diag = "世界觀核心欄位尚未完整"
        except Exception:
            worldview_diag = "世界觀資料無法解析"
    else:
        worldview_diag = "世界觀為空"

    if worldview_diag:
        if not task.options.stream:
            def _error_stream():
                yield "data: " + json.dumps({"type": "error", "message": f"角色生成前置檢查失敗：{worldview_diag}"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return _error_stream()

        def _redirect_to_worldview():
            decision = {
                "action": "CONTINUE",
                "target": "worldview",
                "hint": "世界觀尚未完成，請先生成核心世界觀、多幕式結構與角色漸進登場規劃，再回到角色設計。",
                "agent_prompt": prompt or "請根據作者原始需求生成完整世界觀。",
                "agent_context": f"角色階段前置檢查失敗：{worldview_diag}",
                "reason": "角色設計依賴世界觀核心設定；目前不能在空世界觀上生成角色。",
                "volume_index": None,
                "chapter_index": None,
            }
            yield "data: " + json.dumps({
                "type": "content",
                "delta": "\n【後端前置檢查】角色生成需要先完成世界觀。已導向世界觀階段。\n```json\n"
                + json.dumps(decision, ensure_ascii=False, indent=2)
                + "\n```\n"
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return _redirect_to_worldview()
    
    if task.task_type == "patch":
        field_name = getattr(task, "field_name", None)
        target_char_idx = getattr(task, "target_char_index", None)
        if target_char_idx is not None or field_name:
            return run_incremental_character_designer(
                task.novel_id,
                target_char_idx,
                field_name,
                prompt,
                stream=task.options.stream,
                force_json=True,
            )
        return run_incremental_character_designer(
            task.novel_id,
            None,
            None,
            prompt,
            stream=task.options.stream,
            force_json=True,
        )
            
    mode = _resolve_mode(task)
    target_char_index = task.target.section_index
    if target_char_index is None and task.target.chapter_index is not None:
        target_char_index = task.target.chapter_index

    # 從 task 中解析 [BATCH: xxx] 標籤
    batch_target = None
    texts_to_check = [
        getattr(task, "agent_prompt", None) or "",
        task.instruction or "",
        task.hint or "",
        task.user_prompt or "",
    ]
    for text in texts_to_check:
        if not text:
            continue
        import re
        m = re.search(r'\[BATCH:\s*([^\]]+)\]', text, re.IGNORECASE)
        if m:
            batch_target = m.group(1).strip()
            break

    return run_character_designer(
        task.novel_id,
        user_prompt=prompt or None,
        hint=task.hint,
        mode=mode,
        target_char_index=target_char_index,
        stream=task.options.stream,
        force_json=True,
        batch_target=batch_target,
    )
