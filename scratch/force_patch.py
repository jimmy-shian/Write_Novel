import os
import json

app_path = "app.py"
old_path = "app.py.old"

# 1. Read existing content
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 2. Modify PlotPlannerRequest
old_plot_request = """class PlotPlannerRequest(BaseModel):
    novel_id: str
    user_prompt: Optional[str] = None
    planner_directive: Optional[str] = None"""

new_plot_request = """class PlotPlannerRequest(BaseModel):
    novel_id: str
    chapter_index: Optional[int] = None
    user_prompt: Optional[str] = None
    planner_directive: Optional[str] = None"""

content = content.replace(old_plot_request, new_plot_request)

# 3. Modify DirectorDecisionRequest
old_director_request = """class DirectorDecisionRequest(BaseModel):
    current_stage: str
    user_prompt: Optional[str] = None"""

new_director_request = """class DirectorDecisionRequest(BaseModel):
    current_stage: str
    user_prompt: Optional[str] = None
    chapter_index: Optional[int] = None"""

content = content.replace(old_director_request, new_director_request)

# 4. Modify api_agent_plot_planner call
old_planner_call = """@app.post("/api/agent/plot-planner")
def api_agent_plot_planner(payload: PlotPlannerRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.run_plot_planner(
            novel_id=payload.novel_id,
            user_prompt=payload.user_prompt,
            planner_directive=payload.planner_directive
        ),
        media_type="text/event-stream"
    )"""

new_planner_call = """@app.post("/api/agent/plot-planner")
def api_agent_plot_planner(payload: PlotPlannerRequest):
    if not db.get_novel(payload.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    return StreamingResponse(
        agents.run_plot_planner(
            novel_id=payload.novel_id,
            chapter_index=payload.chapter_index,
            user_prompt=payload.user_prompt,
            planner_directive=payload.planner_directive
        ),
        media_type="text/event-stream"
    )"""

content = content.replace(old_planner_call, new_planner_call)

# 5. Modify api_director_decision call
old_decision_call = """@app.post("/api/novels/{novel_id}/director-decision")
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
            }, ensure_ascii=False) + "\\n\\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\\n\\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    return StreamingResponse(
        agents.run_director_decision(novel_id, payload.current_stage, effective_prompt),
        media_type="text/event-stream"
    )"""

new_decision_call = """@app.post("/api/novels/{novel_id}/director-decision")
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
            }, ensure_ascii=False) + "\\n\\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\\n\\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    return StreamingResponse(
        agents.run_director_decision(novel_id, payload.current_stage, effective_prompt, chapter_index=payload.chapter_index),
        media_type="text/event-stream"
    )"""

content = content.replace(old_decision_call, new_decision_call)

# Windows Rename Bypass
if os.path.exists(old_path):
    os.remove(old_path)
os.rename(app_path, old_path)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

os.remove(old_path)
print("App forced patched successfully!")
