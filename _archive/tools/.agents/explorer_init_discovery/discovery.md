# AI Novel Factory Discovery Report

This report summarizes findings from the read-only exploration of `agents.py`, `director_context.py`, and `test_all.py` in the workspace `c:\Users\user\Desktop\test_html\Write_Novel`.

---

## 1. Executive Summary

- **Test Suite Status**: The test suite in `test_all.py` comprises 15 unit tests testing database operations, worldview serialization, characters bible structure, parsing logic, backoff algorithms, FastAPI endpoints, programmatic character updates, deterministic seed allocations, and context selection policies. Running the tests via PowerShell timed out waiting for user permission (a constraint in unattended or non-interactive environments). However, static code analysis reveals the test suite is complete and self-contained.
- **Rule Loading & Validation Operations**: We identified 2 rule loaders and 18 helper validation/calculation functions in `agents.py` that should be factored out to reduce file clutter.
- **Prompt Builders**: The prompt format templates and message assembly methods are centralized in `prompts/prompt_builder.py`, `prompts/prompt_instructions.py`, and `prompts/prompt_main.py`.
- **Director Operations**: The director pipeline gatekeeper is managed via `run_director_decision` in `agents.py`, which heavily relies on `director_context.py` to construct contextual review payloads and `diagnostics.py` to check database integrity.

---

## 2. Target Functions to be Relocated from `agents.py`

Below is a detailed inventory of functions identified in `agents.py` for relocation or refactoring, sorted by category.

### 2.1 Constraints & Rule-Loading
| Function Name | Signature | Line Range | Rationale & Target Destination |
| :--- | :--- | :--- | :--- |
| `_safe_gold_rules_filename` | `def _safe_gold_rules_filename(title):` | 58–59 | Sanitizes book titles for loading gold rules. Move to `utils.py` or a dedicated rules module. |
| `_load_retrospective_gold_rules` | `def _load_retrospective_gold_rules(novel_id, limit=16000):` | 62–96 | Locates and reads retrospective rules from `gold_rules/`. Move to `utils.py` or a dedicated rules module. |

### 2.2 Foreshadowing Validation & Normalization
| Function Name | Signature | Line Range | Rationale & Target Destination |
| :--- | :--- | :--- | :--- |
| `_foreshadowing_quantity_error` | `def _foreshadowing_quantity_error(seeds, turns):` | 350–358 | Checks if seeds and turning points meet minimum requirements. Move to `models/parsers.py` or `diagnostics.py`. |
| `_clean_foreshadowing_text` | `def _clean_foreshadowing_text(value):` | 361–371 | Cleans text fields during serialization. Move to `models/parsers.py` or `utils.py`. |
| `_first_foreshadowing_text` | `def _first_foreshadowing_text(item, keys):` | 374–381 | Finds the first non-empty text value in a dict. Move to `models/parsers.py` or `utils.py`. |
| `_foreshadowing_text_list` | `def _foreshadowing_text_list(value):` | 384–390 | Converts varying representations into a clean list. Move to `models/parsers.py` or `utils.py`. |
| `_normalize_seed_item` | `def _normalize_seed_item(item, index):` | 393–404 | Formats a raw seed item into strict contract schema. Move to `models/parsers.py`. |
| `_normalize_turning_point_item` | `def _normalize_turning_point_item(item, index):` | 407–418 | Formats a raw turning point item into strict schema. Move to `models/parsers.py`. |
| `_normalize_foreshadowing_output` | `def _normalize_foreshadowing_output(parsed):` | 421–463 | Normalizes varying foreshadowing JSON patterns. Move to `models/parsers.py`. |
| `_foreshadowing_schema_error` | `def _foreshadowing_schema_error(seeds, turns):` | 466–500 | Asserts field completeness and type consistency. Move to `models/parsers.py` or `diagnostics.py`. |

### 2.3 Volume & Chapter Validation / Calculations
| Function Name | Signature | Line Range | Rationale & Target Destination |
| :--- | :--- | :--- | :--- |
| `_volume_plan_validation_error` | `def _volume_plan_validation_error(volumes, mode="generate"):` | 642–660 | Asserts volume counts and chapter boundary constraints. Move to `diagnostics.py` or `models/parsers.py`. |
| `_chapter_index_or_none` | `def _chapter_index_or_none(chapter):` | 735–742 | Resolves chapter index integer from nested dict structures. Move to `utils.py`. |
| `_volume_existing_chapter_indexes` | `def _volume_existing_chapter_indexes(volume, start_ch, end_ch):` | 745–758 | Resolves list of existing chapter integers within bounds. Move to `db.py` or `utils.py`. |
| `_volume_missing_chapter_indexes` | `def _volume_missing_chapter_indexes(volumes, volume_index):` | 761–768 | Computes holes or missing chapters in the volume. Move to `db.py` or `diagnostics.py`. |
| `_parse_requested_chapter_indexes` | `def _parse_requested_chapter_indexes(text, start_ch, end_ch):` | 771–790 | Regex extraction of chapter range tokens from author prompts. Move to `utils.py` or `models/parsers.py`. |
| `_split_consecutive_batches` | `def _split_consecutive_batches(indexes, batch_size=VOLUME_SKELETON_BATCH_SIZE):` | 793–808 | Chunks consecutive chapter holes for parallel skeleton planning. Move to `utils.py`. |
| `_extract_chapters_in_range` | `def _extract_chapters_in_range(parsed_skeleton, expected_indexes):` | 811–827 | Filter parsed LLM lists to the expected batch set. Move to `models/parsers.py` or `utils.py`. |
| `_build_nearby_skeleton_context` | `def _build_nearby_skeleton_context(volume, batch_indexes):` | 830–849 | Extracts adjacent skeleton contexts to avoid duplicating plots. Move to `director_context.py` or `prompts/prompt_builder.py`. |
| `build_precalc_clues` | `def build_precalc_clues(batch_indexes):` | 895–930 | Defined locally in `run_volume_skeleton_planner`. Computes seed/turn distributions. Move to `director_context.py` or `prompts/prompt_builder.py`. |

### 2.4 Prompt & Message Assembly
| Function Name | Signature | Line Range | Rationale & Target Destination |
| :--- | :--- | :--- | :--- |
| `build_missing_character_designer_messages` | `def build_missing_character_designer_messages(worldview_summary, existing_chars_json, new_char_name, chapter_outline):` | 1031–1081 | Message payload compiler. (Unused in the rest of `agents.py` but exists as helper). Move to `prompts/prompt_builder.py`. |

### 2.5 Director-Specific Helper Functions
| Function Name | Signature | Line Range | Rationale & Target Destination |
| :--- | :--- | :--- | :--- |
| `_extract_worldview_dict_preserving` | `def _extract_worldview_dict_preserving(content):` | 503–525 | Strips `<think>` tags and pulls nested JSON blocks. Move to `models/parsers.py` or `utils.py`. |
| `_extract_director_context_request` | `def _extract_director_context_request(content):` | 529–542 | Analyzes if LLM is asking for more information. Move to `director_context.py`. |
| `_handle_director_context_request` | `def _handle_director_context_request(novel_id, agent_label, full_text):` | 545–551 | Halts pipelines and saves chat alerts when information is lacking. Move to `director_context.py`. |

---

## 3. Detailed Analysis of Key Systems

### 3.1 Prompt Assembly and Context Logic
- **Architecture**: All core LLM prompts are externalized to the `prompts` package:
  - `prompts/prompt_main.py` contains structural templates and guidelines for each generator agent (architect, designer, planner, writer).
  - `prompts/prompt_instructions.py` houses orchestration systems, help routines, and the central Copilot instructions (`CO_PILOT_ORCHESTRATOR_PROMPT`).
  - `prompts/prompt_builder.py` contains functions starting with `build_` that take database models, query filters, and custom instructions, and format them into list-dict structures for OpenAI-compatible completions.
- **Context Compaction and Masking**: 
  - `select_worldview_context(worldview_text, current_stage)`: Selects only stage-specific worldview fields (e.g. omitting seeds and turns when planning volumes to save tokens).
  - `compact_json_data(data, max_list_items)`: Compacts large list fields in worldview or outlines (retains first 5 and last 5 elements, inserting a summary placeholder in between).
  - `mask_worldview_seeds_and_turns(worldview_text)`: Mask seeds and turns blocks to avoid leakages when they aren't being evaluated.

### 3.2 Director Context Operations
- **Orchestration Gatekeeping**: The pipeline gatekeeper is `run_director_decision` (lines 1378–1619). It detects the current creation stage and retrieves:
  - Worldview text.
  - Characters Bible.
  - Plot skeleton outlines.
  - Completed prose counts.
- **Diagnostics Validation**: It queries `diagnostics.generate_validation_report(...)` to retrieve database integrity checkmarks.
- **Review Context Composers**: It delegates to `director_context.py` to compile specialized reviews:
  - `build_foreshadowing_allocation_context(...)`: Builds deterministic allocation tables based on the md5 novel-id seed scattering algorithm.
  - `build_writer_review_context(...)`: Collates outline, preceding chapter prose tail, next chapter outline head, and relevant character details for continuity audit.
  - `build_editor_review_context(...)`: Computes before/after diff structures for prose polishing verification.

---

## 4. Test Suite Static Review

The test suite `test_all.py` includes 15 integrated unit tests covering the application:
1. `test_database_crud`: Validates novel creation, properties retrieval, and listing.
2. `test_worldview_and_patches`: Evaluates worldview database saves, version updates, and worldview incremental patches.
3. `test_characters_bible`: Validates characters bible JSON persistence and schema validations.
4. `test_json_parsers`: Tests markdown JSON block extraction and minimum length plot constraints.
5. `test_retry_backoff_equation`: Checks logic for exponential backoff math.
6. `test_fastapi_endpoints`: Verifies FastAPI routes for reading/saving configuration options.
7. `test_programmatic_json_adjustments`: Tests POST calls for individual character field updates (e.g., personality adjustment).
8. `test_deterministic_seeding_and_scattering_algorithm`: Asserts that md5 hashing from a unique novel UUID distributes foreshadowing plants and payoffs identically across runs.
9. `test_global_foreshadowing_precomputation`: Asserts automated precalculation of plants/payoffs during volume saving.
10. `test_validation_report_and_stage_detection`: Verifies the state detection algorithms in `diagnostics.py`.
11. `test_volume_and_chapter_constraints`: Tests the volume plan validation engine limits.
12. `test_volume_skeleton_planner_generates_only_missing_batch`: Ensures skeleton builders correctly resolve holes without overriding existing outlines.
13. `test_incremental_patch_engine_foreshadowing`: Tests patch merges of foreshadowing structures.
14. `test_task_relevant_context_selection`: Verifies prompt builder character and worldview filtering.
15. `test_json_context_compaction`: Validates list truncation, worldview selection policies, and masking routines.
