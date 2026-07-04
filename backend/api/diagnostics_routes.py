"""Diagnostics and special endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class ResolveMissingIndexPayload(BaseModel):
    target: str
    action: Optional[str] = None

@router.post("/novels/{novel_id}/director-decision/resolve-missing-index")
def api_resolve_missing_index(novel_id: str, payload: ResolveMissingIndexPayload):
    from backend import db
    import json
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    target = (payload.target or "").strip().lower()
    resolved_volume_index = None
    resolved_chapter_index = None

    if "skeleton" in target or target == "volume_skeleton":
        vols = db.get_volumes(novel_id)
        for v in sorted(vols, key=lambda x: x.get("volume_index", 0)):
            outline = v.get("chapters_outline")
            if not outline:
                resolved_volume_index = v["volume_index"]
                break
            try:
                parsed = outline if isinstance(outline, list) else json.loads(outline or "[]")
                if not isinstance(parsed, list) or len(parsed) == 0:
                    resolved_volume_index = v["volume_index"]
                    break
            except Exception:
                resolved_volume_index = v["volume_index"]
                break
        if resolved_volume_index is None and vols:
            resolved_volume_index = max(v.get("volume_index", 1) for v in vols)

    elif target in ("writer", "editor"):
        vols = db.get_volumes(novel_id)
        total_planned = sum(
            int(v.get("chapter_count") or 0)
            for v in vols
            if str(v.get("chapter_count", "")).isdigit()
        ) or 50

        written_chs = db.get_all_chapters_latest(novel_id)
        written_idx = set()
        for ch in written_chs:
            c_idx = ch.get("chapter_index")
            if c_idx:
                try:
                    content = ch.get("content", "")
                    is_placeholder = "保底" in content or "占位" in content or len(content.strip()) < 100
                    if not is_placeholder:
                        written_idx.add(int(c_idx))
                except Exception:
                    pass

        for i in range(1, total_planned + 1):
            if i not in written_idx:
                resolved_chapter_index = i
                break

        if resolved_chapter_index is None:
            resolved_chapter_index = total_planned

        if vols:
            for v in sorted(vols, key=lambda x: x.get("volume_index", 0)):
                start_ch, end_ch = db.get_volume_chapter_range(vols, v["volume_index"])
                if start_ch <= resolved_chapter_index <= end_ch:
                    resolved_volume_index = v["volume_index"]
                    break

    return {
        "status": "success",
        "target": target,
        "resolved_volume_index": resolved_volume_index,
        "resolved_chapter_index": resolved_chapter_index,
        "message": f"已補正 volume_index={resolved_volume_index}, chapter_index={resolved_chapter_index}"
    }


class HealRollbackPayload(BaseModel):
    target_chapter_index: int

@router.post("/novels/{novel_id}/retrospective")
def api_novel_retrospective(novel_id: str):
    from backend import db
    import concurrent.futures
    import json

    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    stitched_plot = db.get_stitched_plot(novel_id)
    chapters = db.get_all_chapters_latest(novel_id)
    chapter_samples = []
    if chapters:
        sample_rows = chapters[:3]
        if len(chapters) > 6:
            sample_rows += chapters[-3:]
        else:
            sample_rows = chapters
        for ch in sample_rows:
            content = ch.get("content", "") or ""
            chapter_samples.append({
                "chapter_index": ch.get("chapter_index"),
                "synopsis": ch.get("synopsis", ""),
                "content_excerpt": content[:900]
            })

    from backend.prompts.prompt_builder import extract_worldview_summary, extract_character_names_list
    from backend.llm import call_llm_stream
    context = {
        "worldbuilding": extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定",
        "characters": json.dumps({"character_names": extract_character_names_list(char["json_data"])}, ensure_ascii=False) if char else "尚無角色設定",
        "plot": {
            "total_chapters": len(stitched_plot.get("chapters", [])) if stitched_plot else 0,
            "volumes_summary": [
                {"volume_index": v.get("volume_index"), "title": v.get("title"), "summary": v.get("summary")}
                for v in db.get_volumes(novel_id)
            ]
        } if stitched_plot else {"chapters": []},
        "written_chapters": f"已寫作正文章節共 {len(chapters)} 章。" if chapters else "尚未開始寫作正文。",
        "chapter_samples": chapter_samples
    }

    agents_to_call = {
        "Story Architect": ("architect", "你作為故事結構架構師，請針對本次創作的世界觀底層設定，提出心得。列出3-5條避坑金律。"),
        "Character Designer": ("character", "你作為角色設計大師，請針對本次角色人設，提出心得。列出3-5條人物避坑金律。"),
        "Plot Planner": ("plot", "你作為章節劇情規劃師，請針對本次大綱規劃，提出大綱規劃心得。列出3-5條避坑金律。"),
        "Chapter Writer": ("writer", "你作為小說正文寫作作家，請針對本章正文寫作，提出心得。列出3-5條正文創作金律。"),
        "Co-pilot Director": ("copilot", "你作為首席創意總監，對整部作品進行評審，總結全局避坑指南與終極創作金律。")
    }

    def get_agent_retrospective(agent_key, config_tuple):
        agent_name, prompt_msg = config_tuple
        messages = [
            {"role": "system", "content": "你是一位嚴謹的創作大師。請使用 zh-TW 繁體中文輸出簡潔、深刻、高水準的心得與金律。"},
            {"role": "user", "content": f"{prompt_msg}\n\n上下文：\n{json.dumps(context, ensure_ascii=False)}"}
        ]
        text = ""
        for chunk in call_llm_stream(agent_name, messages):
            if chunk.startswith("data:"):
                try:
                    data = json.loads(chunk[5:].strip())
                    if data.get("type") == "content":
                        text += data.get("delta", "")
                except:
                    pass
        return text.strip()

    retrospectives = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_agent_retrospective, k, v): k for k, v in agents_to_call.items()}
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                retrospectives[key] = future.result()
            except Exception as e:
                retrospectives[key] = f"生成心得失敗：{str(e)}"

    final_markdown = f"# 《{novel['title']}》AI 創作圓桌避坑金律說明書\n\n"
    for agent_display_name in agents_to_call.keys():
        val = retrospectives.get(agent_display_name, "生成心得失敗：未取得結果")
        final_markdown += f"## {agent_display_name} 的復盤心得\n\n{val}\n\n---\n\n"

    import os
    from backend.utils import safe_filename
    gold_rules_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "gold_rules")
    os.makedirs(gold_rules_dir, exist_ok=True)
    safe_title = safe_filename(novel["title"])
    filepath = os.path.join(gold_rules_dir, f"{safe_title}_retrospective_gold_rules.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_markdown)

    return {
        "status": "success",
        "filepath": filepath,
        "markdown": final_markdown
    }

@router.post("/novels/{novel_id}/chapters/heal-rollback")
def api_heal_rollback(novel_id: str, payload: HealRollbackPayload):
    from backend import db
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        db.delete_and_shift_surrounding_chapters(novel_id, payload.target_chapter_index)
        start_del = max(1, payload.target_chapter_index - 3)
        end_del = payload.target_chapter_index + 3
        return {"status": "success", "start_del": start_del, "end_del": end_del}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/novels/{novel_id}/pipeline-status")
def api_pipeline_status(novel_id: str):
    from backend import db
    lock_info = db.get_pipeline_lock_status(novel_id)
    if lock_info is not None:
        try:
            db.update_pipeline_heartbeat(novel_id)
        except Exception:
            pass
    return {"running": lock_info is not None, "lock_info": lock_info}

@router.post("/novels/{novel_id}/chapters/restore-backup")
def api_restore_chapters_backup(novel_id: str):
    from backend import db
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    restored = db.restore_chapters_backup(novel_id)
    return {"status": "success", "restored_count": restored}

@router.post("/novels/{novel_id}/bodystop")
def api_bodystop(novel_id: str):
    """Hard tail break: delete all chapters beyond the given chapter_index."""
    from backend.services.diagnostics import bodystop_command
    try:
        result = bodystop_command(novel_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))