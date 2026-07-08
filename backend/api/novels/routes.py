"""Novel CRUD and core data endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import uuid

from backend import persistence as db

router = APIRouter()

# --- PYDANTIC SCHEMAS ---
class NovelCreate(BaseModel):
    title: str
    genre: Optional[str] = "Fantasy"
    style: Optional[str] = "Classic Modernism"

class WorldbuildingSave(BaseModel):
    content: str

class CharactersSave(BaseModel):
    json_data: Any

class PlotSave(BaseModel):
    outline_json: Any

class ChapterSave(BaseModel):
    content: str

class CharacterAdjustRequest(BaseModel):
    char_index: int
    field_name: str
    value: Any

class VolumeAdjustRequest(BaseModel):
    volume_index: int
    field_name: str
    value: Any

class PipelinePromptSave(BaseModel):
    pipeline_prompt: str

# --- NOVELS ROUTES ---
@router.get("/novels")
def api_list_novels():
    return db.list_novels()

@router.post("/novels")
def api_create_novel(novel: NovelCreate):
    novel_id = str(uuid.uuid4())
    db.create_novel(novel_id, novel.title, novel.genre, novel.style)
    return {"status": "success", "novel_id": novel_id}

@router.get("/novels/{novel_id}")
def api_get_novel(novel_id: str):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    plot_data = db.get_stitched_plot(novel_id)
    written_ch = db.get_all_chapters_latest(novel_id)
    memory = db.get_chat_memory(novel_id, limit=30)

    return {
        "novel": novel,
        "worldbuilding": wb["content"] if wb else "",
        "worldbuilding_version": wb["version"] if wb else 0,
        "characters": char["parsed_data"] if char else None,
        "characters_raw": char["json_data"] if char else "",
        "characters_version": char["version"] if char else 0,
        "plot": plot_data if plot_data else {"chapters": []},
        "plot_raw": str(plot_data) if plot_data else "{}",
        "plot_version": 1,
        "chapters": written_ch,
        "chat_memory": memory,
        "volumes": db.get_volumes(novel_id),
        "worldview_patches": db.get_worldview_patches(novel_id)
    }

@router.delete("/novels/{novel_id}")
def api_delete_novel(novel_id: str):
    db.delete_novel(novel_id)
    return {"status": "success"}


# --- MANUAL SAVE OVERRIDES ---
@router.post("/novels/{novel_id}/worldbuilding")
def api_save_worldbuilding(novel_id: str, payload: WorldbuildingSave):
    try:
        v = db.save_worldbuilding(novel_id, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "success", "version": v}

@router.post("/novels/{novel_id}/characters")
def api_save_characters(novel_id: str, payload: CharactersSave):
    v = db.save_characters(novel_id, payload.json_data)
    return {"status": "success", "version": v}

@router.post("/novels/{novel_id}/characters/deduplicate")
def api_deduplicate_characters(novel_id: str):
    char_data = db.get_latest_characters(novel_id)
    if not char_data:
        raise HTTPException(status_code=404, detail="尚無角色設定可進行去重")
    parsed = char_data.get("parsed_data")
    if not parsed or "characters" not in parsed:
        raise HTTPException(status_code=400, detail="角色聖經結構不完整")

    v = db.save_characters(novel_id, parsed)
    return {"status": "success", "version": v}

@router.post("/novels/{novel_id}/plot")
def api_save_plot(novel_id: str, payload: PlotSave):
    v = db.save_plot_chapters(novel_id, payload.outline_json)
    return {"status": "success", "version": v}

@router.post("/novels/{novel_id}/chapters/{chapter_index}")
def api_save_chapter(novel_id: str, chapter_index: int, payload: ChapterSave):
    v = db.save_chapter(novel_id, chapter_index, payload.content)
    return {"status": "success", "version": v}

@router.post("/novels/{novel_id}/clear-chat")
def api_clear_chat(novel_id: str):
    db.clear_chat_memory(novel_id)
    return {"status": "success"}

@router.post("/novels/{novel_id}/pipeline-prompt")
def api_save_pipeline_prompt(novel_id: str, payload: PipelinePromptSave):
    db.update_novel_pipeline_prompt(novel_id, payload.pipeline_prompt)
    return {"status": "success"}

@router.get("/novels/{novel_id}/pipeline-prompt")
def api_get_pipeline_prompt(novel_id: str):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return {"pipeline_prompt": novel.get("pipeline_prompt", "")}


# --- CODE-BASED JSON MANIPULATIONS WITH RETRY ---
@router.post("/novels/{novel_id}/characters/adjust")
def api_adjust_character(novel_id: str, payload: CharacterAdjustRequest):
    import time
    for attempt in range(3):
        try:
            char_data = db.get_latest_characters(novel_id)
            if not char_data:
                raise HTTPException(status_code=404, detail="Characters Bible not found")
            parsed = char_data.get("parsed_data", {})
            chars = parsed.get("characters", [])

            try:
                normalized_idx = db.normalize_char_index(payload.char_index, len(chars), source='api_adjust_character')
                chars[normalized_idx][payload.field_name] = payload.value
                db.save_characters(novel_id, parsed)
                return {"status": "success", "message": f"Successfully updated character {normalized_idx}."}
            except IndexError:
                raise HTTPException(status_code=400, detail=f"角色索引 {payload.char_index} 超出範圍 [0, {len(chars)})")
        except Exception as e:
            print(f"[Programmatic Adjust Retry] Character edit attempt {attempt + 1} failed: {e}")
            time.sleep(1)

    raise HTTPException(status_code=500, detail="Failed to adjust character JSON programmatically after 3 attempts")

@router.post("/novels/{novel_id}/volumes/adjust")
def api_adjust_volume(novel_id: str, payload: VolumeAdjustRequest):
    import time
    for attempt in range(3):
        try:
            vols = db.get_volumes(novel_id)
            target = next((v for v in vols if v["volume_index"] == payload.volume_index), None)
            if target:
                for v in vols:
                    if v["volume_index"] == payload.volume_index:
                        v[payload.field_name] = payload.value
                db.save_volumes(novel_id, vols)
                return {"status": "success", "message": f"Successfully updated volume {payload.volume_index}."}
            else:
                raise HTTPException(status_code=404, detail=f"Volume index {payload.volume_index} not found")
        except Exception as e:
            print(f"[Programmatic Adjust Retry] Volume edit attempt {attempt + 1} failed: {e}")
            time.sleep(1)

    raise HTTPException(status_code=500, detail="Failed to adjust volume JSON programmatically after 3 attempts")