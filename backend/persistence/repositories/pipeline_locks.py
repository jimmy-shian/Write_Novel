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

def acquire_pipeline_lock(novel_id, locked_by="pipeline"):
    """Acquire a pipeline lock for a novel. Returns True if lock acquired, False if already locked by active process.
    If lock exists but heartbeat is older than 5 minutes (stale), breaks the stale lock and acquires new one.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO pipeline_locks (novel_id, locked_by, locked_at, heartbeat_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (novel_id, locked_by))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Lock exists - check if stale (heartbeat older than 5 minutes)
        cursor.execute("""
            SELECT locked_by, heartbeat_at FROM pipeline_locks WHERE novel_id = ?
        """, (novel_id,))
        row = cursor.fetchone()
        if row:
            # Check if heartbeat is stale (older than 5 minutes)
            # SQLite: (julianday('now') - julianday(heartbeat_at)) * 24 * 60 gives minutes difference
            cursor.execute("""
                SELECT (julianday('now') - julianday(heartbeat_at)) * 24 * 60 as minutes_diff
                FROM pipeline_locks WHERE novel_id = ?
            """, (novel_id,))
            diff_row = cursor.fetchone()
            if diff_row and diff_row["minutes_diff"] > 5:
                # Stale lock - break it and acquire new one
                cursor.execute("DELETE FROM pipeline_locks WHERE novel_id = ?", (novel_id,))
                cursor.execute("""
                    INSERT INTO pipeline_locks (novel_id, locked_by, locked_at, heartbeat_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (novel_id, locked_by))
                conn.commit()
                print(f"[LOCK] Broke stale lock for novel {novel_id} (held by {row['locked_by']})")
                return True
        return False
    finally:
        conn.close()

def release_pipeline_lock(novel_id):
    """Release the pipeline lock for a novel."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pipeline_locks WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()

def update_pipeline_heartbeat(novel_id):
    """Update the heartbeat timestamp for an active pipeline lock."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pipeline_locks SET heartbeat_at = CURRENT_TIMESTAMP WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()

def get_pipeline_lock_status(novel_id):
    """Get the current pipeline lock status for a novel. Returns dict if locked, None if not locked."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM pipeline_locks WHERE novel_id = ?", (novel_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# --- WORLDVIEW VALIDATION FUNCTIONS (P1-4) ---

# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *
