# -*- coding: utf-8 -*-
"""Central JSON output prompt builders for generation agents.

Role prompts describe what an agent should create. This module describes the
machine-readable JSON shape that the backend parser expects.
"""

from backend.schemas import agent_json
from backend.prompts.output_contracts import STRICT_JSON_KEY_CONTRACT, format_json_schema_prompt


SCHEMA_STAGE_MAP = {
    "worldview": "worldview",
    "worldview_core": "worldview_core",
    "multi_act_structure": "multi_act_structure",
    "progressive_character_plan": "progressive_character_plan",
    "foreshadowing": "foreshadowing",
    "character": "characters",
    "characters": "characters",
    "volumes": "volumes",
    "skeleton": "volume_skeleton",
    "volume_skeleton": "volume_skeleton",
    "writer": "writer",
    "editor": "editor",
}


CRITERIA_STAGE_MAP = {
    "worldview_core": "worldview",
    "multi_act_structure": "worldview",
    "progressive_character_plan": "worldview",
    "skeleton": "volume_skeleton",
    "character": "characters",
}


def get_json_schema_prompt_snippet(schema_name):
    """Return canonical output schema + approval criteria from agent_json.py."""
    stage_name = SCHEMA_STAGE_MAP.get(schema_name, schema_name)
    criteria_stage = CRITERIA_STAGE_MAP.get(schema_name, stage_name)
    return (
        f"{STRICT_JSON_KEY_CONTRACT}\n"
        f"{agent_json.format_output_schema_for_prompt(stage_name, label=schema_name)}\n"
        f"{agent_json.format_criteria_for_prompt(criteria_stage)}"
    )
