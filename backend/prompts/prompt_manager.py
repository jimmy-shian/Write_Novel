# -*- coding: utf-8 -*-
"""
Prompt 設定管理 - 集中管理/快取/動態組合全流程 prompt template
"""

import json
import os
from typing import Dict, Any, Optional

PROMPT_MANAGER_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE: Dict[str, str] = {}


def load_prompt_template(template_name: str) -> str:
    """讀取特定 prompt template"""
    if template_name in CACHE:
        return CACHE[template_name]

    fallback = os.path.join(PROMPT_MANAGER_DIR, f"{template_name}.txt")
    if os.path.exists(fallback):
        with open(fallback, "r", encoding="utf-8") as f:
            CACHE[template_name] = f.read()
            return CACHE[template_name]

    return ""


def build_runtime_prompt(
    base_template: str,
    overrides: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """將 base_template 與 runtime overrides 組合為最終 prompt"""
    result = base_template
    for key, value in (overrides or {}).items():
        placeholder = f"{{{key}}}"
        result = result.replace(placeholder, str(value))
    if context:
        context_block = "\n\n".join(
            f"【{k}】\n{v}" for k, v in context.items() if v
        )
        result += f"\n\n{context_block}"
    return result


def save_prompt_override(template_name: str, key: str, value: str):
    """持久化 prompt override 到資料庫"""
    from backend import persistence as db
    db.save_prompt_override(template_name, key, value)


def get_prompt_override(template_name: str, key: str) -> Optional[str]:
    from backend import persistence as db
    return db.get_prompt_override(template_name, key)
