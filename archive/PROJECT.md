# Project: Write_Novel Agent Refactoring

## Architecture
- `agents.py`: Contains only pipeline routing, streaming, and execution orchestration.
- `constraints.py` (New): Rule loading and constraint management (R1).
- `validation.py` (New): Validation and quantity calculations (R2).
- `prompts/prompt_builder.py` and `director_context.py`: Centralized prompt assembly and director contexts (R3).

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Baseline Verification | Verify that test_all.py passes under UTF-8. | none | PLANNED |
| M2 | Constraints Relocation (R1) | Create constraints.py, relocate rule-loading and safe gold rules functions. | M1 | PLANNED |
| M3 | Validation Relocation (R2) | Create validation.py, relocate foreshadowing/volume checks and calculations. | M2 | PLANNED |
| M4 | Prompt & Director Logic (R3) | Relocate prompts/messages, consolidate director operations. | M3 | PLANNED |
| M5 | Streamline agents.py (R4) | Update agents.py imports, strip inline templates/helpers, verify everything runs. | M4 | PLANNED |
| M6 | E2E Testing Integration | Integrate E2E test suite from testing track and run all tests. | M5 | PLANNED |
| M7 | Adversarial Hardening (Tier 5) | Challenger-led edge case search and bug fixing. | M6 | PLANNED |

## Interface Contracts
### `constraints` ↔ `agents`
- `_load_retrospective_gold_rules(novel_id: str, limit: int) -> dict`
- `_safe_gold_rules_filename(title: str) -> str`

### `validation` ↔ `agents`
- `_foreshadowing_quantity_error(seeds: list, turns: list) -> str | None`
- `_foreshadowing_schema_error(seeds: list, turns: list) -> str | None`
- `_volume_plan_validation_error(volumes: list, mode: str) -> str | None`
- `_chapter_index_or_none(chapter: dict | int) -> int | None`
- `_volume_existing_chapter_indexes(volume: dict, start_ch: int, end_ch: int) -> list[int]`
- `_volume_missing_chapter_indexes(volumes: list, volume_index: int) -> list[int]`
- `_parse_requested_chapter_indexes(text: str, start_ch: int, end_ch: int) -> list[int]`
- `_split_consecutive_batches(indexes: list[int], batch_size: int) -> list[list[int]]`
- `_extract_chapters_in_range(parsed_skeleton: list, expected_indexes: list[int]) -> list[dict]`
- `_clean_foreshadowing_text(value: str) -> str`
- `_first_foreshadowing_text(item: dict, keys: list[str]) -> str`
- `_foreshadowing_text_list(value: any) -> list[str]`
- `_normalize_seed_item(item: dict, index: int) -> dict`
- `_normalize_turning_point_item(item: dict, index: int) -> dict`
- `_normalize_foreshadowing_output(parsed: dict) -> dict`

## Code Layout
- `agents.py`
- `constraints.py`
- `validation.py`
- `director_context.py`
- `utils.py`
- `prompts/prompt_builder.py`
