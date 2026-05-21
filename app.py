from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any
import uuid
import os
import json

from db import (
    db_init,
    create_novel,
    get_novel,
    list_novels,
    delete_novel,
    get_latest_worldbuilding,
    get_latest_characters,
    get_latest_plot_chapters,
    get_latest_chapter,
    get_all_chapters_latest,
    get_chat_memory,
    clear_chat_memory,
    save_worldbuilding,
    save_characters,
    save_plot_chapters,
    save_chapter,
    get_agent_configs,
    save_agent_config,
    append_foreshadowing,
    insert_plot_chapter,
    update_character_single_field,
    parse_worldview_to_json
)

from agents import (
    run_story_architect,
    run_character_designer,
    run_plot_planner,
    run_chapter_writer,
    run_editor_agent,
    run_copilot_chat,
    run_director_decision,
    set_director_auto_execute,
    set_director_user_prompt,
    get_director_auto_execute
)
# 增量生成 Agent
from agents_incremental import (
    run_incremental_architect,
    run_incremental_character_designer,
    run_incremental_plot_planner
)
from llm import get_config_for_agent, get_default_config
from db import AGENT_DEFAULTS



# Agent friendly names for frontend display
AGENT_DISPLAY_NAMES = {
    "global": "Global 全域 (預設設置)",
    "architect": "1️⃣ Story Architect (故事結構架構師)",
    "character": "2️⃣ Character Designer (角色設計大師)",
    "plot": "3️⃣ Plot Planner (章節劇情規劃師)",
    "writer": "4️⃣ Chapter Writer (小說正文寫作作家)",
    "editor": "5️⃣ Editor Agent (精緻文風編輯)",
    "copilot": "🧠 Co-Pilot Orchestrator (AI 總監)"
}

# Initialize database
db_init()

app = FastAPI(title="AI Novel Factory API", version="1.0.0")

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

# --- NOVELS ROUTES ---
@app.get("/api/novels")
def api_list_novels():
    return list_novels()

@app.post("/api/novels")
def api_create_novel(novel: NovelCreate):
    novel_id = str(uuid.uuid4())
    create_novel(novel_id, novel.title, novel.genre, novel.style)
    return {"status": "success", "novel_id": novel_id}

@app.get("/api/novels/{novel_id}")
def api_get_novel(novel_id: str):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
        
    wb = get_latest_worldbuilding(novel_id)
    char = get_latest_characters(novel_id)
    plot = get_latest_plot_chapters(novel_id)
    written_ch = get_all_chapters_latest(novel_id)
    memory = get_chat_memory(novel_id, limit=30)
    
    return {
        "novel": novel,
        "worldbuilding": wb["content"] if wb else "",
        "worldbuilding_version": wb["version"] if wb else 0,
        "characters": char["parsed_data"] if char else None,
        "characters_raw": char["json_data"] if char else "",
        "characters_version": char["version"] if char else 0,
        "plot": plot["parsed_data"] if plot else None,
        "plot_raw": plot["outline_json"] if plot else "",
        "plot_version": plot["version"] if plot else 0,
        "chapters": written_ch,
        "chat_memory": memory
    }

@app.delete("/api/novels/{novel_id}")
def api_delete_novel(novel_id: str):
    delete_novel(novel_id)
    return {"status": "success"}

# --- MANUAL SAVE OVERRIDES ---
@app.post("/api/novels/{novel_id}/worldbuilding")
def api_save_worldbuilding(novel_id: str, payload: WorldbuildingSave):
    v = save_worldbuilding(novel_id, payload.content)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/characters")
def api_save_characters(novel_id: str, payload: CharactersSave):
    # Payload can be JSON object or string
    v = save_characters(novel_id, payload.json_data)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/plot")
def api_save_plot(novel_id: str, payload: PlotSave):
    v = save_plot_chapters(novel_id, payload.outline_json)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/chapters/{chapter_index}")
def api_save_chapter(novel_id: str, chapter_index: int, payload: ChapterSave):
    v = save_chapter(novel_id, chapter_index, payload.content)
    return {"status": "success", "version": v}

@app.post("/api/novels/{novel_id}/clear-chat")
def api_clear_chat(novel_id: str):
    clear_chat_memory(novel_id)
    return {"status": "success"}

class PipelinePromptSave(BaseModel):
    pipeline_prompt: str

@app.post("/api/novels/{novel_id}/pipeline-prompt")
def api_save_pipeline_prompt(novel_id: str, payload: PipelinePromptSave):
    """Save the user's last pipeline orchestration prompt for memory"""
    from db import update_novel_pipeline_prompt
    update_novel_pipeline_prompt(novel_id, payload.pipeline_prompt)
    return {"status": "success"}

@app.get("/api/novels/{novel_id}/pipeline-prompt")
def api_get_pipeline_prompt(novel_id: str):
    """Get the user's last pipeline orchestration prompt"""
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return {"pipeline_prompt": novel.get("pipeline_prompt", "")}

# --- DIRECTOR PIPELINE STAGES ENDPOINT ---
@app.post("/api/novels/{novel_id}/director-decision")
def api_director_decision(novel_id: str, current_stage: str = Body(...), user_prompt: str = Body(...)):
    """
    The Director (Copilot) evaluates whether to proceed to the next stage.
    Returns a decision with reasoning about whether to continue, skip, or adjust.
    """
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_director_decision(novel_id, current_stage, user_prompt),
        media_type="text/event-stream"
    )

# --- AGENT STREAMING ACTIONS ---
@app.post("/api/agent/story-architect")
def api_agent_story_architect(novel_id: str = Body(...), user_prompt: str = Body(...)):
    # Verify novel exists
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_story_architect(novel_id, user_prompt),
        media_type="text/event-stream"
    )

@app.post("/api/agent/character-designer")
def api_agent_character_designer(novel_id: str = Body(...), user_prompt: Optional[str] = Body(None)):
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_character_designer(novel_id, user_prompt),
        media_type="text/event-stream"
    )

@app.post("/api/agent/plot-planner")
def api_agent_plot_planner(novel_id: str = Body(...), user_prompt: Optional[str] = Body(None)):
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_plot_planner(novel_id, user_prompt),
        media_type="text/event-stream"
    )

@app.post("/api/agent/write-chapter")
def api_agent_write_chapter(novel_id: str = Body(...), chapter_index: int = Body(...), custom_style: Optional[str] = Body("Classic Modernism")):
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_chapter_writer(novel_id, chapter_index, custom_style),
        media_type="text/event-stream"
    )

@app.post("/api/agent/edit-chapter")
def api_agent_edit_chapter(novel_id: str = Body(...), chapter_index: int = Body(...), edit_instructions: Optional[str] = Body(None)):
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_editor_agent(novel_id, chapter_index, edit_instructions),
        media_type="text/event-stream"
    )

@app.post("/api/agent/copilot-chat")
def api_agent_copilot_chat(novel_id: str = Body(...), user_message: str = Body(...)):
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_copilot_chat(novel_id, user_message),
        media_type="text/event-stream"
    )

@app.get("/api/settings")
def api_get_settings():
    """
    Returns agent configurations loaded strictly from .env.
    """
    defaults = get_default_config()
    all_agents = ["global", "architect", "character", "plot", "writer", "editor", "copilot"]
    
    merged = {}
    for agent in all_agents:
        # Get config from robust function (strictly from .env/defaults)
        llm_config = get_config_for_agent(agent)
        
        merged[agent] = {
            "api_key": llm_config.get("api_key", ""),
            "base_url": llm_config.get("base_url", defaults["base_url"]),
            "model": llm_config.get("model", ""),
            "temperature": llm_config.get("temperature", defaults["temperature"]),
            "top_p": llm_config.get("top_p", defaults["top_p"]),
            "max_tokens": llm_config.get("max_tokens", defaults["max_tokens"]),
            "enable_thinking": llm_config.get("enable_thinking", defaults["enable_thinking"]),
            "display_name": AGENT_DISPLAY_NAMES.get(agent, agent)
        }
    
    return merged

@app.post("/api/settings")
def api_save_settings(config: AgentConfigSave):
    save_agent_config(
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

# --- EXPORT ROUTE ---
from fastapi.responses import Response
from urllib.parse import quote

@app.get("/api/novels/{novel_id}/export")
def api_export_novel(novel_id: str, format: str = "txt"):
    novel = get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
        
    wb = get_latest_worldbuilding(novel_id)
    char = get_latest_characters(novel_id)
    plot = get_latest_plot_chapters(novel_id)
    chapters = get_all_chapters_latest(novel_id)
    
    title = novel.get("title", "未命名小說")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設風格")
    
    if format == "txt":
        content = f"《{title}》\n"
        content += f"題材：{genre}\n"
        content += f"風格基調：{style}\n"
        content += "=========================================\n\n"
        
        if not chapters:
            content += "（正文尚無章節內容）\n"
        else:
            sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
            for ch in sorted_ch:
                idx = ch.get("chapter_index", 0)
                ch_title = f"第 {idx} 章"
                if plot and plot.get("parsed_data"):
                    p_data = plot["parsed_data"]
                    for p_ch in p_data.get("chapters", []):
                        if p_ch.get("chapter_index") == idx:
                            ch_title = f"第 {idx} 章：{p_ch.get('title', '')}"
                            break
                
                content += f"【{ch_title}】\n\n"
                content += f"{ch.get('content', '')}\n\n"
                content += "-----------------------------------------\n\n"
                
        filename = f"{title}_完整正文.txt"
        headers = {
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"
        }
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)
        
    elif format == "markdown":
        content = f"# 《{title}》\n\n"
        content += f"- **題材**: {genre}\n"
        content += f"- **風格基調**: {style}\n\n"
        content += "---\n\n"
        
        content += "## 📖 世界觀與核心設定\n\n"
        if wb and wb.get("content"):
            wb_content = wb['content'].strip()
            if wb_content.startswith("{"):
                try:
                    js = parse_worldview_to_json(wb_content)
                    content += f"### 🎯 核心主題\n{js.get('theme', '')}\n\n"
                    content += f"### 💥 核心衝突\n{js.get('main_conflict', '')}\n\n"
                    content += f"### 🌍 世界觀設定\n{js.get('worldview', '')}\n\n"
                    content += f"### 📋 整體故事大綱\n{js.get('macro_outline', '')}\n\n"
                    
                    three_act = js.get("three_act_structure", [])
                    content += f"### 🎬 三幕式結構\n"
                    if isinstance(three_act, list):
                        for item in three_act:
                            content += f"- **{item.get('title', '')}**: {item.get('content', '')}\n"
                    elif isinstance(three_act, dict):
                        content += f"- **第一幕（Setup）**: {three_act.get('act1_setup', '')}\n"
                        content += f"- **第二幕（Confrontation）**: {three_act.get('act2_confrontation', '')}\n"
                        content += f"- **第三幕（Resolution）**: {three_act.get('act3_resolution', '')}\n"
                    content += "\n"
                    
                    char_plan = js.get("progressive_character_plan", [])
                    content += f"### 📈 角色漸進規劃策略\n"
                    if isinstance(char_plan, list):
                        for item in char_plan:
                            content += f"- **{item.get('title', '')}**: {item.get('content', '')}\n"
                    elif isinstance(char_plan, dict):
                        content += f"- **第一波開篇**: {char_plan.get('wave_1_opening', '')}\n"
                        content += f"- **第二波發展**: {char_plan.get('wave_2_development', '')}\n"
                        content += f"- **第三波高潮**: {char_plan.get('wave_3_climax', '')}\n"
                    content += "\n"
                    
                    seeds = js.get("foreshadowing_seeds", [])
                    content += f"### 🔑 伏筆種子\n"
                    if seeds:
                        for idx, s in enumerate(seeds, 1):
                            content += f"{idx}. {s}\n"
                    else:
                        content += "*尚無伏筆種子*\n"
                    content += "\n"
                    
                    pts = js.get("key_turning_points", [])
                    content += f"### ⚡ 關鍵轉折點\n"
                    if pts:
                        for idx, p in enumerate(pts, 1):
                            content += f"{idx}. {p}\n"
                    else:
                        content += "*尚無關鍵轉折點*\n"
                    content += "\n"
                except Exception as e:
                    content += f"{wb['content']}\n\n"
            else:
                content += f"{wb['content']}\n\n"
        else:
            content += "*尚無設定*\n\n"
            
        content += "---\n\n"
        
        content += "## 👥 角色聖經 (Character Bible)\n\n"
        if char and char.get("parsed_data"):
            c_data = char["parsed_data"]
            for idx, c in enumerate(c_data.get("characters", []), 1):
                content += f"### {idx}. {c.get('name', '未命名')} ({c.get('role', '未知角色')})\n"
                content += f"- **性格特質**: {', '.join(c.get('personality', []))}\n"
                content += f"- **致命弱點**: {', '.join(c.get('flaws', []))}\n"
                content += f"- **核心動機與欲求 (Want)**: {c.get('want', '無')}\n"
                content += f"- **內在深層需求 (Need)**: {c.get('need', '無')}\n"
                content += f"- **個人成長軌跡**: {c.get('arc', '無')}\n"
                content += f"- **背景設定**: {c.get('backstory', '無')}\n\n"
        else:
            content += "*尚無角色設定*\n\n"
            
        content += "---\n\n"
        
        content += "## 🗺️ 劇情章節大綱\n\n"
        if plot and plot.get("parsed_data"):
            p_data = plot["parsed_data"]
            for ch in p_data.get("chapters", []):
                content += f"### 第 {ch.get('chapter_index', 0)} 章：{ch.get('title', '未命名')}\n"
                content += f"- **核心事件**: {ch.get('event', '無')}\n"
                content += f"- **伏筆與鋪墊 (Foreshadowing)**: {ch.get('foreshadowing', '無')}\n"
                content += f"- **涉及角色**: {ch.get('characters_involved', '無')}\n"
                content += f"- **時間與場景**: {ch.get('time_event', '無')}\n\n"
        else:
            content += "*尚無章節大綱*\n\n"
            
        content += "---\n\n"
        
        content += "## 📝 小說完整正文\n\n"
        if not chapters:
            content += "*尚未撰寫任何章節*\n\n"
        else:
            sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
            for ch in sorted_ch:
                idx = ch.get("chapter_index", 0)
                ch_title = f"第 {idx} 章"
                if plot and plot.get("parsed_data"):
                    p_data = plot["parsed_data"]
                    for p_ch in p_data.get("chapters", []):
                        if p_ch.get("chapter_index") == idx:
                            ch_title = f"第 {idx} 章：{p_ch.get('title', '')}"
                            break
                            
                content += f"### {ch_title}\n\n"
                prose_lines = ch.get("content", "").split("\n")
                formatted_prose = "\n\n".join([line.strip() for line in prose_lines if line.strip()])
                content += f"{formatted_prose}\n\n"
                
        filename = f"{title}_小說設定與全書正文.md"
        headers = {
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"
        }
        return Response(content=content, media_type="text/markdown; charset=utf-8", headers=headers)

# --- STATIC CONTENT HOSTING ---
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Mount standard index fallback
@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "AI Novel Factory UI files missing from /static"}

# Mount other static files
app.mount("/", StaticFiles(directory=static_dir), name="static")

# ============================================================
# INCREMENTAL UPDATE API ENDPOINTS (細粒度編輯)
# ============================================================

class ForeshadowingAppend(BaseModel):
    """新增伏筆種子"""
    seed: str

class PlotChapterInsert(BaseModel):
    """在指定位置插入新大綱章節"""
    insert_after_index: int  # 插入到此索引之後（0 表示插入到最前面）
    chapter_data: dict

class CharacterFieldUpdate(BaseModel):
    """更新角色單一欄位"""
    char_index: int
    field_name: str
    new_value: Any

# --- 增量操作端點 ---
@app.post("/api/novels/{novel_id}/worldbuilding/foreshadowing")
def api_append_foreshadowing(novel_id: str, payload: ForeshadowingAppend):
    """增量添加伏筆種子到世界觀（不重新生成全部）"""
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    version = append_foreshadowing(novel_id, payload.seed)
    if version:
        return {"status": "success", "version": version}
    raise HTTPException(status_code=400, detail="Failed to append foreshadowing")

@app.post("/api/novels/{novel_id}/plot/chapters/insert")
def api_insert_plot_chapter(novel_id: str, payload: PlotChapterInsert):
    """在指定位置插入新的大綱章節"""
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    version = insert_plot_chapter(novel_id, payload.insert_after_index, payload.chapter_data)
    if version:
        return {"status": "success", "version": version}
    raise HTTPException(status_code=400, detail="Failed to insert chapter outline")

@app.patch("/api/novels/{novel_id}/characters/field")
def api_update_character_field(novel_id: str, payload: CharacterFieldUpdate):
    """增量更新角色單一欄位（細粒度修改）"""
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    result = update_character_single_field(novel_id, payload.char_index, payload.field_name, payload.new_value)
    if result.get("status") == "success":
        return result
    raise HTTPException(status_code=400, detail=result.get("message", "Failed to update character field"))

# --- 增量生成 Agent 端點 ---
class IncrementalArchitectRequest(BaseModel):
    """增量生成世界觀（局部上下文）"""
    novel_id: str
    target_section: str  # 要生成的部分，如 "foreshadowing_seeds", "three_act_structure"
    user_hint: str       # 用戶的提示

class IncrementalCharacterRequest(BaseModel):
    """增量生成角色（局部上下文）"""
    novel_id: str
    target_char_index: Optional[int] = None  # 要修改的角色索引，None 表示新增
    field_name: Optional[str] = None         # 要修改的欄位，None 表示全部
    user_hint: str                           # 用戶的提示

class IncrementalPlotRequest(BaseModel):
    """增量生成大綱（局部上下文）"""
    novel_id: str
    insert_after_index: int                  # 插入位置
    user_hint: str                           # 用戶的提示

@app.post("/api/agent/incremental-architect")
def api_incremental_architect(payload: IncrementalArchitectRequest):
    """增量生成世界觀的特定部分（不重新生成全部）"""
    novel_id = payload.novel_id
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_incremental_architect(novel_id, payload.target_section, payload.user_hint),
        media_type="text/event-stream"
    )

@app.post("/api/agent/incremental-character")
def api_incremental_character(payload: IncrementalCharacterRequest):
    """增量生成/修改角色（局部上下文）"""
    novel_id = payload.novel_id
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_incremental_character_designer(novel_id, payload.target_char_index, payload.field_name, payload.user_hint),
        media_type="text/event-stream"
    )

@app.post("/api/agent/incremental-plot")
def api_incremental_plot(payload: IncrementalPlotRequest):
    """增量生成大綱章節（局部上下文，可在指定位置插入）"""
    novel_id = payload.novel_id
    if not get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        run_incremental_plot_planner(novel_id, payload.insert_after_index, payload.user_hint),
        media_type="text/event-stream"
    )
