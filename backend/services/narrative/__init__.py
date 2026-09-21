# -*- coding: utf-8 -*-
"""
Narrative Reasoning Services Package (Story Engine 2.0)
包含衝突因果特徵帳本 (conflict_ledger)、設定系統登錄 (setting_registry)
與敘事推理診斷引擎 (narrative_auditor)。
"""

from backend.services.narrative.conflict_ledger import ConflictLedger
from backend.services.narrative.setting_registry import SettingRegistry
from backend.services.narrative.narrative_auditor import NarrativeAuditor
from backend.services.narrative.backfill import backfill_novel_narrative
from backend.services.narrative.fix import fix_chapter_from_audits, build_fix_instructions

__all__ = ["ConflictLedger", "SettingRegistry", "NarrativeAuditor", "backfill_novel_narrative", "fix_chapter_from_audits", "build_fix_instructions"]
