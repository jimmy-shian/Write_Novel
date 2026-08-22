# -*- coding: utf-8 -*-
"""
Constraints Module (限制規範層)
負責管理所有規則載入、格式化，以及 gold rules 黃金律的讀取與治理。
對接 GoldRulesManager 實現 Scope 分流與生命週期控制。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from backend import persistence as db
from backend.common.utils import safe_filename
from backend.services.gold_rules.gold_rules_manager import (
    GoldRule,
    GoldRulesManager,
    get_gold_rules_manager,
    load_scoped_gold_rules,
)


def gold_rules_filename(title: str) -> str:
    """將小說標題轉換為安全的 gold rules 檔名前綴。"""
    return safe_filename(title)


def gold_rules_directory() -> str:
    """傳回 gold rules 的統一儲存目錄（backend/data/gold_rules/）。"""
    return get_gold_rules_manager().get_storage_directory()


def load_retrospective_gold_rules(
    novel_id: str,
    limit: int = 16000,
    agent_scope: str = "global",
) -> str:
    """
    載入指定小說的 Retrospective Gold Rules。
    支援 Scope 篩選與優先級動態排序。
    """
    if not novel_id:
        return ""
    mgr = get_gold_rules_manager()
    formatted = mgr.format_rules_for_prompt(
        novel_id=novel_id,
        agent_scope=agent_scope,
        max_rules=12,
    )
    if formatted:
        return formatted[:limit] if limit else formatted

    # Fallback to legacy markdown if any
    legacy_md = mgr._get_legacy_markdown_path(novel_id)
    if legacy_md and os.path.isfile(legacy_md):
        try:
            with open(legacy_md, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content[:limit] if limit else content
        except OSError:
            pass

    return ""
