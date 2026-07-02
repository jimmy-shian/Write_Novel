# Original User Request

## Initial Request — 2026-07-02T03:14:33+08:00

The project aim is to refactor the agent architectures in `Write_Novel` to separate concerns: constraints/rules, prompt assembly, count/validation logic, and director prompt operations, which are currently mixed across multiple files.

Working directory: c:\Users\user\Desktop\test_html\Write_Novel
Integrity mode: development

## Requirements

### R1. Move Constraints to `constraints.py`
- Create constraints.py to manage all rule-loading, rule-formatting, and gold rules checks.
- Move functions like `_load_retrospective_gold_rules` or other rule/constraint loaders from agents.py to `constraints.py`.

### R2. Move Validation and Quantity Calculations to `validation.py`
- Create validation.py to handle count checks, foreshadowing validations, volumes planners structure validation, chapter parsing/ranges, and all related checks.
- Move functions like `_foreshadowing_quantity_error`, `_foreshadowing_schema_error`, `_volume_plan_validation_error`, `_volume_existing_chapter_indexes`, `_volume_missing_chapter_indexes`, `_parse_requested_chapter_indexes`, `_split_consecutive_batches`, `_extract_chapters_in_range` from agents.py into `validation.py`.

### R3. Separate Prompt Assembly and Director Operations
- Reorganize all prompt assembly functions inside the `prompts` module (e.g. prompts/prompt_builder.py).
- Consolidate director-specific prompt/context logic, memory building, and continuity contexts in director_context.py and prompts/prompt_builder.py.
- Clean up any raw prompt format templates or inline prompt generation logic from agents.py.

### R4. Streamline `agents.py`
- Ensure agents.py only contains pipeline routing, streaming, and execution logic. Import functions from the newly created modules for constraints, validation, prompts, and director context.

## Acceptance Criteria

### Verification and Clean Architecture
- No mixed concerns: agents.py only contains routing, streaming, and pipeline orchestration.
- No inline prompt formatting or count validation functions inside agents.py.
- Create constraints.py and validation.py and integrate them with the rest of the application.
- The existing test suite in test_all.py must run and pass completely under UTF-8 encoding.
