# Refactoring Plan — Write_Novel Agent Architectures

This plan outlines the milestones to refactor the agent architectures in `Write_Novel` to separate concerns (constraints, validation, prompt assembly, and director context logic) from `agents.py` into specialized modules.

## Milestones

### Milestone 0: Initialization and Discovery [in-progress]
- Run existing tests to verify baseline correctness.
- Map out the exact list of functions to extract from `agents.py` for Constraints, Validation, Prompts, and Director context.

### Milestone 1: Refactor Constraints (R1) [pending]
- Extract rule-loading and constraint checks to `constraints.py`.
- Ensure imports and functions work seamlessly.

### Milestone 2: Refactor Validation and Calculations (R2) [pending]
- Extract quantity/count validation functions, chapter range parsers, foreshadowing validation functions to `validation.py`.
- Re-integrate with `agents.py`.

### Milestone 3: Reorganize Prompt Assembly and Director Operations (R3) [pending]
- Move prompt assembly functions to `prompts/prompt_builder.py`.
- Consolidate director context, memory building, and continuity logic in `director_context.py` and `prompts/prompt_builder.py`.
- Clean up raw prompt templates from `agents.py`.

### Milestone 4: Streamline agents.py (R4) [pending]
- Clean up `agents.py` to contain only routing, streaming, and execution pipeline orchestrations.
- Ensure all other concerns are imported.

### Milestone 5: Verification & Adversarial Coverage Hardening [pending]
- Run complete test suite `test_all.py` under UTF-8.
- Spawn Challengers to verify correctness under edge cases.
- Run Forensic Auditor to verify integrity and authentic logic.
