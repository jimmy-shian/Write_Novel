# -*- coding: utf-8 -*-
import sqlite3
import json
from datetime import datetime
import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# 新增 opencc 套件，用於簡體轉繁體
try:
    from opencc import OpenCC
    _s2t_converter = OpenCC('s2t')
    # 進行安全自我檢測，防止 Windows 環境下 opencc 造成中文字串編碼損毀 (Mojibake)
    if _s2t_converter.convert("測試") != "測試":
        _s2t_converter = None
except Exception:
    # 若套件未安裝或載入失敗，fallback 為 identity function
    _s2t_converter = None

def _to_traditional(text):
    """將傳入的文字從簡體轉換為繁體。若非字串或轉換器不可用，直接回傳原值。"""
    if isinstance(text, str) and _s2t_converter:
        try:
            return _s2t_converter.convert(text)
        except Exception:
            return text
    return text

def _convert_obj_to_traditional(obj):
    """遞迴將物件內所有字串轉換為繁體（用於 dict/list 結構）。"""
    if isinstance(obj, str):
        return _to_traditional(obj)
    if isinstance(obj, list):
        return [_convert_obj_to_traditional(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _convert_obj_to_traditional(v) for k, v in obj.items()}
    return obj

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

DB_PATH = os.getenv("DB_PATH", os.path.join(PROJECT_ROOT, "data", "novel_factory.db"))

# --- Agent Default Configurations from .env ---
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

AGENT_DEFAULTS = {
    "global": {
        "model": os.getenv("MODEL_GLOBAL", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "architect": {
        "model": os.getenv("MODEL_ARCHITECT", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 32768,
        "enable_thinking": 0
    },
    "character": {
        "model": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 32768,
        "enable_thinking": 0
    },
    "volumes": {
        "model": os.getenv("MODEL_VOLUMES") or os.getenv("MODEL_ARCHITECT", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "volume_skeleton": {
        "model": os.getenv("MODEL_VOLUME_SKELETON") or os.getenv("MODEL_PLOT", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "plot": {
        "model": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "writer": {
        "model": os.getenv("MODEL_WRITER", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "editor": {
        "model": os.getenv("MODEL_EDITOR", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "copilot": {
        "model": os.getenv("MODEL_COPILOT", DEFAULT_MODEL),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    }
}

import threading

def _configure_sqlite_connection(conn: sqlite3.Connection):
    """套用 SQLite 引擎保護 SSD 與記憶體集中讀寫 PRAGMA 配置"""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA cache_size = -16384;")  # 16 MiB per connection
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA wal_autocheckpoint = 1000;")
    
    # MMAP 作為可選讀取優化（預設關閉 0）
    mmap_size = int(os.getenv("SQLITE_MMAP_SIZE", "0"))
    if mmap_size > 0:
        conn.execute(f"PRAGMA mmap_size = {mmap_size};")


class ConnectionManager:
    """Thread-Local Persistent Connection 管理器，避免頻繁開關檔案控制代碼與鎖震盪"""
    _local = threading.local()

    @classmethod
    def get_connection(cls) -> sqlite3.Connection:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        conn = getattr(cls._local, "conn", None)
        if conn is not None:
            try:
                # 快速連線存活檢查
                conn.execute("SELECT 1;")
                return conn
            except (sqlite3.ProgrammingError, sqlite3.OperationalError):
                try:
                    conn.close()
                except Exception:
                    pass
                cls._local.conn = None

        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        _configure_sqlite_connection(conn)
        cls._local.conn = conn
        return conn

    @classmethod
    def close_thread_connection(cls):
        """關閉目前執行緒的持久連線"""
        conn = getattr(cls._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            cls._local.conn = None


def get_db_connection() -> sqlite3.Connection:
    """取得目前執行緒的 SQLite Persistent Connection"""
    return ConnectionManager.get_connection()

