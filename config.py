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
