# -*- coding: utf-8 -*-
import json
from typing import Optional, Dict, Any
from backend.persistence.connection import get_db_connection



def get_app_preference(key: str, default: Optional[str] = None) -> Optional[str]:
    """荷護單一系統/UI偏彵設定
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT value FROM app_preferences WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def get_all_app_preferences() -> Dict[str, str]:
    """荷護所有系統/UI偏彵設定字典 
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT key, value FROM app_preferences").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_app_preference(key: str, value: Any) -> None:
    """設定單一系統/UI偏字設定“
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    str_val = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    cursor.execute("""
        INSERT INTO app_preferences (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (key, str_val))
    conn.commit()


def set_app_preferences(prefs: Dict[str, Any]) -> Dict[str, str]:
    """批次儲存系統/UI偏字設定“
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    for key, value in prefs.items():
        if value is None:
            continue
        str_val = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        cursor.execute("""
            INSERT INTO app_preferences (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, str_val))
    conn.commit()
    return get_all_app_preferences()
