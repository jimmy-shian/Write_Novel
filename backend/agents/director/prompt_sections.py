# -*- coding: utf-8 -*-
"""Prompt sections for the Director decision agent.

Keep the Director contract short, explicit, and separated from stage content.
The model must decide and emit one valid decision envelope; prose review belongs
inside JSON values only.
"""

from backend.prompts.output_contracts import (
    DIRECTOR_DECISION_KEY_CONTRACT,
    DIRECTOR_HARD_VALIDATION_POLICY,
    DIRECTOR_MANDATORY_INSPECTION_POLICY,
    DIRECTOR_TOOL_CALL_CONTRACT,
)


DIRECTOR_ACTIONS = """
## Allowed Actions
- `TOOL_CALL`: inspect/evaluate/expand/supplement data before deciding.
- `CONTINUE`: send the next generation task to `target`.
- `AUTO_REGENERATE`: regenerate the specified `target`.
- `GO_BACK_TO_WORLDVIEW`: repair or regenerate worldview.
- `GO_BACK_TO_CHARACTERS`: repair or regenerate character bible.
- `GO_BACK_TO_SKELETON_EXPANSION`: repair volume skeletons.
- `INCREMENTAL_MODIFY_CHARACTER`: modify one character field.
- `INCREMENTAL_APPEND_CHARACTER`: append a missing named character.
- `INCREMENTAL_MODIFY_SKELETON`: patch a volume skeleton.
- `INCREMENTAL_MODIFY_CHARACTER_FULL`: repair multiple fields on one character.
- `WAIT_USER`: only for true creative ambiguity requiring the author.
- `FINISH`: only when all planned writing/editing is complete.
"""


DIRECTOR_OUTPUT_CONTRACT = """
## Non-Negotiable Output Contract
You must output exactly one JSON object and nothing else.

Forbidden outputs:
- Markdown fences such as ```json.
- Natural-language report text before or after JSON.
- Analysis objects such as `major_recommendation`, `plan_items`, `fallback_plan`.
- Bare tool parameters such as `{ "stage_name": "...", "field_name": "..." }`.
- Multiple JSON objects in one response.

Every response must be one of these two envelopes.

Tool envelope:
{
  "action": "TOOL_CALL",
  "tool_call": {
    "tool_name": "evaluate_output",
    "parameters": {
      "stage_name": "foreshadowing"
    }
  },
  "reason": "Why this tool is needed and what decision it will support."
}

Decision envelope:
{
  "action": "CONTINUE",
  "target": "characters",
  "hint": "",
  "agent_prompt": "Task instruction for the next agent. Empty string if not needed.",
  "agent_context": "Required context for the next agent. Empty string if not needed.",
  "user_intent_summary": "One-sentence user intent summary. Empty string if not needed.",
  "reason": "Your review and routing rationale. Put all prose here.",
  "volume_index": null,
  "chapter_index": null
}
"""


DIRECTOR_CONTEXT_RULES = """
## Context Interpretation
- `validation_report` is computed by Python and is factual for structure, counts, missing stages, and indexes.
- `Last Agent Run` is evidence about the latest generator output; collapsed previews are not complete review.
- `available_expansion_tool` inside input is reference data only. Do not copy its `parameters_template` as your whole response.
- Prior Director messages may contain failed decisions. If system feedback says action is missing, ignore the malformed shape and produce a full envelope.
- Workflow progress gaps are not content-quality failures. Route to the next missing dependency.
"""


DIRECTOR_FLOW_RULES = """
## Dependency Flow
Standard flow:
`worldview` -> `characters` -> `foreshadowing` -> `volumes` -> `volume_skeleton` -> `writer` -> `editor` -> next writer/editor -> `FINISH`

Routing rules:
- Empty/incomplete worldview => `CONTINUE` target `worldview`.
- Worldview complete but characters missing => `CONTINUE` target `characters`.
- Characters complete but foreshadowing seeds/turning points missing => `CONTINUE` target `foreshadowing` with `[BATCH: foreshadowing_seeds]` or `[BATCH: key_turning_points]`.
- Foreshadowing complete but volumes missing => `CONTINUE` target `volumes`.
- Volumes complete but skeleton missing => `CONTINUE` target `volume_skeleton` with `volume_index`.
- Skeleton complete but prose missing => `CONTINUE` target `writer` with `chapter_index`.
- Writer complete => `CONTINUE` target `editor` for the same chapter unless editor already exists.
- Editor complete => next missing `writer`, or `FINISH` if all planned chapters are done.
"""


SELF_CORRECTION_RULES = """
## Self-Correction Mode
If input contains `系統決策校驗回報`:
- Treat it as the highest-priority instruction for this turn.
- Do not continue the same malformed shape.
- If the error says action is missing, output a full Tool envelope or Decision envelope with `action`.
- Do not output only `stage_name`, `field_name`, `start_index`, `end_index`, or any other parameter-only object.
"""


STAGE_REVIEW_RULES = {
    "worldview": """
## Stage Review: worldview
Check core worldview, multi-act structure, and progressive character plan.
If the data is empty or incomplete, route to `worldview`.
Put any critique inside `reason`; do not write a separate report.
""",
    "foreshadowing": """
## Stage Review: foreshadowing
Check both `foreshadowing_seeds` and `key_turning_points`.
First use `evaluate_output` for hard checks when needed.
Use `expand_collapsed_json` only through the full Tool envelope.
If one batch is missing, route to `foreshadowing` with the required batch marker.
If characters are missing, route to `characters` before continuing foreshadowing.
If both batches are structurally complete and sufficiently reviewed, route to `volumes`.
""",
    "characters": """
## Stage Review: characters
Check character list, protagonist completeness, relationship logic, and fit with worldview.
If characters are missing or unusable, route to `characters`.
If complete, route to `foreshadowing` if foreshadowing is incomplete; otherwise route to `volumes`.
""",
    "volumes": """
## Stage Review: volumes
Check volume count, chapter counts, macro-arc alignment, and volume functions.
If volumes are missing, route to `volumes`.
If complete, route to `volume_skeleton`.
""",
    "volume_skeleton": """
## Stage Review: volume_skeleton
Check the active volume skeleton against volume range, allocated_tasks, continuity, and character/faction consistency.
If a volume skeleton is missing, route to `volume_skeleton` with `volume_index`.
Do not ask for segmented generation; request one complete lightweight volume skeleton.
""",
    "writer": """
## Stage Review: writer
Check the current chapter prose against outline, characters, style, and allocated tasks.
If prose is missing or invalid, route to `writer` with `chapter_index`.
If prose passes, route to `editor` for the same chapter.
""",
    "editor": """
## Stage Review: editor
Check edited prose preserves outline, character voice, continuity, and improves readability.
If edit passes, route to next missing `writer` chapter, or `FINISH` when complete.
""",
}


def build_stage_review_rules(current_stage):
    return STAGE_REVIEW_RULES.get((current_stage or "").strip(), """
## Stage Review
Use validation_report and current persisted data to route to the next missing dependency.
Put all reasoning inside the JSON `reason` field.
""")


def build_director_decision_contract(current_stage, stage_criteria):
    return "\n\n".join(
        part.strip()
        for part in (
            DIRECTOR_OUTPUT_CONTRACT,
            DIRECTOR_DECISION_KEY_CONTRACT,
            DIRECTOR_ACTIONS,
            DIRECTOR_FLOW_RULES,
            DIRECTOR_CONTEXT_RULES,
            SELF_CORRECTION_RULES,
            build_stage_review_rules(current_stage),
            stage_criteria or "",
            DIRECTOR_TOOL_CALL_CONTRACT,
            DIRECTOR_HARD_VALIDATION_POLICY,
            DIRECTOR_MANDATORY_INSPECTION_POLICY,
        )
        if part and part.strip()
    )


FINAL_USER_INSTRUCTION = (
    "請根據上述資料做流程判斷。只輸出單一合法總監決策 JSON；"
    "所有評估、審查理由、下一步說明都放入 JSON value，尤其是 `reason`、`hint`、`agent_prompt` 或 `agent_context`。"
)
