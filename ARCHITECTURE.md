# AI Novel Factory - Architecture

## Runtime Flow

```text
Frontend
  -> POST /api/generation-task
  -> backend.app
  -> backend.generation.routing.router
  -> backend.generation.handlers
  -> backend.agents.<agent>.runner
  -> backend.agents.<agent>.prompts
  -> backend.persistence.repositories
  -> backend.common.llm
```

The backend no longer uses monolithic runtime modules such as `backend/db.py`,
`backend/llm.py`, `backend/utils.py`, `backend/config.py`,
`backend/generation/agent_runners.py`, or `backend/prompts/prompt_builder.py`.
Those modules were removed and their code now lives in domain packages.

## Backend Map

```text
backend/
├── agents/
│   ├── shared/                       # cross-agent SSE/context/tool helpers
│   ├── story_architect/              # worldview architecture runner + prompts
│   ├── character_designer/           # character runner + prompts
│   ├── foreshadowing_orchestrator/   # foreshadowing runner + prompts
│   ├── volumes_planner/              # volume plan runner + prompts
│   ├── volume_skeleton/              # skeleton full/segment/completion runners
│   ├── chapter_writer/               # chapter prose runner + prompts
│   ├── editor/                       # editor runner + prompts
│   ├── director/                     # director decision runner + prompts
│   ├── copilot/                      # copilot chat runner + prompts
│   └── incremental/                  # incremental update runners + prompts
├── api/
│   ├── novels/routes.py
│   ├── settings/routes.py
│   ├── export/routes.py
│   ├── volumes/routes.py
│   └── diagnostics/routes.py
├── common/
│   ├── config.py                     # shared constants
│   ├── llm.py                        # LLM transport/config resolution
│   └── utils.py                      # shared utilities
├── generation/
│   ├── routing/
│   │   ├── router.py
│   │   ├── schema.py
│   │   ├── validator.py
│   │   └── stage_registry.py
│   ├── orchestration/
│   │   ├── context_builder.py
│   │   ├── lock_manager.py
│   │   ├── post_processor.py
│   │   └── response_builder.py
│   └── handlers/                     # stage-to-agent adapters
├── persistence/
│   ├── connection.py
│   ├── schema.py
│   └── repositories/
│       ├── agent_runs.py
│       ├── chapters.py
│       ├── characters.py
│       ├── foreshadowing.py
│       ├── novels.py
│       ├── pipeline_locks.py
│       ├── volumes.py
│       └── worldbuilding.py
├── prompts/
│   ├── common/context.py             # shared prompt context helpers
│   ├── output_contracts.py
│   ├── prompt_detail_modifier.py
│   ├── prompt_instructions.py
│   ├── prompt_main.py
│   └── prompt_manager.py
├── schemas/
├── services/
│   ├── diagnostics/report.py
│   ├── director/
│   │   ├── context.py
│   │   ├── tools.py
│   │   └── tool_registry/
│   ├── foreshadowing/
│   │   ├── blueprint.py
│   │   └── chapter_math.py
│   ├── incremental_patch/engine.py
│   └── settings/service.py
└── app.py
```

## Ownership Rules

- Agent-specific runner logic belongs in `backend/agents/<agent>/runner.py`.
- Agent-specific prompt builders belong in `backend/agents/<agent>/prompts.py`.
- Shared prompt context selection belongs in `backend/prompts/common/context.py`.
- Database code belongs in `backend/persistence/repositories/*`.
- Generation request validation and routing belong in `backend/generation/routing`.
- Generation context, locking, response shaping, and post-processing belong in
  `backend/generation/orchestration`.
- Director tools belong in `backend/services/director`.

## Verification

```powershell
python -m compileall backend
python - <<'PY'
import importlib
for mod in [
    "backend.app",
    "backend.generation.routing.router",
    "backend.generation.handlers",
    "backend.services.director.tools",
]:
    importlib.import_module(mod)
    print("OK", mod)
PY
```

Run the application:

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
