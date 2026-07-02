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
