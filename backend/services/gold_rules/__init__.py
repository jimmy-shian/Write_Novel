# -*- coding: utf-8 -*-
"""
Gold Rules & Style Governance Service
"""

from .gold_rules_manager import (
    GoldRule,
    GoldRulesManager,
    get_gold_rules_manager,
    load_scoped_gold_rules,
)

__all__ = [
    "GoldRule",
    "GoldRulesManager",
    "get_gold_rules_manager",
    "load_scoped_gold_rules",
]
