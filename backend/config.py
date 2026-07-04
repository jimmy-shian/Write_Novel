# -*- coding: utf-8 -*-
"""
Shared configuration constants for the AI Novel Factory.

Centralizes pipeline constraints and阈值 constants that were previously
duplicated across agents.py and diagnostics.py.
"""

# --- Foreshadowing constraints ---
MIN_FORESHADOWING_SEEDS = 50
MIN_KEY_TURNING_POINTS = 50

# --- Volume constraints ---
MIN_VOLUME_COUNT = 10
MAX_VOLUME_COUNT = 20
MIN_CHAPTERS_PER_VOLUME = 40
MAX_CHAPTERS_PER_VOLUME = 50

# --- Pipeline constraints ---
MAX_AUTO_LOOPS = 10

# --- Volume skeleton batching ---
VOLUME_SKELETON_BATCH_SIZE = 8
VOLUME_SKELETON_BATCH_RETRIES = 10

# --- Volume skeleton segmentation (總監調度的分段生成) ---
# 給總監決定切段點時的建議前半長度上限；總監可依劇情起伏動態調整。
VOLUME_SKELETON_SEGMENT_SUGGESTED = 4
VOLUME_SKELETON_SEGMENT_RETRIES = 10
# completion 補全時，assistant 前綴最多帶入多少個已生成章節（避免 prefix 過長）
VOLUME_SKELETON_COMPLETION_PREFIX_LIMIT = 12
