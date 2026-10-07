# -*- coding: utf-8 -*-
"""
Shared configuration constants for the AI Novel Factory.

Centralizes pipeline constraints and阈值 constants that were previously
duplicated across agents.py and diagnostics.py.
"""

# --- Foreshadowing constraints ---
MIN_FORESHADOWING_SEEDS = 150
MIN_KEY_TURNING_POINTS = 150

# --- Character constraints ---
MIN_CHARACTER_COUNT = 15

# --- Volume constraints ---
MIN_VOLUME_COUNT = 10
MAX_VOLUME_COUNT = 20
MIN_CHAPTERS_PER_VOLUME = 40
MAX_CHAPTERS_PER_VOLUME = 50

# --- Pipeline constraints ---
# API/模型端點可能暫時不穩定；所有「重新呼叫生成端點」的預設上限以此倍率放大。
# 這不是內容規則的放寬，只增加失敗後的重送機會。
RETRY_MULTIPLIER = 10
MAX_AUTO_LOOPS = 10 * RETRY_MULTIPLIER
FINAL_QUALITY_GATE_RETRIES = 2 * RETRY_MULTIPLIER
PROGRAMMATIC_ADJUST_RETRIES = 3 * RETRY_MULTIPLIER

# Writer 先交付可編輯的劇情底稿；Editor 負責擴成完整章節正文。
MIN_WRITER_DRAFT_LENGTH = 300
MIN_COMPLETE_CHAPTER_LENGTH = 1200

# --- Volume skeleton batching ---
VOLUME_SKELETON_BATCH_SIZE = 8
VOLUME_SKELETON_BATCH_RETRIES = 10 * RETRY_MULTIPLIER

# --- Volume skeleton segmentation (總監調度的分段生成) ---
# 給總監決定切段點時的建議前半長度上限；總監可依劇情起伏動態調整。
VOLUME_SKELETON_SEGMENT_SUGGESTED = 4
VOLUME_SKELETON_SEGMENT_RETRIES = 10 * RETRY_MULTIPLIER
# completion 補全時，assistant 前綴最多帶入多少個已生成章節（避免 prefix 過長）
VOLUME_SKELETON_COMPLETION_PREFIX_LIMIT = 12

# --- Story Engine 2.0: Narrative Reasoning & Anti-Repetition ---
MAX_RECENT_CONFLICT_SIGNATURES = 5
CONFLICT_SIMILARITY_WARNING_THRESHOLD = 0.70
SETTING_AUDIT_STALENESS_CHAPTERS = 25
LONG_RANGE_CONFLICT_CHECK_WINDOW = 60
