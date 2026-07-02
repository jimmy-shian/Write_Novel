# Constraints Relocation Analysis and Recommendations Report

## Executive Summary
This report provides the analysis and concrete recommendations for refactoring constraint management and rule loading in `agents.py` into a new, dedicated `constraints.py` module as defined in **Milestone 2 (Constraints Relocation)**. 

Based on the contracts in `PROJECT.md`, the interface between `constraints` and `agents` must support the following:
- `_load_retrospective_gold_rules(novel_id: str, limit: int) -> dict`
- `_safe_gold_rules_filename(title: str) -> str`

The functions `_safe_gold_rules_filename` and `_load_retrospective_gold_rules` are currently located at lines 58–96 of `agents.py`. This report details the implementation of `constraints.py` and the exact modifications needed in `agents.py`.

---

## 1. Exact Implementation of `constraints.py`
The new `constraints.py` module must be placed in the project root directory. It imports `db`, `os`, and `safe_filename` from `utils.py` and implements the two required interface functions.

To comply with the contract defined in `PROJECT.md` stating `_load_retrospective_gold_rules` returns a `dict`, the return value is structured as `{"content": text_content}`. This preserves the metadata capability of the function while enabling the calling code to access the raw text smoothly.

### Proposed Code for `constraints.py`
```python
# -*- coding: utf-8 -*-
"""
AI Novel Factory Constraint and Rules Management

This file centralizes rule loading and constraint management,
relocated from agents.py according to the Milestone 2 architecture constraints.
"""

import os
import db
from utils import safe_filename

def _safe_gold_rules_filename(title: str) -> str:
    """
    Get a filesystem-safe filename for a novel's retrospective gold rules.
    """
    return safe_filename(title)

def _load_retrospective_gold_rules(novel_id: str, limit: int = 16000) -> dict:
    """
    Load the latest retrospective gold rules for a given novel.
    Limits the total characters to prevent context window overflow.
    
    Returns:
        dict: A dictionary containing the gold rules content.
              Format: {"content": str}
    """
    novel = db.get_novel(novel_id)
    if not novel:
        return {"content": ""}
        
    gold_rules_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_rules")
    if not os.path.isdir(gold_rules_dir):
        return {"content": ""}

    safe_title = _safe_gold_rules_filename(novel.get("title", ""))
    candidates = []
    expected_name = f"{safe_title}_retrospective_gold_rules.md"
    expected_path = os.path.join(gold_rules_dir, expected_name)
    
    if os.path.isfile(expected_path):
        candidates.append(expected_path)
    else:
        for name in os.listdir(gold_rules_dir):
            if name.endswith("_retrospective_gold_rules.md") and name.startswith(safe_title):
                path = os.path.join(gold_rules_dir, name)
                if os.path.isfile(path):
                    candidates.append(path)

    if not candidates:
        return {"content": ""}
        
    latest = max(candidates, key=lambda path: os.path.getmtime(path))
    try:
        with open(latest, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except OSError:
        return {"content": ""}
        
    if len(content) <= limit:
        return {"content": content}
        
    marker = f"\n\n...[創作金律過長，已省略 {len(content) - limit} 字，保留開頭與結尾]...\n\n"
    head_len = max(1, (limit - len(marker)) * 2 // 3)
    tail_len = max(1, limit - len(marker) - head_len)
    truncated = content[:head_len] + marker + content[-tail_len:]
    return {"content": truncated}
```

---

## 2. Recommended Updates for `agents.py`
To integrate `constraints.py` into the runner pipeline, `agents.py` should be modified as follows:

### A. Imports Modification
Add the relocated functions import at the top level of `agents.py`, near other module imports:
```python
# Before (around line 18)
import director_context
from llm import call_llm_stream

# After
import director_context
from constraints import _load_retrospective_gold_rules, _safe_gold_rules_filename
from llm import call_llm_stream
```

### B. Functions Deletion
Remove the local definitions of `_safe_gold_rules_filename` and `_load_retrospective_gold_rules` (lines 58–96).

### C. Updates to Call Sites
Update call sites in `agents.py` to extract the `"content"` key from the returned dictionary. This maintains compatibility with the downstream prompt builders (`build_copilot_chat_messages` and `build_director_decision_messages`) which expect string inputs.

#### 1. In `run_copilot_chat` (around line 1359)
```python
# Before
    messages = build_copilot_chat_messages(
        novel_id, worldview_text, characters_text, plot_text, history_context, user_message, 
        validation_report=validation_report,
        gold_rules_context=_load_retrospective_gold_rules(novel_id)
    )

# After
    messages = build_copilot_chat_messages(
        novel_id, worldview_text, characters_text, plot_text, history_context, user_message, 
        validation_report=validation_report,
        gold_rules_context=_load_retrospective_gold_rules(novel_id).get("content", "")
    )
```

#### 2. In `run_director_decision` (around line 1607)
```python
# Before
    messages = build_director_decision_messages(
        novel_id, current_stage, worldview_text, characters_text, plot_text, written_chapters_text, 
        user_prompt, validation_report,
        character_review_mode=character_review_mode,
        character_review_hint=character_review_hint,
        character_review_target_content=character_review_target_content,
        suggested_next_chapter=suggested_next_chapter,
        chapter_index=chapter_index,
        director_context_block=director_context_block,
        gold_rules_context=_load_retrospective_gold_rules(novel_id)
    )

# After
    messages = build_director_decision_messages(
        novel_id, current_stage, worldview_text, characters_text, plot_text, written_chapters_text, 
        user_prompt, validation_report,
        character_review_mode=character_review_mode,
        character_review_hint=character_review_hint,
        character_review_target_content=character_review_target_content,
        suggested_next_chapter=suggested_next_chapter,
        chapter_index=chapter_index,
        director_context_block=director_context_block,
        gold_rules_context=_load_retrospective_gold_rules(novel_id).get("content", "")
    )
```

---

## 3. Rationale and Design Decisions
1. **Interface Contract Alignment**: The contract in `PROJECT.md` specifies `_load_retrospective_gold_rules(novel_id: str, limit: int) -> dict`. Returning a dictionary structured as `{"content": string_data}` allows the contract to be fully satisfied without breaking backwards compatibility.
2. **Backwards Compatibility**: Downstream prompt-building functions (`build_copilot_chat_messages` and `build_director_decision_messages` in `prompts/prompt_builder.py`) consume the rules as string inputs to append to prompt templates. Extracting `.get("content", "")` at call sites avoids modifying `prompt_builder.py` and maintains clean string payloads in prompts.
3. **Utility Re-use**: The function `_safe_gold_rules_filename` leverages the pre-refactored `safe_filename` from `utils.py` to prevent redundant implementation.

---

## 4. Verification steps
To verify the changes, the implementer should:
1. Write the new `constraints.py` file with the proposed content.
2. Apply the changes to `agents.py` (either via `agents.patch` or manual editing).
3. Run the integrated test suite:
   ```cmd
   C:\Users\user\venv\Scripts\python.exe test_all.py
   ```
4. Verify that `test_all.py` runs and passes successfully.
