"""Diagnostics and special endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class HealRollbackPayload(BaseModel):
    target_chapter_index: int

@router.post("/novels/{novel_id}/retrospective")
def api_novel_retrospective(novel_id: str):
    from backend import persistence as db
    import concurrent.futures
    import json

    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    stitched_plot = db.get_stitched_plot(novel_id)
    chapters = db.get_all_chapters_latest(novel_id)
    chapter_samples = {
        "director_payload_view": "collapsed_json",
        "payload_kind": "written_chapters",
        "total_count": len(chapters or []),
        "chapters": [
            {
                "chapter_index": ch.get("chapter_index"),
                "synopsis": ch.get("synopsis", ""),
                "content_char_count": len(ch.get("content", "") or ""),
                "content": (ch.get("content", "") or "") if len(ch.get("content", "") or "") <= 1200 else {
                    "__collapsed_text__": True,
                    "message": "章節正文已收合；復盤若需精讀，應由總監指定章節展開。",
                },
            }
            for ch in (chapters or [])
        ],
    }

    from backend.prompts.common.context import extract_worldview_summary, extract_character_names_list
    from backend.common.llm import call_llm_stream
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
        "Story Architect": ("architect",
            "你作為故事結構架構師，回顧本次創作的世界觀底層設定，輸出結構化創作金律。\n"
            "請嚴格依以下三區塊輸出，每區塊 3-5 條，業務範圍限於「世界觀與故事結構」：\n"
            "【必做規則】列出在建立世界觀時必須遵守的步驟與檢查項。\n"
            "【禁止事項】列出在世界觀設計中曾導致問題、不得再犯的禁止事項。\n"
            "【允許範圍】列出可由創作者自由發揮、不影響結構正確性的彈性區域。"),
        "Character Designer": ("character",
            "你作為角色設計大師，回顧本次角色人設的製作過程，輸出結構化創作金律。\n"
            "請嚴格依以下三區塊輸出，每區塊 3-5 條，業務範圍限於「角色設計」：\n"
            "【必做規則】列出角色設計時必須完成的步驟與必要欄位。\n"
            "【禁止事項】列出角色設計中曾導致人設紊亂或矛盾的禁止事項。\n"
            "【允許範圍】列出角色性格、背景等可由創作者自由調整的彈性區域。"),
        "Plot Planner": ("plot",
            "你作為章節劇情規劃師，回顧本次大綱規劃的製作過程，輸出結構化創作金律。\n"
            "請嚴格依以下三區塊輸出，每區塊 3-5 條，業務範圍限於「大綱與劇情規劃」：\n"
            "【必做規則】列出大綱規劃時必須遵守的步驟與結構檢查項。\n"
            "【禁止事項】列出大綱規劃中曾導致劇情断裂或邏輯衝突的禁止事項。\n"
            "【允許範圍】列出劇情細節、節奏等可由創作者自由調整的彈性區域。"),
        "Chapter Writer": ("writer",
            "你作為小說正文寫作作家，回顧本章正文的寫作過程，輸出結構化創作金律。\n"
            "請嚴格依以下三區塊輸出，每區塊 3-5 條，業務範圍限於「正文寫作」：\n"
            "【必做規則】列出正文寫作時必須遵守的寫作步驟與品質檢查項。\n"
            "【禁止事項】列出正文寫作中曾導致品質問題的禁止事項（如視角混亂、語氣不一致等）。\n"
            "【允許範圍】列出文風、修辭等可由創作者自由發揮的彈性區域。"),
        "Co-pilot Director": ("copilot",
            "你作為首席創意總監，對整部作品進行全局評審，輸出結構化終極創作金律。\n"
            "請嚴格依以下三區塊輸出，每區塊 3-5 條，業務範圍涵蓋「全局品質與流程管控」：\n"
            "【必做規則】列出跨階段協作時必須遵守的流程步驟與全局檢查項。\n"
            "【禁止事項】列出曾導致跨階段衝突或全局品質問題的禁止事項。\n"
            "【允許範圍】列出可由各階段創作者自行決定、不影響全局一致性的彈性區域。"),
    }

    def get_agent_retrospective(agent_key, config_tuple):
        agent_name, prompt_msg = config_tuple
        messages = [
            {"role": "system", "content": "你是一位嚴謹的創作大師。請使用 zh-TW 繁體中文，以結構化規則格式輸出創作金律。每條規則必須具體、可操作、可被程式比對，不得輸出空泛心得。嚴格遵從【必做規則】【禁止事項】【允許範圍】三區塊結構。"},
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

    final_markdown = f"# 《{novel['title']}》AI 創作金律規則手冊\n\n"
    for agent_display_name in agents_to_call.keys():
        val = retrospectives.get(agent_display_name, "生成金律失敗：未取得結果")
        final_markdown += f"## {agent_display_name} 的創作金律\n\n{val}\n\n---\n\n"

    from backend.schemas.constraints import gold_rules_directory, gold_rules_filename
    import os
    gold_rules_dir = gold_rules_directory()
    os.makedirs(gold_rules_dir, exist_ok=True)
    safe_title = gold_rules_filename(novel["title"])
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
    from backend import persistence as db
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
    from backend import persistence as db
    lock_info = db.get_pipeline_lock_status(novel_id)
    return {"running": lock_info is not None, "lock_info": lock_info}

@router.post("/novels/{novel_id}/chapters/restore-backup")
def api_restore_chapters_backup(novel_id: str):
    from backend import persistence as db
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
