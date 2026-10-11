# -*- coding: utf-8 -*-
"""完本質檢工具（post-completion QC）：分層抽查＋全書掃描＋合併整理＋總結。"""
from .audit_engine import stratify, adjacent_pairs
from .orchestrator import run_audit

__all__ = ["stratify", "adjacent_pairs", "run_audit"]
