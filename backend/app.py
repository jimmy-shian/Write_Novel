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

# Set console title to the port number on Windows
if sys.platform == 'win32':
    try:
        import ctypes
        port = "8000"  # Default uvicorn port
        for i, arg in enumerate(sys.argv):
            if arg in ("--port", "-p") and i + 1 < len(sys.argv):
                port = sys.argv[i + 1]
                break
        ctypes.windll.kernel32.SetConsoleTitleW(port)
    except Exception:
        pass


from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import os

# Import route modules
from backend.api.novels.routes import router as novels_router
from backend.api.settings.routes import router as settings_router
from backend.api.export.routes import router as export_router
from backend.api.volumes.routes import router as volumes_router
from backend.api.diagnostics.routes import router as diagnostics_router
from backend.api.sync.routes import router as sync_router
from backend.api.autonomous.routes import router as autonomous_router
from backend.api.temporal_graph.routes import router as temporal_graph_router
from backend.api.terms.routes import router as terms_router
from backend.api.proposals.routes import router as proposals_router
from backend.services.hf_sync import restore_database, async_backup, is_hf_sync_available, DB_PATH

# Restore database from Hugging Face Dataset if running in cloud / configured
restore_ok = restore_database(force=False)
if is_hf_sync_available() and not restore_ok:
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        raise RuntimeError(
            "[CRITICAL] Cloud restore failed and no local database exists. "
            "Halting startup to prevent initializing an empty database that would overwrite cloud storage. "
            "Please check HF_TOKEN and storage configuration or network connectivity."
        )

# Initialize database (must happen before routes)
from backend import persistence as db
db.db_init()

from backend.common.version import get_version

app = FastAPI(title="AI Novel Factory API", version=get_version())

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(novels_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(volumes_router, prefix="/api")
app.include_router(diagnostics_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(autonomous_router, prefix="/api")
app.include_router(temporal_graph_router, prefix="/api")
app.include_router(terms_router, prefix="/api")
app.include_router(proposals_router, prefix="/api")

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
            def stream_with_sync():
                try:
                    for chunk in stream_generation_task(task):
                        yield chunk
                finally:
                    async_backup(reason=f"Stage {task.stage} stream finished")

            return StreamingResponse(
                stream_with_sync(),
                media_type="text/event-stream",
            )
        response = execute_generation_task(task)
        async_backup(reason=f"Stage {task.stage} execution finished")
        return response.dict() if hasattr(response, "dict") else response
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- STATIC CONTENT HOSTING ---
base_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
dist_dir = os.path.join(base_frontend_dir, "dist")
legacy_static_dir = os.path.join(base_frontend_dir, "static")

static_dir = dist_dir if (os.path.exists(dist_dir) and os.path.exists(os.path.join(dist_dir, "index.html"))) else legacy_static_dir

@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "AI Novel Factory UI files missing"}

if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir), name="static")