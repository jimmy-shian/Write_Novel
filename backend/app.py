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
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import os

# Import route modules
from backend.api import novels, settings, export, volume_routes, diagnostics_routes

# Initialize database (must happen before routes)
from backend import db
db.db_init()

app = FastAPI(title="AI Novel Factory API", version="3.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(novels.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(volume_routes.router, prefix="/api")
app.include_router(diagnostics_routes.router, prefix="/api")

# --- GENERATION TASK ENDPOINT (kept inline for now as core feature) ---
@app.post("/api/generation-task")
def api_generation_task(payload: dict = Body(...)):
    from backend.generation import coerce_generation_task_request, execute_generation_task, stream_generation_task
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    try:
        task = coerce_generation_task_request(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not db.get_novel(task.novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        if task.options.stream:
            return StreamingResponse(
                stream_generation_task(task),
                media_type="text/event-stream",
            )
        response = execute_generation_task(task)
        return response.dict() if hasattr(response, "dict") else response
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- STATIC CONTENT HOSTING ---
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "static")

@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    return {"message": "AI Novel Factory UI files missing from /static"}

app.mount("/", StaticFiles(directory=static_dir), name="static")