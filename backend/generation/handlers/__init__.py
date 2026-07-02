"""Stage-specific handler wrappers for unified generation-task routing."""

from __future__ import annotations

from .characters_handler import run_characters_task
from .director_handler import run_director_task
from .editor_handler import run_editor_task
from .foreshadowing_handler import run_foreshadowing_task
from .volumes_handler import run_volumes_task
from .volume_skeleton_handler import run_volume_skeleton_task
from .worldview_handler import run_worldview_task
from .writer_handler import run_writer_task

HANDLER_REGISTRY = {
    "worldview": run_worldview_task,
    "characters": run_characters_task,
    "foreshadowing": run_foreshadowing_task,
    "volumes": run_volumes_task,
    "volume_skeleton": run_volume_skeleton_task,
    "writer": run_writer_task,
    "editor": run_editor_task,
    "evaluate": run_director_task,
}

