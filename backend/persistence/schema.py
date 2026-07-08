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

def sync_agent_configs_from_env(cursor):
    """
    Reads all agent configurations from .env file and inserts/updates them
    directly into the agent_configs table.
    """
    agents = ["global", "architect", "character", "volumes", "volume_skeleton", "plot", "writer", "editor", "copilot"]
    
    # Build env key mappings programmatically from agent names
    # Each agent key is derived from its uppercase name (with volume_skeleton -> VOLUME_SKELETON)
    env_keys = {}
    for agent in agents:
        agent_upper = agent.upper()
        env_keys[agent] = {
            "api_key": f"NVIDIA_API_KEY_{agent_upper}",
            "base_url": f"BASE_URL_{agent_upper}",
            "model": f"MODEL_{agent_upper}",
            "temperature": f"TEMPERATURE_{agent_upper}",
            "top_p": f"TOP_P_{agent_upper}",
            "max_tokens": f"MAX_TOKENS_{agent_upper}",
            "enable_thinking": f"ENABLE_THINKING_{agent_upper}",
        }

    # Fallbacks from global .env variables
    default_base_url = os.getenv("DEFAULT_BASE_URL", "https://integrate.api.nvidia.com/v1")
    default_temp = float(os.getenv("DEFAULT_TEMPERATURE", 0.7))
    default_top_p = float(os.getenv("DEFAULT_TOP_P", 0.95))
    default_max_tokens = int(os.getenv("DEFAULT_MAX_TOKENS", 16384))
    default_enable_thinking = int(os.getenv("DEFAULT_ENABLE_THINKING", 1))

    for agent in agents:
        keys = env_keys[agent]
        
        # Load from agent-specific env var, fallback to global defaults or global env var
        api_key = os.getenv(keys["api_key"]) or os.getenv("NVIDIA_API_KEY_GLOBAL") or ""
        base_url = os.getenv(keys["base_url"]) or os.getenv("BASE_URL_GLOBAL") or default_base_url
        
        # Model mapping with correct fallbacks
        model = os.getenv(keys["model"])
        if not model:
            if agent == "character":
                model = os.getenv("MODEL_STORY")
            elif agent == "plot":
                model = os.getenv("MODEL_CRITIC")
            elif agent == "volumes":
                model = os.getenv("MODEL_VOLUMES") or os.getenv("MODEL_ARCHITECT")
            elif agent == "volume_skeleton":
                model = os.getenv("MODEL_VOLUME_SKELETON") or os.getenv("MODEL_PLOT")
            if not model:
                model = os.getenv("MODEL_GLOBAL") or "patcher-main"

        # Float / Int parameters with robust fallbacks
        def get_float_env(key, fallback):
            val = os.getenv(key)
            try:
                return float(val) if val is not None else fallback
            except ValueError:
                return fallback

        def get_int_env(key, fallback):
            val = os.getenv(key)
            try:
                return int(val) if val is not None else fallback
            except ValueError:
                return fallback

        agent_defaults = AGENT_DEFAULTS.get(agent, AGENT_DEFAULTS["global"])
        
        # temperature
        if agent_defaults.get("temperature") != AGENT_DEFAULTS["global"].get("temperature"):
            temperature = get_float_env(keys["temperature"], agent_defaults["temperature"])
        else:
            temperature = get_float_env(keys["temperature"], get_float_env("TEMPERATURE_GLOBAL", agent_defaults["temperature"]))
            
        # top_p
        if agent_defaults.get("top_p") != AGENT_DEFAULTS["global"].get("top_p"):
            top_p = get_float_env(keys["top_p"], agent_defaults["top_p"])
        else:
            top_p = get_float_env(keys["top_p"], get_float_env("TOP_P_GLOBAL", agent_defaults["top_p"]))
            
        # max_tokens
        if agent_defaults.get("max_tokens") != AGENT_DEFAULTS["global"].get("max_tokens"):
            max_tokens = get_int_env(keys["max_tokens"], agent_defaults["max_tokens"])
        else:
            max_tokens = get_int_env(keys["max_tokens"], get_int_env("MAX_TOKENS_GLOBAL", agent_defaults["max_tokens"]))
            
        # enable_thinking
        if agent_defaults.get("enable_thinking") != AGENT_DEFAULTS["global"].get("enable_thinking"):
            enable_thinking = get_int_env(keys["enable_thinking"], agent_defaults["enable_thinking"])
        else:
            enable_thinking = get_int_env(keys["enable_thinking"], get_int_env("ENABLE_THINKING_GLOBAL", agent_defaults["enable_thinking"]))

        cursor.execute("""
            INSERT OR REPLACE INTO agent_configs (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (agent, api_key, base_url, model, temperature, top_p, max_tokens, int(enable_thinking)))


def db_init():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Novels table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS novels (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        genre TEXT,
        style TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Ensure pipeline_prompt column exists
    try:
        cursor.execute("ALTER TABLE novels ADD COLUMN pipeline_prompt TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
        
    # Ensure worldview_patches column exists
    try:
        cursor.execute("ALTER TABLE novels ADD COLUMN worldview_patches TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass
    
    # 2. Worldbuilding table (versioned)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS worldbuilding (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        content TEXT,
        version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
    # 3. Characters table (versioned)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        json_data TEXT,
        version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
    # 4. Plot chapters table (versioned)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plot_chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        outline_json TEXT,
        version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
    # Ensure is_dirty exists in plot_chapters table
    try:
        cursor.execute("ALTER TABLE plot_chapters ADD COLUMN is_dirty INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    # 5. Chapters table (versioned)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        chapter_index INTEGER,
        content TEXT,
        synopsis TEXT,
        version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
    # Ensure synopsis column exists in chapters table
    try:
        cursor.execute("ALTER TABLE chapters ADD COLUMN synopsis TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Ensure thinking column exists in chapters table
    try:
        cursor.execute("ALTER TABLE chapters ADD COLUMN thinking TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Ensure is_dirty column exists in chapters table
    try:
        cursor.execute("ALTER TABLE chapters ADD COLUMN is_dirty INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    # 6. Chat Memory table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    try:
        cursor.execute("ALTER TABLE chat_memory ADD COLUMN thinking TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE chat_memory ADD COLUMN message_type TEXT DEFAULT 'chat'")
    except sqlite3.OperationalError:
        pass
    
    # 💡 Migrate historical director decisions to avoid token limit issues in existing databases
    try:
        cursor.execute("""
            UPDATE chat_memory 
            SET message_type = 'director' 
            WHERE message_type = 'chat' 
              AND (content LIKE '%【總監評估】%' 
                   OR content LIKE '%【決策理由】%' 
                   OR content LIKE '%[Plot Planner Rescue Attempt%')
        """)
    except Exception as e:
        print(f"[DB MIGRATION] Failed to migrate historical chat memory: {e}")
    
    # 7. Agent configs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_configs (
        agent_name TEXT PRIMARY KEY,
        api_key TEXT,
        base_url TEXT,
        model TEXT,
        temperature REAL,
        top_p REAL,
        max_tokens INTEGER,
        enable_thinking INTEGER DEFAULT 1
    )
    """)
    
    # 8. Volumes table (Bridging Layer)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS volumes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        volume_index INTEGER,
        title TEXT NOT NULL,
        summary TEXT,
        factions TEXT,
        is_dirty INTEGER DEFAULT 0,
        chapter_count INTEGER DEFAULT 50,
        time_timeline TEXT,
        sequence_context TEXT,
        applicable_rules TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
    # Ensure is_dirty exists in volumes table
    try:
        cursor.execute("ALTER TABLE volumes ADD COLUMN is_dirty INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    # Ensure chapters_outline exists in volumes table
    try:
        cursor.execute("ALTER TABLE volumes ADD COLUMN chapters_outline TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Ensure chapter_count exists in volumes table
    try:
        cursor.execute("ALTER TABLE volumes ADD COLUMN chapter_count INTEGER DEFAULT 50")
    except sqlite3.OperationalError:
        pass
        
    # Ensure time_timeline exists in volumes table
    try:
        cursor.execute("ALTER TABLE volumes ADD COLUMN time_timeline TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Ensure sequence_context exists in volumes table
    try:
        cursor.execute("ALTER TABLE volumes ADD COLUMN sequence_context TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Ensure applicable_rules exists in volumes table
    try:
        cursor.execute("ALTER TABLE volumes ADD COLUMN applicable_rules TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Migrate any default 10 values to 50 for legacy compatibility
    try:
        cursor.execute("UPDATE volumes SET chapter_count = 50 WHERE chapter_count = 10")
    except sqlite3.OperationalError:
        pass
    
    # Sync all configurations from .env on start to ensure DB is always up to date
    sync_agent_configs_from_env(cursor)
    
    
    # 9. Global Foreshadowing Blueprint table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS foreshadowing_blueprints (
        novel_id TEXT PRIMARY KEY,
        blueprint_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)

    # 9.5. Pipeline locks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_locks (
        novel_id TEXT PRIMARY KEY,
        locked_by TEXT NOT NULL,
        locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        heartbeat_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 9.5b. Director review ledger
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS director_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT NOT NULL,
        stage_name TEXT NOT NULL,
        status TEXT NOT NULL,
        block_name TEXT,
        volume_index INTEGER,
        chapter_index INTEGER,
        reason TEXT,
        decision_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_director_reviews_lookup ON director_reviews (novel_id, stage_name, created_at)")
    except sqlite3.OperationalError:
        pass

    # 9.5c. Narrative memory tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapter_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT NOT NULL,
        chapter_index INTEGER NOT NULL,
        summary_json TEXT NOT NULL,
        source_version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(novel_id, chapter_index),
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapter_memory_lookup ON chapter_memory (novel_id, chapter_index)")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS arc_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT NOT NULL,
        arc_start INTEGER NOT NULL,
        arc_end INTEGER NOT NULL,
        summary_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(novel_id, arc_start, arc_end),
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_arc_summaries_lookup ON arc_summaries (novel_id, arc_start, arc_end)")
    except sqlite3.OperationalError:
        pass

    # 9.6. Chapters backup table (for P0-1 wipe protection)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters_backup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        chapter_index INTEGER,
        content TEXT,
        synopsis TEXT,
        thinking TEXT,
        version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        backed_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    
    # Auto-prune chapters_backup older than 24 hours
    try:
        cursor.execute("""
            DELETE FROM chapters_backup 
            WHERE backed_up_at < datetime('now', '-24 hours')
        """)
        conn.commit()
    except Exception as e:
        print(f"[WARN] Failed to prune chapters_backup: {e}")
    
    # 9.7. Last agent run tracking table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_agent_run (
            novel_id TEXT PRIMARY KEY,
            agent_name TEXT,
            input_data TEXT,
            output_data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
    except Exception as e:
        print(f"[WARN] Failed to create last_agent_run table: {e}")
        
    # Clear any leftover pipeline locks on startup/init
    try:
        cursor.execute("DELETE FROM pipeline_locks")
        conn.commit()
        print("[DB] Cleared all stale pipeline locks on startup.")
    except Exception as e:
        print(f"[WARN] Failed to clear pipeline locks on startup: {e}")

    # Prompt overrides table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompt_overrides (
            template_name TEXT,
            key TEXT,
            value TEXT,
            PRIMARY KEY (template_name, key)
        )
        """)
        conn.commit()
    except Exception as e:
        print(f"[WARN] Failed to create prompt_overrides table: {e}")
        
    conn.close()

# --- PROMPT OVERRIDES ---
