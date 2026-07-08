# -*- coding: utf-8 -*-
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from backend.common.utils import deep_merge_dict, safe_filename
from backend.persistence.connection import (
    AGENT_DEFAULTS,
    DB_PATH,
    _convert_obj_to_traditional,
    _to_traditional,
    get_db_connection,
)
try:
    from backend.schemas.agent_json import CHARACTER_BASIC_FIELDS
except Exception:
    CHARACTER_BASIC_FIELDS = []

def save_foreshadowing_allocations(novel_id, allocations):
    """
    [新功能] 將全局伏筆編織導演分配好的 allocated_tasks 寫回到各章節的骨架中
    這是 Stage 3 (Foreshadowing Orchestration) 的產出儲存點
    """
    # 伏筆/轉折章節位置以 Python deterministic blueprint 為唯一來源。
    # 舊版 LLM allocations 僅作為觸發點，不再追加寫入，以免同一 seed 被錯章重複埋收。
    touched = repair_foreshadowing_allocations(novel_id)
    print(f"[DB] Canonical foreshadowing allocations repaired for {novel_id} (volumes={touched})")
    return



def _canonical_seed_id(seed_index):
    from backend.services.foreshadowing.blueprint import canonical_seed_id
    return canonical_seed_id(seed_index)


def _coerce_int(value, default=0):
    from backend.services.foreshadowing.blueprint import coerce_int
    return coerce_int(value, default)


def _normalize_allocation_pair(pair, total_chapters):
    from backend.services.foreshadowing.blueprint import normalize_allocation_pair
    return normalize_allocation_pair(pair, total_chapters)


def _is_valid_foreshadowing_blueprint(blueprint, seed_count, turn_count, total_chapters):
    from backend.services.foreshadowing.blueprint import is_valid_foreshadowing_blueprint
    return is_valid_foreshadowing_blueprint(blueprint, seed_count, turn_count, total_chapters)


def build_canonical_foreshadowing_task_map(novel_id):
    from backend.services.foreshadowing.blueprint import build_canonical_foreshadowing_task_map as _build_map
    return _build_map(novel_id)


def apply_canonical_allocated_tasks_to_chapters(novel_id, chapters):
    from backend.services.foreshadowing.blueprint import apply_canonical_allocated_tasks_to_chapters as _apply_tasks
    return _apply_tasks(novel_id, chapters)


def repair_foreshadowing_allocations(novel_id, volume_index=None):
    from backend.services.foreshadowing.blueprint import repair_foreshadowing_allocations as _repair
    return _repair(novel_id, volume_index=volume_index)

def precompute_global_foreshadowing(novel_id):
    from backend.services.foreshadowing.blueprint import precompute_global_foreshadowing as _precompute
    return _precompute(novel_id)


def get_global_foreshadowing_blueprint(novel_id):
    from backend.services.foreshadowing.blueprint import get_global_foreshadowing_blueprint as _get_blueprint
    return _get_blueprint(novel_id)



# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
