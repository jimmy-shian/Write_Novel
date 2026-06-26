# -*- coding: utf-8 -*-
import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any, List
import uuid
import os
import json
import time

import db
import agents
from llm import get_config_for_agent, get_default_config
from db import AGENT_DEFAULTS

# Initialize database
db.db_init()

app = FastAPI(title="AI Novel Factory API", version="2.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class AgentConfigSave(BaseModel):
    agent_name: str
    api_key: str
    base_url: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    enable_thinking: bool

class HealRollbackPayload(BaseModel):
    target_chapter_index: int

class CharacterDesignerRequest(BaseModel):
    novel_id: str
    user_prompt: Optional[str] = None
    hint: Optional[str] = None
    mode: Optional[str] = "generate"  # generate, expand, modify
    target_char_index: Optional[int] = None

class VolumesPlannerRequest(BaseModel):
    novel_id: str
    user_prompt: Optional[str] = None
    hint: Optional[str] = None
    mode: Optional[str] = "generate"  # generate, patch
    target_vol_idx: Optional[int] = None

class VolumeSkeletonRequest(BaseModel):
    novel_id: str
    volume_index: int
    user_prompt: Optional[str] = None

class PlotPlannerRequest(BaseModel):
    novel_id: str
    chapter_index: Optional[int] = None
    user_prompt: Optional[str] = None
    planner_directive: Optional[str] = None

class ChapterWriterRequest(BaseModel):
    novel_id: str
    chapter_index: int
    custom_style: Optional[str] = "Classic Modernism"
    user_prompt: Optional[str] = None

class EditorAgentRequest(BaseModel):
    novel_id: str
    chapter_index: int
    edit_instructions: Optional[str] = None

class CopilotChatRequest(BaseModel):
    novel_id: str
    user_message: str

class DirectorDecisionRequest(BaseModel):
    current_stage: str
    user_prompt: Optional[str] = None
    chapter_index: Optional[int] = None
    volume_index: Optional[int] = None
    character_review_mode: Optional[str] = None
    character_review_hint: Optional[str] = None
    character_review_target_content: Optional[str] = None
    suggested_next_chapter: Optional[int] = None
    conversation_context: Optional[str] = None
    summary_context: Optional[str] = None
    extra_context: Optional[str] = None

class DirectorHelpPayload(BaseModel):
    current_stage: str
    help_action: str
    help_reason: str

class CharacterAdjustRequest(BaseModel):
    char_index: int
    field_name: str
    value: Any

class VolumeAdjustRequest(BaseModel):
    volume_index: int
    field_name: str
    value: Any

class IncrementalArchitectRequest(BaseModel):
    novel_id: str
    target_section: str
    user_hint: str

class IncrementalCharacterRequest(BaseModel):
    novel_id: str
    target_char_index: Optional[int] = None
    field_name: Optional[str] = None
    user_hint: str

class IncrementalPlotRequest(BaseModel):
    novel_id: str
    insert_after_index: int
    user_hint: str

class IncrementalSkeletonRequest(BaseModel):
    novel_id: str
    volume_index: int
    user_hint: str


# --- NOVELS ROUTES ---
@app.get("/api/novels")
def api_list_novels():
    return db.list_novels()

@app.post("/api/novels")
def api_create_novel(novel: NovelCreate):
    novel_id = str(uuid.uuid4())
    db.create_novel(novel_id, novel.title, novel.genre, novel.style)
    return {"status": "success", "novel_id": novel_id}

@app.get("/api/novels/{novel_id}")
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
        "plot_raw": json.dumps(plot_data, ensure_ascii=False, indent=2) if plot_data else "{}",
        "plot_version": 1,
        "chapters": written_ch,
        "chat_memory": memory,
        "volumes": db.get_volumes(novel_id),
        "worldview_patches": db.get_worldview_patches(novel_id)
    }

@app.delete("/api/novels/{novel_id}")
def api_delete_novel(novel_id: str):
    db.delete_novel(novel_id)
    return {"status": "success"}


# --- MANUAL SAVE OVERRIDES ---
@app.post("/api/novels/{novel_id}/worldbuilding")
def api_save_worldbuilding(novel_id: str, payload: WorldbuildingSave):
    v = db.save_worldbuilding(novel_id, payload.content)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/characters")
def api_save_characters(novel_id: str, payload: CharactersSave):
    v = db.save_characters(novel_id, payload.json_data)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/characters/deduplicate")
def api_deduplicate_characters(novel_id: str):
    char_data = db.get_latest_characters(novel_id)
    if not char_data:
        raise HTTPException(status_code=404, detail="尚無角色設定可進行去重")
    parsed = char_data.get("parsed_data")
    if not parsed or "characters" not in parsed:
        raise HTTPException(status_code=400, detail="角色聖經結構不完整")
    
    v = db.save_characters(novel_id, parsed)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/plot")
def api_save_plot(novel_id: str, payload: PlotSave):
    v = db.save_plot_chapters(novel_id, payload.outline_json)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/chapters/{chapter_index}")
def api_save_chapter(novel_id: str, chapter_index: int, payload: ChapterSave):
    v = db.save_chapter(novel_id, chapter_index, payload.content)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/clear-chat")
def api_clear_chat(novel_id: str):
    db.clear_chat_memory(novel_id)
    return {"status": "success"}

class PipelinePromptSave(BaseModel):
    pipeline_prompt: str

@app.post("/api/novels/{novel_id}/pipeline-prompt")
def api_save_pipeline_prompt(novel_id: str, payload: PipelinePromptSave):
    db.update_novel_pipeline_prompt(novel_id, payload.pipeline_prompt)
    return {"status": "success"}

@app.get("/api/novels/{novel_id}/pipeline-prompt")
def api_get_pipeline_prompt(novel_id: str):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return {"pipeline_prompt": novel.get("pipeline_prompt", "")}


# --- CODE-BASED JSON MANIPULATIONS WITH RETRY ---
@app.post("/api/novels/{novel_id}/characters/adjust")
def api_adjust_character(novel_id: str, payload: CharacterAdjustRequest):
    """
    Programmatic character Bible JSON field update with automatic retries.
    """
    for attempt in range(3):
        try:
            char_data = db.get_latest_characters(novel_id)
            if not char_data:
                raise HTTPException(status_code=404, detail="Characters Bible not found")
            parsed = char_data.get("parsed_data", {})
            chars = parsed.get("characters", [])
            
            if 0 <= payload.char_index < len(chars):
                chars[payload.char_index][payload.field_name] = payload.value
                db.save_characters(novel_id, parsed)
                return {"status": "success", "message": f"Successfully updated character {payload.char_index}."}
            else:
                raise HTTPException(status_code=400, detail="Character index out of bounds")
        except Exception as e:
            print(f"[Programmatic Adjust Retry] Character edit attempt {attempt + 1} failed: {e}")
            time.sleep(1)
            
    raise HTTPException(status_code=500, detail="Failed to adjust character JSON programmatically after 3 attempts")

@app.post("/api/novels/{novel_id}/volumes/adjust")
def api_adjust_volume(novel_id: str, payload: VolumeAdjustRequest):
    """
    Programmatic volumes JSON field update with automatic retries.
    """
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


# --- DYNAMIC AGENT PIPELINE ENDPOINTS ---
@app.post("/api/agent/story-architect")
def api_agent_story_architect(novel_id: str = Body(...), user_prompt: str = Body(...)):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_story_architect(novel_id, user_prompt)),
        media_type="text/event-stream"
    )

@app.post("/api/agent/character-designer")
def api_agent_character_designer(payload: CharacterDesignerRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_character_designer(
            novel_id=payload.novel_id,
            user_prompt=payload.user_prompt,
            hint=payload.hint,
            mode=payload.mode,
            target_char_index=payload.target_char_index
        )),
        media_type="text/event-stream"
    )

@app.post("/api/agent/volumes-planner")
def api_agent_volumes_planner(payload: VolumesPlannerRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_volumes_planner(
            novel_id=payload.novel_id,
            user_prompt=payload.user_prompt,
            hint=payload.hint,
            mode=payload.mode,
            target_vol_idx=payload.target_vol_idx
        )),
        media_type="text/event-stream"
    )

@app.post("/api/agent/volume-skeleton")
def api_agent_volume_skeleton(payload: VolumeSkeletonRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_volume_skeleton_planner(
            novel_id=payload.novel_id,
            volume_index=payload.volume_index,
            user_prompt=payload.user_prompt
        )),
        media_type="text/event-stream"
    )



@app.post("/api/agent/write-chapter")
def api_agent_write_chapter(payload: ChapterWriterRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_chapter_writer(
            novel_id=payload.novel_id,
            chapter_index=payload.chapter_index,
            custom_style=payload.custom_style,
            user_prompt=payload.user_prompt
        )),
        media_type="text/event-stream"
    )

@app.post("/api/agent/edit-chapter")
def api_agent_edit_chapter(payload: EditorAgentRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_editor_agent(
            novel_id=payload.novel_id,
            chapter_index=payload.chapter_index,
            edit_instructions=payload.edit_instructions
        )),
        media_type="text/event-stream"
    )

@app.post("/api/agent/copilot-chat")
def api_agent_copilot_chat(payload: CopilotChatRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_copilot_chat(payload.novel_id, payload.user_message)),
        media_type="text/event-stream"
    )

@app.post("/api/agent/incremental-architect")
def api_incremental_architect(payload: IncrementalArchitectRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_incremental_architect(payload.novel_id, payload.target_section, payload.user_hint)),
        media_type="text/event-stream"
    )

@app.post("/api/agent/incremental-character")
def api_incremental_character(payload: IncrementalCharacterRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_incremental_character_designer(payload.novel_id, payload.target_char_index, payload.field_name, payload.user_hint)),
        media_type="text/event-stream"
    )



@app.post("/api/agent/incremental-skeleton")
def api_incremental_skeleton(payload: IncrementalSkeletonRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_incremental_volume_skeleton(payload.novel_id, payload.volume_index, payload.user_hint)),
        media_type="text/event-stream"
    )


# --- PIPELINE REVIEW & CHECKPOINT ENDPOINTS ---
@app.post("/api/novels/{novel_id}/director-decision")
def api_director_decision(novel_id: str, payload: DirectorDecisionRequest):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
        
    effective_prompt = (payload.user_prompt or "").strip()
    if not effective_prompt:
        effective_prompt = (novel.get("pipeline_prompt") or "").strip()
        
    if not effective_prompt:
        def error_gen():
            yield "data: " + json.dumps({
                "type": "error",
                "message": "缺少創作需求（pipeline prompt）。請先在「一鍵生成全書」輸入你的創作需求。"
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_director_decision(
            novel_id, payload.current_stage, effective_prompt,
            chapter_index=payload.chapter_index,
            volume_index=payload.volume_index,
            character_review_mode=payload.character_review_mode,
            character_review_hint=payload.character_review_hint,
            character_review_target_content=payload.character_review_target_content,
            suggested_next_chapter=payload.suggested_next_chapter,
            conversation_context=payload.conversation_context,
            summary_context=payload.summary_context,
            extra_context=payload.extra_context,
        )),
        media_type="text/event-stream"
    )

@app.post("/api/novels/{novel_id}/director-decision/help")
def api_director_decision_help(novel_id: str, payload: DirectorHelpPayload):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
        
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_director_decision_help(
            novel_id=novel_id,
            current_stage=payload.current_stage,
            help_action=payload.help_action,
            help_reason=payload.help_reason
        )),
        media_type="text/event-stream"
    )


class ResolveMissingIndexPayload(BaseModel):
    target: str  # 目標階段，如 "volume_skeleton", "writer", "editor"
    action: Optional[str] = None  # 例如 "CONTINUE"

@app.post("/api/novels/{novel_id}/director-decision/resolve-missing-index")
def api_resolve_missing_index(novel_id: str, payload: ResolveMissingIndexPayload):
    """
    純 Python 計算補正端點（不呼叫 AI）。
    當 AI 總監的 JSON 缺少 volume_index 或 chapter_index 時，前端可呼叫此端點，
    由後端根據資料庫現有資料，自動計算出正確的 volume_index / chapter_index。
    """
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    target = (payload.target or "").strip().lower()
    resolved_volume_index = None
    resolved_chapter_index = None
    
    if "skeleton" in target or target == "volume_skeleton":
        # 找出第一個缺失骨架的卷
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
        
        # 若所有卷均有骨架，回傳最後一卷 + 1（或錯誤）
        if resolved_volume_index is None and vols:
            resolved_volume_index = max(v.get("volume_index", 1) for v in vols)
    
    elif target in ("writer", "editor"):
        # 找出最早未寫的章節
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
        
        # 同時計算 volume_index
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



# --- SYSTEM SETTINGS CONTROLS ---
@app.get("/api/settings")
def api_get_settings():
    defaults = get_default_config()
    all_agents = ["global", "architect", "character", "volumes", "volume_skeleton", "plot", "writer", "editor", "copilot"]
    try:
        plot_review_batch_size = int(os.getenv("PLOT_REVIEW_BATCH_SIZE", "3"))
        if plot_review_batch_size <= 0:
            plot_review_batch_size = 3
    except Exception:
        plot_review_batch_size = 3
    
    AGENT_DISPLAY_NAMES = {
        "global": "Global 全域 (預設設置)",
        "architect": "1️⃣ Story Architect (故事結構架構師)",
        "character": "2️⃣ Character Designer (角色設計大師)",
        "volumes": "3️⃣ Volumes Planner (篇卷規劃師)",
        "volume_skeleton": "4️⃣ Volume Skeleton Planner (篇卷骨架規劃師)",
        "plot": "5️⃣ Plot Planner (章節劇情規劃師)",
        "writer": "6️⃣ Chapter Writer (小說正文寫作作家)",
        "editor": "7️⃣ Editor Agent (精緻文風編輯)",
        "copilot": "🧠 Co-Pilot Orchestrator (AI 總監)"
    }
    
    merged = {}
    for agent in all_agents:
        llm_config = get_config_for_agent(agent)
        merged[agent] = {
            "api_key": llm_config.get("api_key", ""),
            "base_url": llm_config.get("base_url", defaults["base_url"]),
            "model": llm_config.get("model", ""),
            "temperature": llm_config.get("temperature", defaults["temperature"]),
            "top_p": llm_config.get("top_p", defaults["top_p"]),
            "max_tokens": llm_config.get("max_tokens", defaults["max_tokens"]),
            "enable_thinking": llm_config.get("enable_thinking", defaults["enable_thinking"]),
            "display_name": AGENT_DISPLAY_NAMES.get(agent, agent),
            "plot_review_batch_size": plot_review_batch_size
        }

    try:
        models_config_str = os.getenv("MODELS_CONFIG", "{}")
        models_config = json.loads(models_config_str)
    except Exception:
        models_config = {}
    
    merged["_modelsConfig"] = models_config

    return merged

@app.post("/api/settings")
def api_save_settings(config: AgentConfigSave):
    db.save_agent_config(
        config.agent_name,
        config.api_key,
        config.base_url,
        config.model,
        config.temperature,
        config.top_p,
        config.max_tokens,
        config.enable_thinking
    )
    return {"status": "success"}


# =============================================================================
# PIPELINE CHAPTER INSERT ENDPOINT
# =============================================================================
class PlotChapterInsertPayload(BaseModel):
    insert_after_index: int
    new_chapter: dict

@app.post("/api/novels/{novel_id}/plot/chapters/insert")
def api_insert_plot_chapter(novel_id: str, payload: PlotChapterInsertPayload):
    """Insert a new chapter into the plot outline after specified index."""
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    try:
        version = db.insert_plot_chapter(novel_id, payload.insert_after_index, payload.new_chapter)
        return {"status": "success", "version": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# VOLUME MANAGEMENT ENDPOINTS
# =============================================================================
class VolumeCreatePayload(BaseModel):
    title: str
    summary: Optional[str] = ""
    factions: Optional[str] = ""
    chapter_count: Optional[int] = 50

@app.post("/api/novels/{novel_id}/volumes/{vol_idx}")
def api_create_volume(novel_id: str, vol_idx: int, payload: VolumeCreatePayload):
    """Create or update a volume, supporting the factions field."""
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    vols = db.get_volumes(novel_id)
    existing_vol = next((v for v in vols if v.get("volume_index") == vol_idx), None)
    
    if existing_vol:
        # Update existing volume fields
        existing_vol["title"] = payload.title
        existing_vol["summary"] = payload.summary or ""
        existing_vol["factions"] = payload.factions or ""
        existing_vol["chapter_count"] = payload.chapter_count or 50
        volume_data = existing_vol
    else:
        # Create new volume
        new_vol = {
            "id": str(uuid.uuid4()),
            "volume_index": vol_idx,
            "title": payload.title,
            "summary": payload.summary or "",
            "factions": payload.factions or "",
            "chapter_count": payload.chapter_count or 50
        }
        vols.append(new_vol)
        volume_data = new_vol
        
    vols.sort(key=lambda x: x.get("volume_index", 0))
    db.save_volumes(novel_id, vols)
    return {"status": "success", "volume": volume_data}

@app.delete("/api/novels/{novel_id}/volumes/{vol_idx}")
def api_delete_volume(novel_id: str, vol_idx: int):
    """Delete a volume, sequentially renumber the remaining volumes, delete its chapters, and renumber remaining chapters."""
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    vols = db.get_volumes(novel_id)
    
    # Get the chapter range for this volume to determine which chapters belong to it
    range_start, range_end = db.get_volume_chapter_range(vols, vol_idx)
    
    # Filter out the volume from volumes list
    vols = [v for v in vols if v.get("volume_index") != vol_idx]
    # Re-index remaining volumes sequentially starting from 1
    vols.sort(key=lambda x: x.get("volume_index", 0))
    for idx, v in enumerate(vols):
        v["volume_index"] = idx + 1
        
    db.save_volumes(novel_id, vols)
    
    # 1. Also delete chapters in this volume from plot_chapters outline
    plot = db.get_stitched_plot(novel_id)
    if plot and "chapters" in plot:
        plot["chapters"] = [
            ch for ch in plot["chapters"]
            if not (range_start <= (ch.get("chapter_index", 0) or 0) <= range_end)
        ]
        # Re-number remaining chapters in plot outline to be continuous starting from 1
        plot["chapters"].sort(key=lambda x: int(x.get("chapter_index", 0)))
        for idx, ch in enumerate(plot["chapters"]):
            ch["chapter_index"] = idx + 1
            
        db.save_plot_chapters(novel_id, plot)
        
    # 2. Delete corresponding prose chapters in chapters table, and align/renumber the remaining ones
    conn = db.get_db_connection()
    cursor = conn.cursor()
    try:
        # Delete chapters in deleted volume
        cursor.execute("DELETE FROM chapters WHERE novel_id = ? AND chapter_index BETWEEN ? AND ?", (novel_id, range_start, range_end))
        
        # Select all remaining chapters and update their indexes to be continuous
        rows = cursor.execute("SELECT id, chapter_index FROM chapters WHERE novel_id = ? ORDER BY chapter_index ASC", (novel_id,)).fetchall()
        for new_idx, row in enumerate(rows):
            cursor.execute("UPDATE chapters SET chapter_index = ? WHERE id = ?", (new_idx + 1, row["id"]))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed to align SQLite chapters on delete: {e}")
    finally:
        conn.close()
    
    return {"status": "success"}

@app.post("/api/novels/{novel_id}/volumes/{vol_idx}/align")
def api_align_volume(novel_id: str, vol_idx: int):
    """
    Align chapters within a volume - renumber chapters based on volume position.
    """
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    # Re-number chapters in this volume
    plot = db.get_stitched_plot(novel_id)
    if plot and "chapters" in plot:
        vol_chapters = [ch for ch in plot["chapters"] if ch.get("volume_index", 0) == vol_idx]
        vol_chapters.sort(key=lambda x: x.get("chapter_in_volume", 0))
        
        for idx, ch in enumerate(vol_chapters):
            ch["chapter_in_volume"] = idx + 1
        
        db.save_plot_chapters(novel_id, plot)
    
    return {"status": "success"}

# =============================================================================
# NOVEL EXPORT ---
from fastapi.responses import Response
from urllib.parse import quote

@app.get("/api/novels/{novel_id}/export")
def api_export_novel(novel_id: str, format: str = "txt"):
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
        
    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    plot_data = db.get_stitched_plot(novel_id)
    plot = {"parsed_data": plot_data} if plot_data else None
    chapters = db.get_all_chapters_latest(novel_id)
    
    title = novel.get("title", "未命名小說")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設風格")
    
    if format == "txt":
        content = f"《{title}》\n"
        content += f"題材：{genre}\n"
        content += f"風格基調：{style}\n"
        content += "=========================================\n\n"
        
        # Build chapter titles mapping from plot
        chapter_titles = {}
        if plot and plot.get("parsed_data") and "chapters" in plot["parsed_data"]:
            for c in plot["parsed_data"]["chapters"]:
                if "chapter_index" in c:
                    chapter_titles[c["chapter_index"]] = c.get("chapter_title", "").strip()

        if not chapters:
            content += "（正文尚無章節內容）\n"
        else:
            sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
            for ch in sorted_ch:
                idx = ch.get("chapter_index", 0)
                real_title = chapter_titles.get(idx, "")
                
                if real_title and real_title != f"第 {idx} 章" and real_title != f"第{idx}章":
                    ch_title = f"第 {idx} 章：{real_title}"
                else:
                    ch_title = f"第 {idx} 章"
                    
                content += f"【{ch_title}】\n\n"
                content += f"{ch.get('content', '')}\n\n"
                content += "-----------------------------------------\n\n"
                
        filename = f"{title}_完整正文.txt"
        headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"}
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)
        
    elif format == "markdown":
        content = f"# 《{title}》\n\n"
        content += f"- **題材**: {genre}\n"
        content += f"- **風格基調**: {style}\n\n"
        content += "---\n\n"
        content += "## 📖 世界觀與核心設定\n\n"
        content += f"{wb['content'] if wb else '*尚無設定*'}\n\n"
        content += "---\n\n"
        content += "## 👥 角色聖經 (Character Bible)\n\n"
        content += f"{char['json_data'] if char else '*尚無角色設定*'}\n\n"
        content += "---\n\n"
        content += "## 🗺️ 劇情章節大綱\n\n"
        content += f"{json.dumps(plot['parsed_data'], ensure_ascii=False, indent=2) if plot else '*尚無章節大綱*'}\n\n"
        content += "---\n\n"
        content += "## 📝 小說完整正文\n\n"
        
        # Build chapter titles mapping from plot
        chapter_titles = {}
        if plot and plot.get("parsed_data") and "chapters" in plot["parsed_data"]:
            for c in plot["parsed_data"]["chapters"]:
                if "chapter_index" in c:
                    chapter_titles[c["chapter_index"]] = c.get("chapter_title", "").strip()
        
        if not chapters:
            content += "*尚未撰寫任何章節*\n\n"
        else:
            sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
            for ch in sorted_ch:
                idx = ch.get("chapter_index", 0)
                real_title = chapter_titles.get(idx, "")
                
                if real_title and real_title != f"第 {idx} 章" and real_title != f"第{idx}章":
                    ch_title = f"第 {idx} 章：{real_title}"
                else:
                    ch_title = f"第 {idx} 章"
                    
                content += f"### {ch_title}\n\n"
                content += f"{ch.get('content', '')}\n\n"
                
        filename = f"{title}_小說設定與全書正文.md"
        headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"}
        return Response(content=content, media_type="text/markdown; charset=utf-8", headers=headers)


# --- ROUND-TABLE RETROSPECTIVE AND HEAL ROLLBACK ---
import concurrent.futures
import re

@app.post("/api/novels/{novel_id}/retrospective")
def api_novel_retrospective(novel_id: str):
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
    
    context = {
        "worldbuilding": wb["content"] if wb else "尚無世界觀設定",
        "characters": char["json_data"] if char else "尚無角色設定",
        "plot": stitched_plot if stitched_plot else {"chapters": []},
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
        final_markdown += f"## 👥 {agent_display_name} 的復盤心得\n\n{val}\n\n---\n\n"
        
    gold_rules_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_rules")
    os.makedirs(gold_rules_dir, exist_ok=True)
    safe_title = re.sub(r'[\\/*?:"<>|]', "", novel["title"]) or "novel"
    filepath = os.path.join(gold_rules_dir, f"{safe_title}_retrospective_gold_rules.md")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_markdown)
        
    return {
        "status": "success",
        "filepath": filepath,
        "markdown": final_markdown
    }

@app.post("/api/novels/{novel_id}/chapters/heal-rollback")
def api_heal_rollback(novel_id: str, payload: HealRollbackPayload):
    """
    Removes surrounding chapters +/-3 of target_chapter_index and aligns indexes.
    """
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
        
    # Standard DB operation inside transaction (clean up surrounding 3 chapters)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    try:
        start_del = max(1, payload.target_chapter_index - 3)
        end_del = payload.target_chapter_index + 3
        
        cursor.execute("DELETE FROM chapters WHERE novel_id = ? AND chapter_index BETWEEN ? AND ?", (novel_id, start_del, end_del))
        conn.commit()
        return {"status": "success", "start_del": start_del, "end_del": end_del}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



class ForeshadowingOrchestratorRequest(BaseModel):
    novel_id: str
    user_prompt: Optional[str] = None

@app.post("/api/agent/foreshadowing-orchestrator")
@app.post("/api/agent/foreshadowing-orchestrate")
def api_agent_foreshadowing_orchestrator(payload: ForeshadowingOrchestratorRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.safe_generator_wrapper(agents.run_foreshadowing_orchestrator(
            novel_id=payload.novel_id,
            user_prompt=payload.user_prompt
        )),
        media_type="text/event-stream"
    )


# --- STATIC CONTENT HOSTING ---
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "AI Novel Factory UI files missing from /static"}

app.mount("/", StaticFiles(directory=static_dir), name="static")


