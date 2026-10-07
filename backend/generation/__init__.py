"""Generation-task routing and orchestration package."""

from backend.generation.routing.schema import (
    GenerationTaskRequest,
    GenerationTaskResponse,
    GenerationTaskOptions,
    GenerationTaskTarget,
    GenerationTaskFrontendState,
    GenerationPostProcessResult,
    coerce_generation_task_request,
)
from backend.generation.orchestration.context_builder import build_generation_context
from backend.generation.routing.router import execute_generation_task, resolve_generation_route, run_routed_generation, stream_generation_task
from backend.generation.routing.validator import prepare_generation_task, resolve_generation_task_target, validate_generation_task_request

# Modular topological generation subsystems
from backend.generation.core import (
    TOPO_STAGE_ORDER,
    STAGE_ALIASES,
    normalize_stage_name,
    compute_dynamic_acts,
    get_stage_prerequisites,
    GateResult,
    DirectorArbitration,
    evaluate_stage_rigid_gate,
)
from backend.generation.modules import (
    build_narrative_scale_spec,
    generate_planning_blueprint,
    bind_entities_and_foreshadowings,
    materialize_formal_geometry,
)
from backend.generation.director import (
    arbitrate_director_decision,
    heal_geometry_stalemate,
    heal_missing_volumes,
)

