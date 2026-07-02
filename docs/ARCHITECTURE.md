# AI Novel Factory - Architecture Documentation

## 1. Official Generation Flow

The **only official generation flow** is the `backend/generation/` package:

```
Frontend (frontend/static/generation/generationTaskClient.js)
    → FastAPI endpoint: POST /api/generation-task (backend/app.py)
        → backend/generation/task_router.py:resolve_generation_route()
            → backend/generation/handlers/*.py (per-stage handlers)
                → backend/generation/agent_runners.py (actual agent run functions)
                    → backend/prompts/prompt_builder.py (prompt assembly)
                    → backend/schemas/validation.py / backend/schemas/agent_json.py (validation & schemas)
                    → backend/db.py (database layer)
                    → backend/llm.py (LLM streaming calls)
```

### Key Components

| File | Role |
|------|------|
| `backend/generation/task_router.py` | Route incoming tasks to correct handler, manage pipeline lock, post-process SSE |
| `backend/generation/task_schema.py` | Dataclasses for request/response validation |
| `backend/generation/task_validator.py` | Validate and coerce incoming JSON to `GenerationTaskRequest` |
| `backend/generation/stage_registry.py` | Stage ordering, aliases, scope/task-type normalization |
| `backend/generation/handlers/*.py` | 8 handlers: worldview, characters, foreshadowing, volumes, volume_skeleton, writer, editor, evaluate |
| `backend/generation/agent_runners.py` | Actual generator functions: `run_story_architect`, `run_character_designer`, `run_volumes_planner`, `run_volume_skeleton_planner`, `run_chapter_writer`, `run_editor_agent`, `run_foreshadowing_orchestrator`, `run_director_decision` |
| `backend/generation/context_builder.py` | Build context bundle (worldview, characters, plot, allocations) for handlers |
| `backend/generation/lock_manager.py` | Pipeline lock context manager using `db.pipeline_locks` table |

---

## 2. Legacy: `agents.py` Removed

- **File**: `agents.py` was the old monolithic pipeline runner (~1466 lines)
- **Status**: Moved to `_archive/legacy/agents.py`
- **No longer imported** by any runtime code
- **All its functions** are now in `backend/generation/agent_runners.py` (used by handlers only)
- **Old FastAPI endpoints** that used `agents.run_*` directly have been removed from `app.py`

---

## 3. FastAPI Generation Endpoint

**Single unified endpoint**: `POST /api/generation-task`

```json
{
  "novel_id": "uuid",
  "stage": "worldview|characters|foreshadowing|volumes|volume_skeleton|writer|editor|evaluate",
  "task_type": "generate|regenerate|patch|batch_generate|refine|evaluate",
  "scope": "global|volume|chapter|section|selection",
  "instruction": "user prompt",
  "hint": "director hint",
  "target": { "volume_index": 1, "chapter_index": 5, "selection": [...] },
  "options": { "stream": true, "batch": false, "overwrite": false }
}
```

- Streaming: `stream=true` → returns `text/event-stream` (SSE)
- Non-streaming: `stream=false` → returns `GenerationTaskResponse` JSON

---

## 4. Frontend Entry Point

**File**: `frontend/static/generation/generationTaskClient.js`

Exports `submitGenerationTask(payload, callbacks)` which:
- POSTs to `/api/generation-task`
- Handles SSE streaming with auto-retry (10x)
- Parses events: `thinking`, `content`, `reset`, `status`, `error`, `done`
- Calls back: `onThinking`, `onContent`, `onError`, `onDone`, `onRetrying`, `onEvent`

**Legacy frontend files** (still present but no longer used for generation):
- `frontend/static/pipeline.js` — legacy director pipeline orchestration (uses old `/api/agent/*` endpoints)
- `frontend/static/agentProcessing.js` — legacy SSE terminal display
- `frontend/static/api.js` — legacy `streamAPI` / `requestAPI` (used by `pipeline.js`)
- `frontend/static/app.js` — legacy main controller (uses EventSource GET SSE, deprecated)

---

## 5. Database Layer

**Single DB module**: `backend/db.py` (SQLite + WAL mode, versioned tables)

**Tables**:
- `novels` — novel metadata
- `worldbuilding` — versioned worldview JSON/text
- `characters` — versioned character bible JSON
- `plot_chapters` — versioned stitched plot outlines
- `chapters` — versioned chapter prose (with `synopsis`, `thinking`, `is_dirty`)
- `volumes` — volume metadata + `chapters_outline` (skeleton JSON)
- `chat_memory` — conversation history
- `agent_configs` — per-agent LLM config (synced from `.env` on init)
- `foreshadowing_blueprints` — precomputed global foreshadowing allocations
- `pipeline_locks` — concurrency control for generation pipeline
- `chapters_backup` — 24h backup for wipe protection
- `last_agent_run` — debug/trace of last agent I/O
- `prompt_overrides` — user prompt template overrides

**Legacy `db/` package** (connection.py, queries.py) — different schema, **moved to `_archive/incomplete_db_package/`**

---

## 6. Project Structure

```
Write_Novel/
├── backend/                    # All Python code
│   ├── app.py                  # FastAPI app init, middleware, router inclusion
│   ├── config.py               # Constants (MAX_AUTO_LOOPS, batch sizes, etc.)
│   ├── llm.py                  # call_llm_stream(), agent config from .env
│   ├── utils.py                # Shared helpers (StreamAccumulator, deep_merge_dict, etc.)
│   ├── db.py                   # SQLite database layer (single source of truth)
│   ├── api/                    # Route modules
│   │   ├── __init__.py
│   │   ├── novels.py           # Novel CRUD + manual save overrides + JSON adjust
│   │   ├── settings.py         # Settings snapshot & patch
│   │   ├── export.py           # Novel export (txt/markdown)
│   │   ├── volume_routes.py    # Volume management (create/delete/align)
│   │   └── diagnostics_routes.py # Retrospective, heal-rollback, pipeline-status, bodystop
│   ├── schemas/                # Schema/validation modules
│   │   ├── agent_json.py       # JSON schemas for worldview/characters/plot
│   │   ├── validation.py       # Schema validation functions
│   │   └── constraints.py      # Gold rules loading
│   ├── prompts/                # Prompt templates + builders
│   │   ├── __init__.py
│   │   ├── prompt_main.py      # Main prompt constants
│   │   ├── prompt_builder.py   # Prompt assembly functions
│   │   ├── prompt_detail_modifier.py # Incremental/edit prompts
│   │   ├── prompt_instructions.py  # Director/copilot prompts
│   │   └── prompt_manager.py   # Prompt override DB helpers
│   ├── services/               # Business logic services
│   │   ├── director_context.py     # Director context builders
│   │   ├── director_tools.py       # Director tool invocations
│   │   ├── diagnostics.py          # Rigid validation reports
│   │   ├── incremental_patch_engine.py # Incremental JSON patch/merge
│   │   ├── retry_handler.py        # Retry utilities
│   │   ├── compactor.py            # Context compaction
│   │   └── settings_service.py     # Settings snapshot & patch API
│   ├── models/                 # Data models + parsing
│   │   ├── parsers.py              # JSON extraction/validation
│   │   └── client.py               # LLM client wrapper
│   └── generation/             # NEW OFFICIAL FLOW
│       ├── __init__.py
│       ├── task_router.py
│       ├── task_schema.py
│       ├── task_validator.py
│       ├── stage_registry.py
│       ├── context_builder.py
│       ├── lock_manager.py
│       ├── post_processor.py
│       ├── response_builder.py
│       ├── agent_runners.py      # ← extracted from old agents.py
│       └── handlers/             # 8 stage handlers
│           ├── __init__.py
│           ├── worldview_handler.py
│           ├── characters_handler.py
│           ├── foreshadowing_handler.py
│           ├── volumes_handler.py
│           ├── volume_skeleton_handler.py
│           ├── writer_handler.py
│           ├── editor_handler.py
│           └── director_handler.py
├── frontend/                   # All frontend assets
│   ├── static/
│   │   ├── index.html
│   │   ├── style.css, index.css
│   │   ├── favicon.png
│   │   ├── app.js, main.js       # Legacy entry points
│   │   ├── core/                 # Leaf utilities (no imports)
│   │   │   ├── state.js
│   │   │   ├── dom.js
│   │   │   ├── toast.js
│   │   │   └── utils.js
│   │   ├── api/                  # API wrapper
│   │   │   └── api.js
│   │   ├── pipeline/             # Pipeline orchestration
│   │   │   ├── pipeline.js
│   │   │   ├── agentProcessing.js
│   │   │   └── status_panel.js
│   │   ├── ui/                   # UI rendering modules
│   │   │   ├── renderers.js
│   │   │   ├── settings.js
│   │   │   └── novelLifecycle.js
│   │   └── generation/           # NEW OFFICIAL CLIENT
│   │       ├── generationTaskClient.js
│   │       ├── generationSseHandler.js
│   │       ├── generationStateMapper.js
│   │       ├── generationResultApplier.js
│   │       └── generationTaskSchema.js
├── scripts/                      # Python maintenance scripts
│   ├── clear_generated_content.py
│   └── export_novel.py
├── data/                         # Runtime data files
│   ├── novel_factory.db
│   ├── novels.db
│   └── gold_rules/
├── docs/
│   ├── ARCHITECTURE.md           # THIS FILE
│   ├── DEVELOPER_GUIDE.md
│   ├── USER_GUIDE.md
│   └── archive/
│       ├── ORIGINAL_REQUEST.md
│       ├── PROJECT.md
│       └── TEST_INFRA.md
├── _archive/                     # Legacy/unused code
│   ├── legacy/agents.py
│   ├── incomplete_db_package/
│   ├── scratch/
│   └── tools/
├── README.md
├── USER_GUIDE.md
├── DEVELOPER_GUIDE.md
└── .env
```

---

## 7. Startup & Testing

```bash
# Compile check
python -m py_compile backend/app.py
python -m py_compile backend/generation/task_router.py
python -m py_compile backend/generation/stage_registry.py
python -m py_compile backend/generation/task_schema.py
python -m py_compile backend/generation/task_validator.py

# Full compile
python -m compileall backend/

# Start server
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 8. Key Design Principles

1. **Single generation flow** — Only `backend/generation/` is the runtime path
2. **No dual entry points** — `agents.py` is archived; `app.py` has no old `/api/agent/*` routes
3. **Unified DB** — Only `backend/db.py`; `db/` package archived
4. **Clean separation** — `backend/` for Python, `frontend/` for JS/CSS/HTML, `data/` for runtime data
5. **Documentation consistency** — This file is the source of truth for architecture