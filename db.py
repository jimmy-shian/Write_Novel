# -*- coding: utf-8 -*-
import sqlite3
import json
from datetime import datetime
import os
from utils import deep_merge_dict, safe_filename
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

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novel_factory.db")

# --- Agent Default Configurations from .env ---
AGENT_DEFAULTS = {
    "global": {
        "model": os.getenv("MODEL_GLOBAL", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "architect": {
        "model": os.getenv("MODEL_ARCHITECT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 32768,
        "enable_thinking": 0
    },
    "character": {
        "model": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 32768,
        "enable_thinking": 0
    },
    "volumes": {
        "model": os.getenv("MODEL_VOLUMES") or os.getenv("MODEL_ARCHITECT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "volume_skeleton": {
        "model": os.getenv("MODEL_VOLUME_SKELETON") or os.getenv("MODEL_PLOT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "plot": {
        "model": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "writer": {
        "model": os.getenv("MODEL_WRITER", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "editor": {
        "model": os.getenv("MODEL_EDITOR", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "copilot": {
        "model": os.getenv("MODEL_COPILOT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    }
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn

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
        
    conn.close()

# --- LAST AGENT RUN TRACKING ---
def save_last_agent_run(novel_id, agent_name, input_data, output_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO last_agent_run (novel_id, agent_name, input_data, output_data, timestamp)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(novel_id) DO UPDATE SET
            agent_name = excluded.agent_name,
            input_data = excluded.input_data,
            output_data = excluded.output_data,
            timestamp = CURRENT_TIMESTAMP
        """,
        (novel_id, agent_name, input_data, output_data)
    )
    conn.commit()
    conn.close()

def get_last_agent_run(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM last_agent_run WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

# --- NOVELS CRUD ---
def create_novel(novel_id, title, genre, style):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO novels (id, title, genre, style, pipeline_prompt) VALUES (?, ?, ?, ?, ?)",
        (novel_id, _to_traditional(title), genre, style, "")
    )
    conn.commit()
    conn.close()

def update_novel_pipeline_prompt(novel_id, pipeline_prompt):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE novels SET pipeline_prompt = ? WHERE id = ?",
        (_to_traditional(pipeline_prompt), novel_id)
    )
    conn.commit()
    conn.close()

def get_novel(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_novels():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM novels ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_novel(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    conn.commit()
    conn.close()

# --- VOLUMES (篇卷) HELPERS ---
def save_volumes(novel_id, volumes_list, clear_downstream=False, target_vol_idx=None):
    """
    target_vol_idx: 若指定（patch 模式），則只 upsert 該卷，其餘卷保留不被刪除。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if target_vol_idx is not None:
        cursor.execute(
            "DELETE FROM volumes WHERE novel_id = ? AND volume_index = ?",
            (novel_id, target_vol_idx)
        )
    else:
        cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
        if clear_downstream:
            # Backup chapters before wiping (P0-1)
            cursor.execute("DELETE FROM chapters_backup WHERE novel_id = ?", (novel_id,))
            cursor.execute("""
                INSERT INTO chapters_backup (novel_id, chapter_index, content, synopsis, thinking, version, created_at, backed_up_at)
                SELECT novel_id, chapter_index, content, synopsis, thinking, version, created_at, CURRENT_TIMESTAMP
                FROM chapters WHERE novel_id = ?
            """, (novel_id,))
            cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM foreshadowing_blueprints WHERE novel_id = ?", (novel_id,))
    for idx, vol in enumerate(volumes_list):
        volume_index = vol.get("volume_index", idx + 1)
        title = _to_traditional(vol.get("title", f"第 {volume_index} 卷"))
        summary = _to_traditional(vol.get("summary", ""))
        factions = vol.get("factions", "")
        if isinstance(factions, list) or isinstance(factions, dict):
            factions = json.dumps(_convert_obj_to_traditional(factions), ensure_ascii=False)
        else:
            factions = _to_traditional(factions)
        is_dirty = vol.get("is_dirty", 0)
        chapter_count = vol.get("chapter_count", 50)
        
        # 新增的精密對接欄位
        time_timeline = _to_traditional(vol.get("time_timeline", ""))
        sequence_context = _to_traditional(vol.get("sequence_context", ""))
        applicable_rules = vol.get("applicable_rules", "")
        if isinstance(applicable_rules, list) or isinstance(applicable_rules, dict):
            applicable_rules = json.dumps(_convert_obj_to_traditional(applicable_rules), ensure_ascii=False)
        else:
            applicable_rules = _to_traditional(applicable_rules)
            
        cursor.execute(
            "INSERT OR REPLACE INTO volumes (novel_id, volume_index, title, summary, factions, is_dirty, chapter_count, time_timeline, sequence_context, applicable_rules) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (novel_id, volume_index, title, summary, factions, is_dirty, chapter_count, time_timeline, sequence_context, applicable_rules)
        )
    conn.commit()
    conn.close()
    
    try:
        precompute_global_foreshadowing(novel_id)
    except Exception as e:
        print(f"[WARN] Failed to auto-precompute global foreshadowing inside save_volumes: {e}")

def get_volumes(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,)).fetchall()
    conn.close()
    res = []
    for r in rows:
        d = dict(r)
        try:
            d["parsed_factions"] = json.loads(d["factions"])
        except:
            d["parsed_factions"] = [d["factions"]] if d["factions"] else []
            
        # 解析適用法則 JSON
        try:
            if d.get("applicable_rules"):
                d["parsed_applicable_rules"] = json.loads(d["applicable_rules"])
            else:
                d["parsed_applicable_rules"] = []
        except:
            d["parsed_applicable_rules"] = [d["applicable_rules"]] if d["applicable_rules"] else []
            
        # 解析章節大綱骨架 JSON
        try:
            if d.get("chapters_outline"):
                d["chapters_outline"] = json.loads(d["chapters_outline"])
        except:
            d["chapters_outline"] = None
            
        res.append(d)
    return res

def _get_clean_chapter_count(vol):
    if not vol:
        return 50
    try:
        val = int(vol.get("chapter_count"))
        return val if val > 0 else 50
    except:
        return 50

def get_volume_chapter_range(volumes, target_volume_index):
    """
    根據篇卷列表，動態計算特定篇卷的起始與結束章節序號 (1-indexed)。
    每卷包含的章節數由 vol["chapter_count"] 決定（預設為 50 章）。
    """
    start_chapter = 1
    sorted_vols = sorted(volumes, key=lambda x: int(x.get("volume_index", 0)))
    for vol in sorted_vols:
        vol_idx = int(vol.get("volume_index", 0))
        vol_ch_count = _get_clean_chapter_count(vol)
        end_chapter = start_chapter + vol_ch_count - 1
        if vol_idx == target_volume_index:
            return start_chapter, end_chapter
        start_chapter = end_chapter + 1
        
    # Fallback: 如果 target_volume_index 超出 volumes 已有範圍，則從最後一卷向後推導
    if sorted_vols:
        last_vol = sorted_vols[-1]
        last_vol_idx = int(last_vol.get("volume_index", 0))
        last_start, last_end = get_volume_chapter_range(volumes, last_vol_idx)
        diff = target_volume_index - last_vol_idx
        default_count = _get_clean_chapter_count(last_vol)
        start = last_end + (diff - 1) * default_count + 1
        return start, start + default_count - 1
        
    return (target_volume_index - 1) * 50 + 1, target_volume_index * 50

def get_chapter_volume_index(volumes, chapter_index):
    """
    根據章節序號，尋找所屬的篇卷 index。如果找不到，返回 fallback 估計值。
    """
    start_chapter = 1
    sorted_vols = sorted(volumes, key=lambda x: int(x.get("volume_index", 0)))
    for vol in sorted_vols:
        vol_idx = int(vol.get("volume_index", 0))
        vol_ch_count = _get_clean_chapter_count(vol)
        end_chapter = start_chapter + vol_ch_count - 1
        if start_chapter <= int(chapter_index) <= end_chapter:
            return vol_idx
        start_chapter = end_chapter + 1
        
    # Fallback: 如果超出已規劃卷的最末章節，則往後延伸
    if sorted_vols:
        last_vol = sorted_vols[-1]
        last_vol_idx = int(last_vol.get("volume_index", 0))
        _, last_end = get_volume_chapter_range(volumes, last_vol_idx)
        if int(chapter_index) > last_end:
            default_count = _get_clean_chapter_count(last_vol)
            diff = (int(chapter_index) - last_end - 1) // default_count + 1
            return last_vol_idx + diff
            
    return (int(chapter_index) - 1) // 50 + 1

def get_total_chapter_count(volumes):
    if not volumes:
        return 1000
    return sum(_get_clean_chapter_count(v) for v in volumes)

def update_volume_dirty(novel_id, volume_index, is_dirty):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE volumes SET is_dirty = ? WHERE novel_id = ? AND volume_index = ?", (is_dirty, novel_id, volume_index))
    conn.commit()
    conn.close()

def update_volume_outline(novel_id, volume_index, node_chapters):
    """
    [最終完美修正版] 將特定篇卷的高解像度微觀大綱更新至資料庫。
    採用智慧增量合併，並採用直接 SQL 回寫主表，徹底防止 save_plot_chapters 引發反向抹除骨架的 Bug。
    強制校驗與過濾不在該卷合法章節範圍內的章節，防範跳號與重複。
    """
    # 💡 0. 讀取合法章節範圍
    vols = get_volumes(novel_id)
    start_ch, end_ch = get_volume_chapter_range(vols, volume_index)
    
    # 過濾新章節
    cleaned_node_chapters = []
    for nc in node_chapters:
        ch_idx = nc.get("chapter_index")
        if ch_idx is not None:
            try:
                ch_idx_int = int(ch_idx)
                if start_ch <= ch_idx_int <= end_ch:
                    cleaned_node_chapters.append(nc)
                else:
                    print(f"[WARN] update_volume_outline filtered out out-of-bounds chapter {ch_idx_int} for Vol {volume_index} (expected [{start_ch}, {end_ch}])")
            except:
                pass
        else:
            cleaned_node_chapters.append(nc)
            
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 💡 1. 先讀取當前資料庫中該卷已存在的所有章節大綱/骨架
    row = cursor.execute(
        "SELECT chapters_outline FROM volumes WHERE novel_id = ? AND volume_index = ?", 
        (novel_id, volume_index)
    ).fetchone()
    
    existing_chapters = []
    if row and row["chapters_outline"]:
        try:
            parsed = json.loads(row["chapters_outline"])
            if isinstance(parsed, list):
                existing_chapters = [c for c in parsed if start_ch <= int(c.get("chapter_index", 0)) <= end_ch]
        except:
            pass
            
    # 💡 2. 建立 chapter_index -> chapter_obj 的字典緩衝區
    merged_map = {}
    for ch in existing_chapters:
        ch_idx = ch.get("chapter_index")
        if ch_idx is not None:
            merged_map[int(ch_idx)] = ch
            
    # 💡 3. 用新生成的高解像度微觀章節精確覆蓋或插入緩衝區
    for nc in cleaned_node_chapters:
        ch_idx = nc.get("chapter_index")
        if ch_idx is not None:
            ch_idx_int = int(ch_idx)
            if ch_idx_int in merged_map:
                merged_map[ch_idx_int] = deep_merge_dict(merged_map[ch_idx_int], nc)
            else:
                merged_map[ch_idx_int] = nc
            
    # 重新套用 Python 預計算伏筆/轉折分配，避免 LLM 自行錯塞或同章重複埋收。
    merged_map = apply_canonical_allocated_tasks_to_chapters(novel_id, merged_map.values())

    # 重新轉回列表並依章節序號由小到大排序
    merged_chapters = list(merged_map.values())
    merged_chapters.sort(key=lambda x: int(x.get("chapter_index", 0)))
    
    # 💡 4. 將融合後完整的章節池同步回寫至 volumes 表
    chapters_json = json.dumps(_convert_obj_to_traditional(merged_chapters), ensure_ascii=False)
    cursor.execute(
        "UPDATE volumes SET chapters_outline = ?, is_dirty = 0 WHERE novel_id = ? AND volume_index = ?",
        (chapters_json, novel_id, volume_index)
    )
    
    # 💡 5. 同步將融合後的完整列表縫合回 master plot_chapters 大綱主表
    # 直接在同一個連線中安全讀取主表最末版本，避免併發鎖定
    plot_row = cursor.execute(
        "SELECT outline_json FROM plot_chapters WHERE novel_id = ? ORDER BY version DESC LIMIT 1", 
        (novel_id,)
    ).fetchone()
    
    all_ch = []
    if plot_row and plot_row["outline_json"]:
        try:
            p_parsed = json.loads(plot_row["outline_json"])
            all_ch = p_parsed.get("chapters", []) if isinstance(p_parsed, dict) else (p_parsed if isinstance(p_parsed, list) else [])
        except:
            all_ch = []
    
    filtered_ch = []
    v_rows = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,)).fetchall()
    vols = [dict(vr) for vr in v_rows]
    
    for c in all_ch:
        ch_idx = c.get("chapter_index")
        if ch_idx is not None:
            c_vol = get_chapter_volume_index(vols, int(ch_idx))
            if c_vol != int(volume_index):
                filtered_ch.append(c)
        else:
            filtered_ch.append(c)
            
    # 將本次大融合後的完整章節列表推入全書主線大綱集合中
    for mc in merged_chapters:
        filtered_ch.append(mc)
        
    # 全局升序排序
    filtered_ch.sort(key=lambda x: int(x.get("chapter_index", 0)) if x.get("chapter_index") is not None else 99999)
    
    # 💡 6. 【核心修復】：改用純 SQL 寫入大綱主表新版本，絕不呼叫會觸發反向分卷更新的 save_plot_chapters 函式！
    row_max = cursor.execute("SELECT MAX(version) as max_v FROM plot_chapters WHERE novel_id = ?", (novel_id,)).fetchone()
    next_v = (row_max["max_v"] or 0) + 1
    cursor.execute(
        "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, ?, 0)",
        (novel_id, json.dumps({"chapters": filtered_ch}, ensure_ascii=False), next_v)
    )
    
    conn.commit()
    conn.close()

def get_worldview_patches(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT worldview_patches FROM novels WHERE id = ?", (novel_id,)).fetchone()
    conn.close()
    if row and row["worldview_patches"]:
        try:
            return json.loads(row["worldview_patches"])
        except:
            return []
    return []

def add_worldview_patch(novel_id, category, details, source_chapter_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT worldview_patches FROM novels WHERE id = ?", (novel_id,)).fetchone()
    patches = []
    if row and row["worldview_patches"]:
        try:
            patches = json.loads(row["worldview_patches"])
        except:
            patches = []
    patches.append({
        "category": _to_traditional(category),
        "details": _to_traditional(details),
        "source_chapter": source_chapter_index,
        "created_at": datetime.now().isoformat()
    })
    cursor.execute("UPDATE novels SET worldview_patches = ? WHERE id = ?", (json.dumps(patches, ensure_ascii=False), novel_id))
    conn.commit()
    conn.close()

def mark_downstream_dirty(novel_id, source_chapter_index):
    """
    Marks downstream volumes and chapters as dirty (Lazy Realignment Protocol)
    to terminate immediate LLM cascades.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Mark chapters with index > source_chapter_index as dirty
    cursor.execute("UPDATE chapters SET is_dirty = 1 WHERE novel_id = ? AND chapter_index > ?", (novel_id, source_chapter_index))
    
    # 2. Mark latest plot_chapters (outlines) record as dirty
    cursor.execute("UPDATE plot_chapters SET is_dirty = 1 WHERE novel_id = ?", (novel_id,))
    
    # 3. Mark downstream volumes as dirty
    vols = get_volumes(novel_id)
    source_volume = get_chapter_volume_index(vols, source_chapter_index)
    cursor.execute("UPDATE volumes SET is_dirty = 1 WHERE novel_id = ? AND volume_index > ?", (novel_id, source_volume))
    
    conn.commit()
    conn.close()

def apply_worldview_patch(novel_id, category, details):
    """
    Adapter function that updates the patches list and appends to worldview lists.
    """
    add_worldview_patch(novel_id, category, details, 0)
    append_worldbuilding_list(novel_id, "foreshadowing_seeds", f"[NEW_WORLD_LAW: {category}] {details}")

# Alias to support agents.py imports seamlessly
mark_subsequent_dirty = mark_downstream_dirty

# --- CHAPTERS BACKUP FUNCTIONS (P0-1) ---
def backup_chapters_before_wipe(novel_id):
    """Backup all chapters before wiping for volumes regeneration."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Clear existing backup for this novel
    cursor.execute("DELETE FROM chapters_backup WHERE novel_id = ?", (novel_id,))
    # Copy current chapters to backup
    cursor.execute("""
        INSERT INTO chapters_backup (novel_id, chapter_index, content, synopsis, thinking, version, created_at, backed_up_at)
        SELECT novel_id, chapter_index, content, synopsis, thinking, version, created_at, CURRENT_TIMESTAMP
        FROM chapters WHERE novel_id = ?
    """, (novel_id,))
    conn.commit()
    conn.close()

def restore_chapters_backup(novel_id):
    """Restore chapters from backup after failed volumes regeneration."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Delete current chapters
    cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
    # Restore from backup
    cursor.execute("""
        INSERT INTO chapters (novel_id, chapter_index, content, synopsis, thinking, version, created_at)
        SELECT novel_id, chapter_index, content, synopsis, thinking, version, created_at
        FROM chapters_backup WHERE novel_id = ?
    """, (novel_id,))
    # Clear backup after restore
    cursor.execute("DELETE FROM chapters_backup WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()

# --- PIPELINE LOCK FUNCTIONS (P0-3) ---
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
def validate_worldview_schema(content):
    errors = []
    warnings = []
    parsed = None
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = parse_worldview_to_json(content)
        except Exception:
            pass
    if not isinstance(parsed, dict):
        text_lower = content.lower() if isinstance(content, str) else ''
        title_match = any(k in text_lower for k in ['title', '標題', '書名', '主題', 'theme'])
        if not title_match:
            errors.append('無法解析為結構化世界觀，且未包含必要識別欄位')
        return len(errors) == 0, errors, warnings
    from agent_json import WORLDVIEW_REQUIRED_FIELDS, WORLDVIEW_RECOMMENDED_FIELDS
    for field in WORLDVIEW_REQUIRED_FIELDS:
        if field not in parsed or parsed[field] in (None, '', [], {}):
            errors.append(f'缺少必要欄位: {field}')
    for field in WORLDVIEW_RECOMMENDED_FIELDS:
        if field not in parsed or parsed[field] in (None, '', [], {}):
            warnings.append(f'建議補充欄位: {field}')
    return len(errors) == 0, errors, warnings

# --- WORLDBUILDING (VERSIONED) ---
def get_latest_worldbuilding(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_worldbuilding_history(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT version, created_at FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC",
        (novel_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_worldbuilding_by_version(novel_id, version):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM worldbuilding WHERE novel_id = ? AND version = ?",
        (novel_id, version)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def save_worldbuilding(novel_id, content, validate=True):
    if validate:
        valid, errors, warnings = validate_worldview_schema(content)
        if not valid:
            raise ValueError(f'世界觀結構驗證失敗: {";".join(errors)}')
        if warnings:
            print(f'[WARN] Worldview validation warnings for novel {novel_id}: {";".join(warnings)}')
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM worldbuilding WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO worldbuilding (novel_id, content, version) VALUES (?, ?, ?)",
        (novel_id, _to_traditional(content), next_version)
    )
    conn.commit()
    conn.close()
    return next_version

# --- CHARACTERS (VERSIONED) ---
def get_latest_characters(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM characters WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    conn.close()
    if row:
        data = dict(row)
        try:
            from models.parsers import extract_json_block
            data["parsed_data"] = extract_json_block(data["json_data"])
        except:
            data["parsed_data"] = {}
        return data
    return None


def clean_and_deduplicate_characters(characters_list):
    if not isinstance(characters_list, list):
        return characters_list
        
    cleaned_chars = []
    
    # 1. Filter out invalid/placeholder characters
    placeholder_names = {
        "新登場的次要角色", "待補充", "暫無", "placeholder", "新角色", "路人", 
        "客棧老闆", "符合人設說話風格", "todo", "新登場次要角色"
    }
    
    for c in characters_list:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "").strip()
        if not name:
            continue
            
        # If name is a placeholder, skip
        is_placeholder = False
        for pn in placeholder_names:
            if pn in name.lower() or name.lower() in pn:
                is_placeholder = True
                break
        if is_placeholder:
            continue
            
        # Clean fields in the character dictionary
        cleaned_c = {}
        for k, v in c.items():
            if isinstance(v, str):
                v_clean = v.strip()
                # If value is a placeholder text, make it empty
                if any(p in v_clean.lower() for p in ["符合人設說話風格", "請填入", "待定", "暫無", "待補充"]):
                    v_clean = ""
                cleaned_c[k] = v_clean
            elif isinstance(v, list):
                # Clean elements of lists
                cleaned_list = []
                for x in v:
                    if isinstance(x, str):
                        x_clean = x.strip()
                        if not any(p in x_clean.lower() for p in ["符合人設說話風格", "請填入", "待定", "暫無", "待補充"]):
                            cleaned_list.append(x_clean)
                    else:
                        cleaned_list.append(x)
                cleaned_c[k] = cleaned_list
            else:
                cleaned_c[k] = v
        cleaned_chars.append(cleaned_c)
        
    # Helper to get core name
    def get_core_name(name_str):
        if not name_str:
            return ""
        import re
        # Remove content in parentheses
        name_str = re.sub(r'[\(（].*?[\)）]', '', name_str)
        # Remove content after hyphens, dashes, colons or spaces
        for separator in ['-', '–', '—', '_', ':', '：', ' ', '\t']:
            if separator in name_str:
                parts = name_str.split(separator)
                if parts[0].strip():
                    name_str = parts[0]
        return name_str.strip()

    # Helper to merge two characters
    def merge_two_characters_backend(c1, c2):
        name1 = c1.get("name", "")
        name2 = c2.get("name", "")
        
        chosen_name = name1
        if name2 and len(name2) < len(name1):
            chosen_name = name2
        if not chosen_name:
            chosen_name = name1 or name2
            
        merged = {"name": chosen_name}
        
        # Field: role
        r1 = c1.get("role", "")
        r2 = c2.get("role", "")
        merged["role"] = r1 if len(str(r1)) >= len(str(r2)) else r2
        
        # Field: entry_phase
        ep1 = c1.get("entry_phase", "")
        ep2 = c2.get("entry_phase", "")
        merged["entry_phase"] = ep1 if ep1 else ep2
        
        # Field: personality (list)
        p1 = c1.get("personality", [])
        p2 = c2.get("personality", [])
        if isinstance(p1, str): p1 = [p1]
        if isinstance(p2, str): p2 = [p2]
        p_merged = list(set((p1 or []) + (p2 or [])))
        merged["personality"] = [x for x in p_merged if x]
        
        # Text fields
        for field in ["want", "need", "fatal_flaw", "motivation", "arc", "speech_style"]:
            val1 = c1.get(field, "")
            val2 = c2.get(field, "")
            if val1 and val2:
                if val1.strip().lower() == val2.strip().lower():
                    merged[field] = val1
                else:
                    merged[field] = val1 if len(str(val1)) >= len(str(val2)) else val2
            else:
                merged[field] = val1 or val2
                
        # Relationships (list of dicts)
        rel1 = c1.get("relationships", []) or []
        rel2 = c2.get("relationships", []) or []
        if not isinstance(rel1, list): rel1 = [rel1]
        if not isinstance(rel2, list): rel2 = [rel2]
        
        merged_rels = []
        rel_by_target = {}
        for r in rel1 + rel2:
            if not isinstance(r, dict):
                continue
            target = r.get("with")
            if not target:
                continue
            target_core = get_core_name(target)
            if target_core not in rel_by_target:
                rel_by_target[target_core] = r.copy()
            else:
                existing = rel_by_target[target_core]
                t_type = r.get("type", "")
                e_type = existing.get("type", "")
                if t_type and t_type not in e_type:
                    existing["type"] = f"{e_type} / {t_type}" if e_type else t_type
                t_evo = r.get("evolution", "")
                e_evo = existing.get("evolution", "")
                if t_evo and t_evo not in e_evo:
                    existing["evolution"] = f"{e_evo}。{t_evo}" if e_evo else t_evo
                    
        merged["relationships"] = list(rel_by_target.values())
        return merged

    # 2. Group by core name and merge
    merged_by_core = {}
    core_order = []  # To preserve original ordering of appearance
    
    for c in cleaned_chars:
        name = c.get("name", "")
        core = get_core_name(name)
        if not core:
            continue
            
        if core not in merged_by_core:
            merged_by_core[core] = c
            core_order.append(core)
        else:
            # Merge with existing
            existing = merged_by_core[core]
            merged_by_core[core] = merge_two_characters_backend(existing, c)
            
    # Reconstruct list
    result = [merged_by_core[core] for core in core_order]
    return result

def save_characters(novel_id, json_data):
    if isinstance(json_data, dict) or isinstance(json_data, list):
        # 先將字典/清單內的字串進行繁體轉換
        json_data = _convert_obj_to_traditional(json_data)
        
        # 🚨 自動執行去重與合併 🚨
        if isinstance(json_data, dict) and "characters" in json_data:
            json_data["characters"] = clean_and_deduplicate_characters(json_data["characters"])
        elif isinstance(json_data, list):
            json_data = clean_and_deduplicate_characters(json_data)
            
        json_str = json.dumps(json_data, ensure_ascii=False)
    else:
        json_str = _to_traditional(json_data)
        try:
            from models.parsers import extract_json_block
            parsed = extract_json_block(json_str)
            if isinstance(parsed, dict) and "characters" in parsed:
                parsed["characters"] = clean_and_deduplicate_characters(parsed["characters"])
                json_str = json.dumps(parsed, ensure_ascii=False)
            elif isinstance(parsed, list):
                parsed = clean_and_deduplicate_characters(parsed)
                json_str = json.dumps(parsed, ensure_ascii=False)
        except:
            pass
        
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM characters WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO characters (novel_id, json_data, version) VALUES (?, ?, ?)",
        (novel_id, json_str, next_version)
    )
    conn.commit()
    conn.close()
    return next_version

# --- PLOT CHAPTERS (VERSIONED) ---
def get_latest_plot_chapters(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM plot_chapters WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    conn.close()
    if row:
        data = dict(row)
        try:
            from models.parsers import extract_json_block
            parsed = extract_json_block(data["outline_json"])
            if isinstance(parsed, list):
                data["parsed_data"] = {"chapters": parsed}
            else:
                data["parsed_data"] = parsed
        except Exception as e:
            print(f"[ERROR] Failed to parse plot_chapters JSON: {e}")
            data["parsed_data"] = {}
        return data
    return None

def save_plot_chapters(novel_id, outline_json, skip_volume_sync=False, clear_chapters=False):
    if isinstance(outline_json, dict) or isinstance(outline_json, list):
        # 轉換所有字串為繁體再序列化
        outline_json = _convert_obj_to_traditional(outline_json)
        json_str = json.dumps(outline_json, ensure_ascii=False)
        parsed_dict = outline_json
    else:
        json_str = _to_traditional(outline_json)
        try:
            from models.parsers import extract_json_block
            parsed_dict = extract_json_block(json_str)
            if parsed_dict:
                json_str = json.dumps(parsed_dict, ensure_ascii=False)
        except:
            parsed_dict = {}
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if clear_chapters:
        cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
    
    # The `plot_chapters` table is deprecated. We no longer save plot_json to the database directly.
    # We now strictly rely on `volumes` chapters_outline to persist the story structure.
    
    # 2. Automatically sync and distribute chapters outlines to individual volumes in the volumes table
    #    ⚠️ 重要：採用「智慧合併+刪除同步模式」，不直接覆蓋骨架數據。
    #    骨架欄位（chapter_title/chapter_summary/allocated_tasks）必須保留，
    #    只將章節大綱的欄位 patch 進去；同時刪除 incoming 中已移除的章節。
    chapters_list = []
    has_chapters_payload = False
    if isinstance(parsed_dict, dict):
        if "chapters" in parsed_dict or "chapters_skeleton" in parsed_dict:
            has_chapters_payload = True
            candidate = parsed_dict.get("chapters") or parsed_dict.get("chapters_skeleton") or []
            chapters_list = candidate if isinstance(candidate, list) else []
    elif isinstance(parsed_dict, list):
        has_chapters_payload = True
        chapters_list = parsed_dict

    if not skip_volume_sync and has_chapters_payload:
        vol_groups = {}
        vols = get_volumes(novel_id)
            
        # 💡 建立全書 incoming chapter_index 的完整集合（用於刪除同步）
        all_incoming_chapter_indices = set()
        for ch in chapters_list:
            try:
                c_idx = int(ch.get("chapter_index", 0))
                if c_idx > 0:
                    all_incoming_chapter_indices.add(c_idx)
            except:
                pass
        
        for ch in chapters_list:
            try:
                c_idx = int(ch.get("chapter_index", 0))
            except:
                c_idx = 0
            if c_idx > 0:
                vol_idx = get_chapter_volume_index(vols, c_idx)
                if vol_idx not in vol_groups:
                    vol_groups[vol_idx] = []
                vol_groups[vol_idx].append(ch)
        
        # 💡 對每個有資料的卷進行合併式更新 + 刪除同步
        for vol_idx, new_detail_chaps in vol_groups.items():
            # 建立章節大綱的 chapter_index -> chapter_data 映射
            detail_map = {}
            for ch in new_detail_chaps:
                try:
                    c_idx = int(ch.get("chapter_index", 0))
                    if c_idx > 0:
                        detail_map[c_idx] = ch
                except:
                    pass
            
            # 讀取目前卷的骨架（chapters_outline）
            vol_row = cursor.execute(
                "SELECT id, chapters_outline FROM volumes WHERE novel_id = ? AND volume_index = ?",
                (novel_id, vol_idx)
            ).fetchone()
            
            if vol_row:
                existing_outline_str = vol_row["chapters_outline"]
                
                # 嘗試解析現有骨架
                existing_skeleton = []
                if existing_outline_str:
                    try:
                        existing_skeleton = json.loads(existing_outline_str)
                        if not isinstance(existing_skeleton, list):
                            existing_skeleton = []
                    except:
                        existing_skeleton = []
                
                # 建立骨架的 chapter_index -> skeleton_ch 映射
                skeleton_map = {}
                for sk_ch in existing_skeleton:
                    raw_idx = sk_ch.get("chapter_index") or sk_ch.get("chapter") or sk_ch.get("index")
                    try:
                        sk_idx = int(raw_idx)
                        skeleton_map[sk_idx] = sk_ch
                    except:
                        pass
                
                # 合併：將章節大綱欄位 patch 進骨架（保留骨架欄位）
                merged_chapters = {}
                
                # 先把所有骨架章節放入（但只保留在 incoming 中仍存在的章節）
                # 💡 核心修復：若骨架章節的 index 不在 all_incoming_chapter_indices 中，
                #    代表已被前端刪除，直接跳過（實現骨架刪除同步）
                for sk_idx, sk_ch in skeleton_map.items():
                    if sk_idx in all_incoming_chapter_indices:
                        merged_chapters[sk_idx] = dict(sk_ch)  # 保留所有骨架欄位
                    # 不在 incoming 中 → 已被刪除，不放入 merged
                
                # 再把章節大綱合併進去
                for det_idx, det_ch in detail_map.items():
                    if det_idx in merged_chapters:
                        # 合併：詳細欄位覆蓋，骨架欄位保留（不刪除 chapter_title 等）
                        merged_chapters[det_idx].update(det_ch)
                    else:
                        # 新章節直接加入
                        merged_chapters[det_idx] = dict(det_ch)
                
                # 按章節序號排序
                merged_list = [merged_chapters[k] for k in sorted(merged_chapters.keys())]
                merged_str = json.dumps(merged_list, ensure_ascii=False)
                
                cursor.execute(
                    "UPDATE volumes SET chapters_outline = ? WHERE id = ?",
                    (merged_str, vol_row["id"])
                )
            else:
                # 卷不存在，直接新建（無骨架可合併）
                v_start, v_end = get_volume_chapter_range(vols, vol_idx)
                new_chaps_str = json.dumps(list(detail_map.values()), ensure_ascii=False)
                cursor.execute(
                    "INSERT INTO volumes (novel_id, volume_index, title, summary, factions, is_dirty, chapters_outline) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?)",
                    (novel_id, vol_idx, f"第 {vol_idx} 卷", f"本卷包含第 {v_start} 章至第 {v_end} 章的大綱規劃。", "全域陣列", new_chaps_str)
                )
        
        # 💡 額外處理：對於「有骨架但 incoming 中完全沒有任何章節的卷」，
        #    也要清除其骨架中已被刪除的章節（例如刪除骨架章節後 plot.chapters 為空時）
        all_vol_indices = set(v.get("volume_index", 0) for v in vols)
        for vol_idx in all_vol_indices:
            if vol_idx not in vol_groups:
                # 這個卷在 incoming 中沒有任何章節 → 它的骨架也可能需要清除已刪除章節
                vol_row = cursor.execute(
                    "SELECT id, chapters_outline FROM volumes WHERE novel_id = ? AND volume_index = ?",
                    (novel_id, vol_idx)
                ).fetchone()
                if vol_row and vol_row["chapters_outline"]:
                    try:
                        existing_skeleton = json.loads(vol_row["chapters_outline"])
                        if isinstance(existing_skeleton, list):
                            # 只保留 incoming 中仍存在的章節
                            filtered = []
                            for sk_ch in existing_skeleton:
                                raw_idx = sk_ch.get("chapter_index") or sk_ch.get("chapter") or sk_ch.get("index")
                                try:
                                    sk_idx = int(raw_idx)
                                    if sk_idx in all_incoming_chapter_indices:
                                        filtered.append(sk_ch)
                                except:
                                    pass
                            # 若有章節被刪除，更新骨架
                            if len(filtered) != len(existing_skeleton):
                                cursor.execute(
                                    "UPDATE volumes SET chapters_outline = ? WHERE id = ?",
                                    (json.dumps(filtered, ensure_ascii=False), vol_row["id"])
                                )
                    except:
                        pass
                
    conn.commit()
    conn.close()
    return 1


# --- CHAPTERS (VERSIONED) ---
def get_latest_chapter(novel_id, chapter_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM chapters WHERE novel_id = ? AND chapter_index = ? ORDER BY version DESC LIMIT 1",
        (novel_id, chapter_index)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_second_latest_chapter(novel_id, chapter_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT * FROM chapters WHERE novel_id = ? AND chapter_index = ? ORDER BY version DESC LIMIT 2",
        (novel_id, chapter_index)
    ).fetchall()
    conn.close()
    if len(rows) >= 2:
        return dict(rows[1])
    return None

def get_latest_edit_instructions(novel_id, chapter_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT content FROM chat_memory WHERE novel_id = ? AND role = 'user' AND message_type = 'pipeline' AND content LIKE ? ORDER BY id DESC LIMIT 1",
        (novel_id, f"%第 {chapter_index} 章%")
    ).fetchone()
    conn.close()
    if row:
        content = row["content"]
        # Try to parse instructions out from "指示: {edit_instructions}" or "指示："
        if "指示:" in content:
            return content.split("指示:", 1)[1].strip()
        elif "指示：" in content:
            return content.split("指示：", 1)[1].strip()
        return content
    return "無具體修改指示，由編輯自主優化。" 

def get_all_chapters_latest(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT c.* FROM chapters c
        INNER JOIN (
            SELECT novel_id, chapter_index, MAX(version) as max_v
            FROM chapters
            WHERE novel_id = ?
            GROUP BY chapter_index
        ) latest ON c.novel_id = latest.novel_id 
                 AND c.chapter_index = latest.chapter_index 
                 AND c.version = latest.max_v
        ORDER BY c.chapter_index ASC
    """, (novel_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_chapter(novel_id, chapter_index, content, synopsis=None, thinking=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM chapters WHERE novel_id = ? AND chapter_index = ?",
        (novel_id, chapter_index)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO chapters (novel_id, chapter_index, content, synopsis, thinking, version, is_dirty) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (novel_id, chapter_index, _to_traditional(content), _to_traditional(synopsis) if synopsis else None,
         _to_traditional(thinking) if thinking else None, next_version)
    )
    conn.commit()
    conn.close()
    return next_version

# --- CHAT MEMORY ---
def get_chat_memory(novel_id, limit=20, message_type=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if message_type:
        rows = cursor.execute(
            "SELECT role, content, thinking, message_type, timestamp FROM chat_memory WHERE novel_id = ? AND message_type = ? ORDER BY id DESC LIMIT ?",
            (novel_id, message_type, limit)
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT role, content, thinking, message_type, timestamp FROM chat_memory WHERE novel_id = ? AND message_type IN ('chat', 'director') ORDER BY id DESC LIMIT ?",
            (novel_id, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def save_chat_message(novel_id, role, content, thinking=None, message_type='chat'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_memory (novel_id, role, content, thinking, message_type) VALUES (?, ?, ?, ?, ?)",
        (novel_id, role, _to_traditional(content), _to_traditional(thinking) if thinking else None, message_type)
    )
    conn.commit()
    conn.close()

def clear_chat_memory(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_memory WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()

# --- AGENT CONFIGS ---
def get_agent_configs():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM agent_configs").fetchall()
    conn.close()
    return {r["agent_name"]: dict(r) for r in rows}

def save_agent_config(agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO agent_configs (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, int(enable_thinking)))
    conn.commit()
    conn.close()

# --- INCREMENTAL UPDATE FUNCTIONS ---
def parse_worldview_to_json(content):
    default_structure = {
        "theme": "",
        "main_conflict": "",
        "worldview": "",
        "macro_outline": "",
        "multi_act_structure": [
            {"title": "第一幕 (Setup)", "content": ""},
            {"title": "第二幕 (Confrontation)", "content": ""},
            {"title": "第三幕 (Resolution)", "content": ""}
        ],
        "progressive_character_plan": [
            {"title": "第一波開篇 (Wave 1)", "content": ""},
            {"title": "第二波發展 (Wave 2)", "content": ""},
            {"title": "第三波高潮 (Wave 3)", "content": ""}
        ],
        "foreshadowing_seeds": [],
        "key_turning_points": []
    }

    if not content:
        return default_structure
    
    if isinstance(content, str):
        if "\n\n【全域" in content:
            content = content.split("\n\n【全域")[0]
            
    content_stripped = content.strip()
    # 💡 核心修復：處理 markdown codeblock 包含的 JSON 格式
    if "```" in content_stripped:
        import re
        cleaned = re.sub(r"<think>.*?</think>", "", content_stripped, flags=re.DOTALL).strip()
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if json_match:
            content_stripped = json_match.group(1).strip()
        else:
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace != -1:
                content_stripped = cleaned[first_brace:last_brace + 1].strip()

    if content_stripped.startswith("{") and content_stripped.endswith("}"):
        try:
            parsed = json.loads(content_stripped)
            
            ta = parsed.get("multi_act_structure", [])
            normalized_ta = []
            if isinstance(ta, list):
                for idx, item in enumerate(ta):
                    if isinstance(item, dict):
                        normalized_ta.append({
                            "title": item.get("title", f"項目 #{idx + 1}"),
                            "content": item.get("content", "")
                        })
                    else:
                        normalized_ta.append({
                            "title": f"項目 #{idx + 1}",
                            "content": str(item)
                        })
            elif isinstance(ta, dict):
                normalized_ta = [
                    {"title": "第一幕 (Setup)", "content": ta.get("act1_setup", ta.get("act1", ""))},
                    {"title": "第二幕 (Confrontation)", "content": ta.get("act2_confrontation", ta.get("act2", ""))},
                    {"title": "第三幕 (Resolution)", "content": ta.get("act3_resolution", ta.get("act3", ""))}
                ]
            else:
                normalized_ta = default_structure["multi_act_structure"]

            cp = parsed.get("progressive_character_plan", [])
            normalized_cp = []
            if isinstance(cp, list):
                for idx, item in enumerate(cp):
                    if isinstance(item, dict):
                        normalized_cp.append({
                            "title": item.get("title", f"階段 #{idx + 1}"),
                            "content": item.get("content", "")
                        })
                    else:
                        normalized_cp.append({
                            "title": f"階段 #{idx + 1}",
                            "content": str(item)
                        })
            elif isinstance(cp, dict):
                normalized_cp = [
                    {"title": "第一波開篇 (Wave 1)", "content": cp.get("wave_1_opening", "")},
                    {"title": "第二波發展 (Wave 2)", "content": cp.get("wave_2_development", "")},
                    {"title": "第三波高潮 (Wave 3)", "content": cp.get("wave_3_climax", "")}
                ]
            else:
                normalized_cp = default_structure["progressive_character_plan"]

            result_obj = parsed.copy()
            result_obj.update({
                "theme": parsed.get("theme", ""),
                "main_conflict": parsed.get("main_conflict", ""),
                "worldview": parsed.get("worldview", ""),
                "macro_outline": parsed.get("macro_outline", ""),
                "multi_act_structure": normalized_ta,
                "progressive_character_plan": normalized_cp,
                "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []) if isinstance(parsed.get("foreshadowing_seeds"), list) else [],
                "key_turning_points": parsed.get("key_turning_points", []) if isinstance(parsed.get("key_turning_points"), list) else []
            })
            return result_obj

        except Exception as e:
            print(f"[WARN] parse_worldview_to_json JSON load failed: {e}. Falling back to text parser.")
            
    result = {
        "theme": "",
        "main_conflict": "",
        "worldview": "",
        "macro_outline": "",
        "multi_act_structure": [
            {"title": "第一幕 (Setup)", "content": ""},
            {"title": "第二幕 (Confrontation)", "content": ""},
            {"title": "第三幕 (Resolution)", "content": ""}
        ],
        "progressive_character_plan": [
            {"title": "第一波開篇 (Wave 1)", "content": ""},
            {"title": "第二波發展 (Wave 2)", "content": ""},
            {"title": "第三波高潮 (Wave 3)", "content": ""}
        ],
        "foreshadowing_seeds": [],
        "key_turning_points": []
    }
    
    headers = [
        "【核心主題】",
        "【核心衝突】",
        "【世界觀設定】",
        "【整體故事大綱】",
        "【多幕式結構】",
        "【角色漸進規劃策略】",
        "【伏筆種子】",
        "【關鍵轉折點】"
    ]
    
    pos = []
    for h in headers:
        idx = content.find(h)
        if idx != -1:
            pos.append((idx, h))
    pos.sort()
    
    sections = {}
    for i in range(len(pos)):
        start_idx = pos[i][0] + len(pos[i][1])
        end_idx = pos[i+1][0] if i + 1 < len(pos) else len(content)
        sections[pos[i][1]] = content[start_idx:end_idx].strip()
        
    if "【核心主題】" in sections:
        result["theme"] = sections["【核心主題】"]
    if "【核心衝突】" in sections:
        result["main_conflict"] = sections["【核心衝突】"]
    if "【世界觀設定】" in sections:
        result["worldview"] = sections["【世界觀設定】"]
    if "【整體故事大綱】" in sections:
        result["macro_outline"] = sections["【整體故事大綱】"]
        
    if "【多幕式結構】" in sections:
        three_act_text = sections["【多幕式結構】"]
        parsed_ta = []
        for line in three_act_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            clean_line = line[1:].strip() if (line.startswith("-") or line.startswith("•") or line.startswith("*")) else line
            if "：" in clean_line or ":" in clean_line:
                sep = "：" if "：" in clean_line else ":"
                parts = clean_line.split(sep, 1)
                title = parts[0].strip()
                content_text = parts[1].strip()
                parsed_ta.append({"title": title, "content": content_text})
            else:
                parsed_ta.append({"title": f"項目 #{len(parsed_ta) + 1}", "content": clean_line})
        if parsed_ta:
            result["multi_act_structure"] = parsed_ta

    if "【角色漸進規劃策略】" in sections:
        prog_text = sections["【角色漸進規劃策略】"]
        parsed_cp = []
        for line in prog_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            clean_line = line[1:].strip() if (line.startswith("-") or line.startswith("•") or line.startswith("*")) else line
            if "：" in clean_line or ":" in clean_line:
                sep = "：" if "：" in clean_line else ":"
                parts = clean_line.split(sep, 1)
                title = parts[0].strip()
                content_text = parts[1].strip()
                parsed_cp.append({"title": title, "content": content_text})
            else:
                parsed_cp.append({"title": f"階段 #{len(parsed_cp) + 1}", "content": clean_line})
        if parsed_cp:
            result["progressive_character_plan"] = parsed_cp
                        
    if "【伏筆種子】" in sections:
        seeds_text = sections["【伏筆種子】"]
        for line in seeds_text.split("\n"):
            line = line.strip()
            if line.startswith("•") or line.startswith("-") or line.startswith("*"):
                line = line[1:].strip()
            if line:
                result["foreshadowing_seeds"].append(line)
                
    if "【關鍵轉折點】" in sections:
        pts_text = sections["【關鍵轉折點】"]
        for line in pts_text.split("\n"):
            line = line.strip()
            if line.startswith("•") or line.startswith("-") or line.startswith("*"):
                line = line[1:].strip()
            if line:
                result["key_turning_points"].append(line)
                
    return result

def append_foreshadowing(novel_id, new_seed):
    wb = get_latest_worldbuilding(novel_id)
    if not wb:
        return None
    
    current_content = wb["content"]
    if current_content and current_content.strip().startswith("{"):
        try:
            parsed = parse_worldview_to_json(current_content)
            if "foreshadowing_seeds" not in parsed:
                parsed["foreshadowing_seeds"] = []
            parsed["foreshadowing_seeds"].append(new_seed)
            return save_worldbuilding(novel_id, json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[ERROR] JSON append failed: {e}. Falling back to text append.")

    if "伏筆種子" in current_content:
        parts = current_content.split("【伏筆種子】")
        if len(parts) > 1:
            new_part = parts[1]
            if new_part.strip():
                lines = new_part.strip().split("\n")
                last_idx = len(lines) - 1
                while last_idx >= 0 and not lines[last_idx].strip():
                    last_idx -= 1
                if last_idx >= 0:
                    lines.insert(last_idx + 1, f"  • {new_seed}")
                    new_part = "\n".join(lines)
            parts[1] = new_part
            new_content = "【伏筆種子】".join(parts)
        else:
            new_content = current_content + f"\n  • {new_seed}"
    else:
        new_content = current_content + f"\n\n【伏筆種子】\n  • {new_seed}"
    
    return save_worldbuilding(novel_id, new_content)

def insert_plot_chapter(novel_id, insert_after_index, new_chapter, skip_volume_sync=False):
    plot_data = get_stitched_plot(novel_id)
    if not plot_data:
        plot_data = {"chapters": []}
    
    if "chapters" not in plot_data:
        plot_data["chapters"] = []
    
    chapters = plot_data["chapters"]
    
    # 💡 核心修復：根據 chapter_index 尋找插入位置，而不是陣列索引！
    # 支援 1-based 的 chapter_index。若 insert_after_index 為 0，代表插入到最前面。
    insert_pos = -1
    if insert_after_index <= 0:
        insert_pos = 0
    else:
        for idx, ch in enumerate(chapters):
            try:
                if int(ch.get("chapter_index", 0)) == int(insert_after_index):
                    insert_pos = idx + 1
                    break
            except:
                pass
                
    if insert_pos == -1:
        new_chapter["chapter_index"] = len(chapters) + 1
        chapters.append(new_chapter)
    else:
        new_chapter["chapter_index"] = insert_pos + 1
        chapters.insert(insert_pos, new_chapter)
        
    # 重新對所有章節重新編排 chapter_index 確保連續
    for idx, ch in enumerate(chapters):
        ch["chapter_index"] = idx + 1

    # 💡 核心優化：同步將 `chapters` 表（已寫正文）大於等於插入位置的章節索引向後平移 1，避免正文與大綱對接錯位！
    if insert_pos != -1:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chapters SET chapter_index = chapter_index + 1 WHERE novel_id = ? AND chapter_index >= ?",
            (novel_id, insert_pos + 1)
        )
        conn.commit()
        conn.close()
    
    return save_plot_chapters(novel_id, plot_data, skip_volume_sync=skip_volume_sync)


from agent_json import CHARACTER_BASIC_FIELDS
ALLOWED_CHARACTER_FIELDS = set(CHARACTER_BASIC_FIELDS) | {"identity"}

def normalize_char_index(raw_index, total_chars, source='unknown'):
    if 0 <= raw_index < total_chars:
        return raw_index
    if 1 <= raw_index <= total_chars:
        print(f"[WARN] {source}: received 1-based index {raw_index}, converting to 0-based {raw_index - 1}")
        return raw_index - 1
    raise IndexError(f"Character index {raw_index} out of range [0, {total_chars}) from {source}")

def update_character_field(novel_id, char_index, field_name, new_value):
    if field_name not in ALLOWED_CHARACTER_FIELDS:
        print(f"[ERROR] Field '{field_name}' is not in character fields whitelist")
        return None
        
    char_data = get_latest_characters(novel_id)
    if not char_data or "parsed_data" not in char_data:
        return None
    
    parsed = char_data["parsed_data"]
    if "characters" not in parsed:
        return None
    
    try:
        norm_idx = normalize_char_index(char_index, len(parsed["characters"]), source='update_character_field')
    except IndexError:
        return None
    
    parsed["characters"][norm_idx][field_name] = new_value
    
    return save_characters(novel_id, parsed)


def update_character_single_field(novel_id, char_index, field_name, new_value):
    result = update_character_field(novel_id, char_index, field_name, new_value)
    if result:
        return {"status": "success", "version": result}
    return {"status": "error", "message": "Failed to update character field"}

def append_worldbuilding_list(novel_id, key_section, new_item):
    wb = get_latest_worldbuilding(novel_id)
    if not wb:
        return None
    
    current_content = wb["content"]
    parsed = parse_worldview_to_json(current_content)
    
    if key_section not in parsed or not isinstance(parsed[key_section], list):
        parsed[key_section] = []
        
    if isinstance(new_item, list):
        for item in new_item:
            if isinstance(item, str) and item not in parsed[key_section]:
                parsed[key_section].append(item)
    else:
        if isinstance(new_item, str) and new_item not in parsed[key_section]:
            parsed[key_section].append(new_item)
            
    return save_worldbuilding(novel_id, json.dumps(parsed, ensure_ascii=False, indent=2))

def update_volume(novel_id, volume_index, title, summary, factions):
    conn = get_db_connection()
    cursor = conn.cursor()
    if isinstance(factions, list) or isinstance(factions, dict):
        factions = json.dumps(_convert_obj_to_traditional(factions), ensure_ascii=False)
    else:
        factions = _to_traditional(factions)
        
    # Check if volume already exists
    row = cursor.execute(
        "SELECT id FROM volumes WHERE novel_id = ? AND volume_index = ?",
        (novel_id, volume_index)
    ).fetchone()
    
    if row:
        cursor.execute(
            "UPDATE volumes SET title = ?, summary = ?, factions = ? WHERE novel_id = ? AND volume_index = ?",
            (_to_traditional(title), _to_traditional(summary), factions, novel_id, volume_index)
        )
    else:
        cursor.execute(
            "INSERT INTO volumes (novel_id, volume_index, title, summary, factions, is_dirty, chapters_outline, chapter_count) VALUES (?, ?, ?, ?, ?, 0, '[]', 50)",
            (novel_id, volume_index, _to_traditional(title), _to_traditional(summary), factions)
        )
    conn.commit()
    conn.close()

def delete_volume(novel_id, volume_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 取得所有篇卷，以便在刪除前計算章節範圍與章節數
    rows = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,)).fetchall()
    vols = [dict(r) for r in rows]
    
    if not vols:
        conn.close()
        return
        
    start_ch, end_ch = get_volume_chapter_range(vols, volume_index)
    ch_count = end_ch - start_ch + 1
    
    # 2. 從 volumes 表中刪除該卷
    cursor.execute("DELETE FROM volumes WHERE novel_id = ? AND volume_index = ?", (novel_id, volume_index))
    
    # 3. 對剩餘的所有卷進行 volume_index 重排，確保 1-indexed 連續無縫，並同步平移及更新每個餘下卷內 chapters_outline 中的 chapter_index
    remaining_rows = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,)).fetchall()
    for idx, r in enumerate(remaining_rows):
        new_vol_idx = idx + 1
        old_vol_idx = r["volume_index"]
        
        # 解析並處理該卷對應的 chapters_outline
        ch_outline_str = r["chapters_outline"]
        updated_outline_str = ch_outline_str
        if ch_outline_str:
            try:
                ch_list = json.loads(ch_outline_str)
                if isinstance(ch_list, list):
                    updated_chaps = []
                    for c in ch_list:
                        c_idx = int(c.get("chapter_index", 0))
                        if start_ch <= c_idx <= end_ch:
                            continue # 剔除已被刪除卷範圍內的章節
                        elif c_idx > end_ch:
                            c["chapter_index"] = c_idx - ch_count # 平移後續章節 index
                        updated_chaps.append(c)
                    updated_outline_str = json.dumps(updated_chaps, ensure_ascii=False)
            except Exception as e:
                print(f"[ERROR] Failed to update chapters_outline for vol {old_vol_idx}: {e}")
                
        cursor.execute(
            "UPDATE volumes SET volume_index = ?, chapters_outline = ? WHERE id = ?",
            (new_vol_idx, updated_outline_str, r["id"])
        )
            
    # 4. 同步更新 worldbuilding 表中最先進世界觀 JSON 數據，防止幽靈卷殘留
    wb_row = cursor.execute("SELECT * FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC LIMIT 1", (novel_id,)).fetchone()
    if wb_row:
        wb_data = dict(wb_row)
        try:
            current_json = json.loads(wb_data["content"])
            if isinstance(current_json, dict) and "volumes" in current_json:
                v_list = current_json["volumes"]
                if isinstance(v_list, list):
                    # 篩選掉被刪除的那一卷
                    updated_v_list = [v for v in v_list if int(v.get("volume_index", 0)) != volume_index]
                    # 重新編排 volume_index
                    for idx, v in enumerate(updated_v_list):
                        v["volume_index"] = idx + 1
                    current_json["volumes"] = updated_v_list
                    
                    next_wb_version = int(wb_data.get("version", 0)) + 1
                    cursor.execute(
                        "INSERT INTO worldbuilding (novel_id, content, version) VALUES (?, ?, ?)",
                        (novel_id, json.dumps(_convert_obj_to_traditional(current_json), ensure_ascii=False, indent=2), next_wb_version)
                    )
        except Exception as e:
            print(f"[ERROR] Failed to synchronize worldview JSON: {e}")

    # 5. 刪除對應的已寫正文章節，並將其後所有章節的 chapter_index 向前平移以填補空洞
    cursor.execute("DELETE FROM chapters WHERE novel_id = ? AND chapter_index >= ? AND chapter_index <= ?", (novel_id, start_ch, end_ch))
    cursor.execute("UPDATE chapters SET chapter_index = chapter_index - ? WHERE novel_id = ? AND chapter_index > ?", (ch_count, novel_id, end_ch))
    
    # 6. 自大綱（plot_chapters 表）中剔除該卷的章節，並將後續大綱章節的 chapter_index 同步向前平移
    plot_rows = cursor.execute("SELECT * FROM plot_chapters WHERE novel_id = ? ORDER BY version DESC LIMIT 1", (novel_id,)).fetchall()
    if plot_rows:
        latest = dict(plot_rows[0])
        try:
            parsed = json.loads(latest["outline_json"])
            if isinstance(parsed, dict) and "chapters" in parsed:
                chaps = parsed["chapters"]
                updated_chaps = []
                for c in chaps:
                    c_idx = int(c.get("chapter_index", 0))
                    if start_ch <= c_idx <= end_ch:
                        continue # 剔除被刪卷的章節
                    elif c_idx > end_ch:
                        c["chapter_index"] = c_idx - ch_count # 平移後續章節
                    updated_chaps.append(c)
                parsed["chapters"] = updated_chaps
                
                next_version = int(latest.get("version", 0)) + 1
                cursor.execute(
                    "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, ?, 0)",
                    (novel_id, json.dumps(_convert_obj_to_traditional(parsed), ensure_ascii=False), next_version)
                )
        except Exception as e:
            print(f"[ERROR] Failed to update plot chapters: {e}")
            
    conn.commit()
    conn.close()
    
    try:
        precompute_global_foreshadowing(novel_id)
    except Exception as e:
        print(f"[WARN] Failed to auto-precompute global foreshadowing inside delete_volume: {e}")

def get_stitched_plot(novel_id):
    volumes = get_volumes(novel_id)
    stitched_chapters = []
    
    for vol in volumes:
        ch_list = vol.get("chapters_outline")
        if ch_list and isinstance(ch_list, list) and len(ch_list) > 0:
            stitched_chapters.extend(ch_list)
    
    if stitched_chapters:
        try:
            stitched_chapters.sort(key=lambda x: int(x.get("chapter_index", 0)) if x.get("chapter_index") is not None else 99999)
        except:
            pass
        return {"chapters": stitched_chapters}
        
    plot = get_latest_plot_chapters(novel_id)
    return plot["parsed_data"] if plot else {"chapters": []}


# ==============================================================================
# NEW: 四階段大綱生成策略 - Stage 2 & Stage 3 資料庫函數
# ==============================================================================

def save_volume_skeletons(novel_id, volume_index, chapters_skeleton):
    """
    [新功能] 保存某卷的簡易章節骨架大綱到 volumes 表的 chapters_outline 欄位
    這是 Stage 2 (Volume Skeleton) 的產出儲存點，強制過濾超界章節。
    """
    volumes = get_volumes(novel_id)
    start_ch, end_ch = get_volume_chapter_range(volumes, volume_index)
    
    # 過濾出界章節，避免不連續跳號或骨架寫入其他卷
    cleaned_skeleton = []
    for ch in chapters_skeleton:
        c_idx = ch.get("chapter_index")
        if c_idx is not None:
            try:
                c_idx_int = int(c_idx)
                if start_ch <= c_idx_int <= end_ch:
                    cleaned_skeleton.append(ch)
                else:
                    print(f"[WARN] save_volume_skeletons filtered out out-of-bounds chapter {c_idx_int} for Vol {volume_index} (expected [{start_ch}, {end_ch}])")
            except:
                pass
        else:
            cleaned_skeleton.append(ch)
            
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 將章節骨架轉為 JSON 並保存
    skeleton_json = json.dumps(_convert_obj_to_traditional(cleaned_skeleton), ensure_ascii=False, indent=2)
    
    # 更新 volumes 表中該卷的 chapters_outline
    cursor.execute(
        "UPDATE volumes SET chapters_outline = ? WHERE novel_id = ? AND volume_index = ?",
        (skeleton_json, novel_id, volume_index)
    )
    
    # 如果該卷記錄不存在，則新增
    if cursor.rowcount == 0:
        from db import get_volumes, get_volume_chapter_range
        volumes = get_volumes(novel_id)
        start_ch, end_ch = get_volume_chapter_range(volumes, volume_index)
        cursor.execute(
            "INSERT INTO volumes (novel_id, volume_index, title, summary, factions, is_dirty, chapters_outline) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (novel_id, volume_index, f"第 {volume_index} 卷", f"本卷包含第 {start_ch} 章至第 {end_ch} 章的簡易骨架大綱。", "全域陣列", skeleton_json)
        )
    
    conn.commit()
    conn.close()
    print(f"[DB] Volume {volume_index} skeleton saved successfully")


def get_all_volume_skeletons(novel_id):
    """
    [新功能] 獲取所有卷的簡易章節骨架（用於 Stage 3 全局伏筆編織）
    """
    volumes = get_volumes(novel_id)
    all_skeletons = []
    
    for vol in volumes:
        ch_outline_str = vol.get("chapters_outline")
        if ch_outline_str:
            try:
                ch_list = ch_outline_str if isinstance(ch_outline_str, list) else json.loads(ch_outline_str or "[]")
                if isinstance(ch_list, list) and len(ch_list) > 0:
                    # 為每個章節附加 volume_index 資訊
                    vol_idx = int(vol.get("volume_index", 0))
                    vol_title = vol.get("title", f"第 {vol_idx} 卷")
                    for ch in ch_list:
                        ch["volume_index"] = vol_idx
                        ch["volume_title"] = vol_title
                    all_skeletons.extend(ch_list)
            except Exception as e:
                print(f"[WARN] Failed to parse skeleton for vol {vol.get('volume_index')}: {e}")
    
    # 按章節序號排序
    all_skeletons.sort(key=lambda x: int(x.get("chapter_index", 0)) if x.get("chapter_index") is not None else 99999)
    
    return all_skeletons


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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 建立 chapter_index -> allocation 的映射
        allocation_map = {}
        for alloc in allocations:
            ch_idx = alloc.get("chapter_index")
            if ch_idx is not None:
                allocation_map[int(ch_idx)] = alloc
        
        # 取得所有 volumes
        cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,))
        volume_rows = cursor.fetchall()
        
        for vol_row in volume_rows:
            vol = dict(vol_row)
            ch_outline_str = vol.get("chapters_outline")
            if not ch_outline_str:
                continue
            
            try:
                ch_list = json.loads(ch_outline_str)
                if not isinstance(ch_list, list):
                    continue
                    
                modified = False
                for ch in ch_list:
                    ch_idx = int(ch.get("chapter_index", 0))
                    if ch_idx in allocation_map:
                        alloc = allocation_map[ch_idx]
                        
                        # 💡【Step 6 修復】：確保原本的章節骨架基礎欄位不被覆蓋或遺漏
                        ch["chapter_title"] = ch.get("chapter_title") or ch.get("title") or "待設定標題"
                        ch["chapter_summary"] = ch.get("chapter_summary") or ch.get("summary") or "待設定摘要"
                        
                        # 更新 allocated_tasks
                        if "allocated_tasks" not in ch:
                            ch["allocated_tasks"] = {}
                        
                        alloc_tasks = ch["allocated_tasks"]
                        if "foreshadowing_plants" in alloc:
                            existing_plants = alloc_tasks.get("foreshadowing_plants", [])
                            if isinstance(existing_plants, list):
                                for plant in alloc["foreshadowing_plants"]:
                                    if plant not in existing_plants:
                                        existing_plants.append(plant)
                            else:
                                alloc_tasks["foreshadowing_plants"] = alloc["foreshadowing_plants"]
                        
                        if "foreshadowing_payoffs" in alloc:
                            existing_payoffs = alloc_tasks.get("foreshadowing_payoffs", [])
                            if isinstance(existing_payoffs, list):
                                for payoff in alloc["foreshadowing_payoffs"]:
                                    if payoff not in existing_payoffs:
                                        existing_payoffs.append(payoff)
                            else:
                                alloc_tasks["foreshadowing_payoffs"] = alloc["foreshadowing_payoffs"]
                        
                        if "turning_points" in alloc:
                            existing_tps = alloc_tasks.get("turning_points", [])
                            if isinstance(existing_tps, list):
                                for tp in alloc["turning_points"]:
                                    if tp not in existing_tps:
                                        existing_tps.append(tp)
                            else:
                                alloc_tasks["turning_points"] = alloc["turning_points"]
                        
                        modified = True
                
                if modified:
                    # 回寫到資料庫
                    new_outline_json = json.dumps(_convert_obj_to_traditional(ch_list), ensure_ascii=False, indent=2)
                    cursor.execute(
                        "UPDATE volumes SET chapters_outline = ? WHERE id = ?",
                        (new_outline_json, vol_row["id"])
                    )
                    
            except Exception as e:
                print(f"[WARN] Failed to update allocations for vol {vol.get('volume_index')}: {e}")
        
        conn.commit()
        print(f"[DB] Foreshadowing allocations saved successfully for {novel_id}")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed to save foreshadowing allocations: {e}")
        raise
    finally:
        conn.close()


def delete_and_shift_surrounding_chapters(novel_id, target_chapter_index):
    """
    [微創自癒協議] 刪除指定章節前後 +-3 章節（即 N-3 至 N+3）的大綱與已寫正文，
    並將後續所有章節的 chapter_index 向前平移，最後將所屬篇卷標記為 dirty 以觸發重新生成與對齊。
    """
    import re
    from datetime import datetime
    N = int(target_chapter_index)
    start_del = max(1, N - 3)
    end_del = N + 3
    del_count = end_del - start_del + 1
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 刪除 `chapters` 表（已寫正文）範圍內的章節
    cursor.execute(
        "DELETE FROM chapters WHERE novel_id = ? AND chapter_index >= ? AND chapter_index <= ?",
        (novel_id, start_del, end_del)
    )
    
    # 2. 將 `chapters` 表後續已寫正文的索引向前平移 `del_count`
    cursor.execute(
        "UPDATE chapters SET chapter_index = chapter_index - ? WHERE novel_id = ? AND chapter_index > ?",
        (del_count, novel_id, end_del)
    )
    
    # 3. 從 `plot_chapters` 主表中刪除範圍內大綱，並對後續大綱做向前平移
    plot_row = cursor.execute(
        "SELECT * FROM plot_chapters WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    
    if plot_row and plot_row["outline_json"]:
        try:
            parsed = json.loads(plot_row["outline_json"])
            chaps = parsed.get("chapters", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
            updated_chaps = []
            for c in chaps:
                c_idx = int(c.get("chapter_index", 0))
                if start_del <= c_idx <= end_del:
                    continue  # 剔除範圍內大綱
                elif c_idx > end_del:
                    c["chapter_index"] = c_idx - del_count  # 向前平移
                updated_chaps.append(c)
                
            parsed_final = {"chapters": updated_chaps} if isinstance(parsed, dict) else updated_chaps
            next_version = (plot_row["version"] or 0) + 1
            cursor.execute(
                "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, ?, 1)",
                (novel_id, json.dumps(parsed_final, ensure_ascii=False), next_version)
            )
        except Exception as e:
            print(f"[ERROR] Failed to update plot chapters in delete_and_shift_surrounding_chapters: {e}")
            
    # 4. 對各卷的 `chapters_outline` 及 `chapters_skeleton` 進行同樣的平移與剔除
    v_rows = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,)).fetchall()
    vols = [dict(vr) for vr in v_rows]
    
    for r in vols:
        vol_idx = r["volume_index"]
        ch_outline_str = r["chapters_outline"]
        updated_outline_str = ch_outline_str
        
        # 標記被影響卷為 dirty (is_dirty = 1)
        # 凡是包含刪除範圍或在其之後的卷都標記為 dirty
        is_vol_dirty = 0
        v_start, v_end = get_volume_chapter_range(vols, vol_idx)
        if v_end >= start_del:
            is_vol_dirty = 1
            
        if ch_outline_str:
            try:
                ch_list = json.loads(ch_outline_str)
                if isinstance(ch_list, list):
                    updated_chaps = []
                    for c in ch_list:
                        c_idx = int(c.get("chapter_index", 0))
                        if start_del <= c_idx <= end_del:
                            continue
                        elif c_idx > end_del:
                            c["chapter_index"] = c_idx - del_count
                        updated_chaps.append(c)
                    updated_outline_str = json.dumps(updated_chaps, ensure_ascii=False)
            except Exception as e:
                print(f"[ERROR] Failed to update chapters_outline in delete_and_shift_surrounding_chapters: {e}")
                
        cursor.execute(
            "UPDATE volumes SET chapters_outline = ?, is_dirty = ? WHERE id = ?",
            (updated_outline_str, is_vol_dirty, r["id"])
        )
        
    conn.commit()
    conn.close()
    print(f"[HEALING SUCCESS] Deleted and shifted chapter range [{start_del}, {end_del}] for novel {novel_id}.")

    try:
        precompute_global_foreshadowing(novel_id)
    except Exception as e:
        print(f"[WARN] Failed to recompute foreshadowing blueprint after chapter shift: {e}")

    try:
        repair_foreshadowing_allocations(novel_id)
    except Exception as e:
        print(f"[WARN] Failed to repair foreshadowing allocations after chapter shift: {e}")

    return start_del, end_del



def _canonical_seed_id(seed_index):
    return f"FS{seed_index + 1:03d}"


def _coerce_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _normalize_allocation_pair(pair, total_chapters):
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    p_ch = _coerce_int(pair[0])
    r_ch = _coerce_int(pair[1])
    if total_chapters <= 0:
        total_chapters = max(p_ch, r_ch, 1)
    p_ch = max(1, min(total_chapters, p_ch))
    r_ch = max(1, min(total_chapters, r_ch))
    if total_chapters > 1 and r_ch <= p_ch:
        p_ch = max(1, min(total_chapters - 1, p_ch))
        r_ch = p_ch + 1
    return p_ch, r_ch


def _is_valid_foreshadowing_blueprint(blueprint, seed_count, turn_count, total_chapters):
    if not isinstance(blueprint, dict):
        return False
    allocations = blueprint.get("foreshadowing_allocations", [])
    turns = blueprint.get("turning_allocations", [])
    if len(allocations) != seed_count or len(turns) != turn_count:
        return False
    if total_chapters <= 1:
        return True
    for pair in allocations:
        normalized = _normalize_allocation_pair(pair, total_chapters)
        if not normalized:
            return False
        p_ch, r_ch = normalized
        if total_chapters > 1 and p_ch >= r_ch:
            return False
    for turn_ch in turns:
        turn_ch = _coerce_int(turn_ch)
        if turn_ch < 1 or (total_chapters > 0 and turn_ch > total_chapters):
            return False
    return True


def build_canonical_foreshadowing_task_map(novel_id):
    """Return chapter_index -> canonical allocated_tasks from the deterministic blueprint."""
    volumes = get_volumes(novel_id)
    if not volumes:
        return {}
    wb = get_latest_worldbuilding(novel_id)
    worldview = parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    seeds = worldview.get("foreshadowing_seeds", []) or []
    turns = worldview.get("key_turning_points", []) or []
    blueprint = get_global_foreshadowing_blueprint(novel_id)
    total_chapters = _coerce_int(blueprint.get("T"), get_total_chapter_count(volumes))

    task_map = {}

    def chapter_tasks(chapter_index):
        chapter_index = int(chapter_index)
        if chapter_index not in task_map:
            task_map[chapter_index] = {
                "foreshadowing_plants": [],
                "foreshadowing_payoffs": [],
                "turning_points": []
            }
        return task_map[chapter_index]

    for idx, pair in enumerate(blueprint.get("foreshadowing_allocations", [])[:len(seeds)]):
        normalized = _normalize_allocation_pair(pair, total_chapters)
        if not normalized:
            continue
        p_ch, r_ch = normalized
        seed_id = _canonical_seed_id(idx)
        chapter_tasks(p_ch)["foreshadowing_plants"].append(seed_id)
        chapter_tasks(r_ch)["foreshadowing_payoffs"].append(seed_id)

    for idx, turn_ch in enumerate(blueprint.get("turning_allocations", [])[:len(turns)]):
        turn_ch = _coerce_int(turn_ch)
        if turn_ch <= 0:
            continue
        chapter_tasks(turn_ch)["turning_points"].append(f"TP{idx + 1:03d}")

    return task_map


def apply_canonical_allocated_tasks_to_chapters(novel_id, chapters):
    """Overwrite foreshadowing/turn allocations so each seed has one plant and one payoff."""
    task_map = build_canonical_foreshadowing_task_map(novel_id)
    normalized = {}
    for chapter in chapters or []:
        if not isinstance(chapter, dict):
            continue
        ch_idx = chapter.get("chapter_index")
        if ch_idx is None:
            continue
        ch_idx = int(ch_idx)
        chapter["chapter_index"] = ch_idx
        allocated = chapter.get("allocated_tasks")
        if not isinstance(allocated, dict):
            allocated = {}
        canonical = task_map.get(ch_idx, {})
        allocated["foreshadowing_plants"] = list(canonical.get("foreshadowing_plants", []))
        allocated["foreshadowing_payoffs"] = list(canonical.get("foreshadowing_payoffs", []))
        allocated["turning_points"] = list(canonical.get("turning_points", []))
        chapter["allocated_tasks"] = allocated
        for stale_key in (
            "foreshadowing_plant",
            "foreshadowing_plants",
            "foreshadowing_payoff",
            "foreshadowing_payoffs",
            "foreshadowing",
        ):
            chapter.pop(stale_key, None)
        normalized[ch_idx] = chapter
    return normalized


def repair_foreshadowing_allocations(novel_id, volume_index=None):
    """Rewrite existing volume skeletons and stitched plot with deterministic allocations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if volume_index is None:
        rows = cursor.execute(
            "SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC",
            (novel_id,)
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT * FROM volumes WHERE novel_id = ? AND volume_index = ? ORDER BY volume_index ASC",
            (novel_id, int(volume_index))
        ).fetchall()

    all_chapters = []
    touched = 0
    for row in rows:
        vol = dict(row)
        try:
            chapters = json.loads(vol.get("chapters_outline") or "[]")
        except Exception:
            chapters = []
        if not isinstance(chapters, list):
            chapters = []
        canonical_map = apply_canonical_allocated_tasks_to_chapters(novel_id, chapters)
        canonical_list = list(canonical_map.values())
        canonical_list.sort(key=lambda item: int(item.get("chapter_index", 0)))
        cursor.execute(
            "UPDATE volumes SET chapters_outline = ? WHERE id = ?",
            (json.dumps(_convert_obj_to_traditional(canonical_list), ensure_ascii=False), vol["id"])
        )
        all_chapters.extend(canonical_list)
        touched += 1

    if volume_index is None and all_chapters:
        all_chapters.sort(key=lambda item: int(item.get("chapter_index", 0)))
        row_max = cursor.execute(
            "SELECT MAX(version) as max_v FROM plot_chapters WHERE novel_id = ?",
            (novel_id,)
        ).fetchone()
        next_v = (row_max["max_v"] or 0) + 1
        cursor.execute(
            "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, ?, 0)",
            (novel_id, json.dumps({"chapters": _convert_obj_to_traditional(all_chapters)}, ensure_ascii=False), next_v)
        )

    conn.commit()
    conn.close()
    return touched

def precompute_global_foreshadowing(novel_id):
    """
    [新功能] 根據卷結構與世界觀伏筆/轉折設定，預計算全書總章數與全域伏筆/轉折的絕對章節分配，
    並儲存為單一且確定的 Blueprint JSON，防止 volume_skeleton 生成時漂移。
    """
    # 1. 取得所有篇卷，計算總章數 T
    volumes = get_volumes(novel_id)
    if not volumes:
        from config import MIN_VOLUME_COUNT, MIN_CHAPTERS_PER_VOLUME
        return {
            "T": MIN_VOLUME_COUNT * MIN_CHAPTERS_PER_VOLUME,
            "foreshadowing_allocations": [],
            "turning_allocations": []
        }
        
    sorted_vols = sorted(volumes, key=lambda x: int(x.get("volume_index", 0)))
    _, T = get_volume_chapter_range(volumes, sorted_vols[-1]["volume_index"])
    
    # 2. 取得世界觀中所有的伏筆種子與關鍵轉折點
    wb = get_latest_worldbuilding(novel_id)
    worldview_parsed = parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview_parsed.get("foreshadowing_seeds", [])
    all_turns = worldview_parsed.get("key_turning_points", [])
    
    import hashlib
    import random
    
    # 3. 初始化確定性隨機數生成器
    h_seed = int(hashlib.md5(f"global_blueprint_{novel_id}".encode('utf-8')).hexdigest(), 16) % (2**32)
    r = random.Random(h_seed)
    
    # 4. 確定性循環對齊散射：保證每個卷均勻分配到伏筆埋設與回收任務，絕不漏空
    foreshadowing_allocations = []
    V = len(sorted_vols)
    MIN_PAYOFF_DISTANCE = max(20, int(T * 0.05))
    
    for idx, seed in enumerate(all_seeds):
        if V <= 1:
            # 單卷時保底前後散射
            start_p, end_p = get_volume_chapter_range(volumes, sorted_vols[0]["volume_index"])
            if end_p - start_p >= 1:
                P = r.randint(start_p, end_p - 1)
                R = r.randint(P + 1, end_p)
            else:
                P = start_p
                R = end_p
        else:
            # 多卷時，循環指定埋設卷與回收卷，保證跨卷張力
            v_p_idx = (idx % V) + 1  # 埋設卷
            if v_p_idx < V:
                v_r_idx = r.randint(v_p_idx + 1, V)  # 回收卷在埋設卷之後
            else:
                # 若為最後一卷，則將埋設點放到前面任意一卷，回收點放在最後一卷
                v_p_idx = r.randint(1, V - 1)
                v_r_idx = V
                
            start_p, end_p = get_volume_chapter_range(volumes, v_p_idx)
            start_r, end_r = get_volume_chapter_range(volumes, v_r_idx)
            
            P = r.randint(start_p, end_p)
            
            low = max(start_r, P + MIN_PAYOFF_DISTANCE)
            high = end_r
            if low > high:
                low = start_r
            if low > high:
                low = high
            R = r.randint(low, high)
            
        normalized_pair = _normalize_allocation_pair((P, R), T)
        if normalized_pair:
            foreshadowing_allocations.append(normalized_pair)
        
    # 5. 關鍵轉折點確定性循環位置分配，確保均勻覆蓋各卷
    turning_allocations = []
    for jdx, turn in enumerate(all_turns):
        if V > 0:
            v_k_idx = (jdx % V) + 1
            start_k, end_k = get_volume_chapter_range(volumes, v_k_idx)
            K = r.randint(start_k, end_k)
        else:
            K = r.randint(1, T)
        turning_allocations.append(K)
        
    blueprint = {
        "T": T,
        "foreshadowing_allocations": foreshadowing_allocations,
        "turning_allocations": turning_allocations
    }
    
    # 6. 保存至資料庫
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO foreshadowing_blueprints (novel_id, blueprint_json) VALUES (?, ?)",
        (novel_id, json.dumps(blueprint, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    
    print(f"[DB] Global foreshadowing blueprint precomputed successfully for novel {novel_id} (T={T})")
    return blueprint


def get_global_foreshadowing_blueprint(novel_id):
    """
    [新功能] 獲取預計算的伏筆分配藍圖。
    具備自癒檢驗：若藍圖長度與目前世界觀種子/轉折點個數不一致，或尚未預計算，則會自動重算！
    """
    wb = get_latest_worldbuilding(novel_id)
    worldview_parsed = parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_seeds = worldview_parsed.get("foreshadowing_seeds", [])
    all_turns = worldview_parsed.get("key_turning_points", [])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT blueprint_json FROM foreshadowing_blueprints WHERE novel_id = ?", (novel_id,)).fetchone()
    conn.close()
    
    if row:
        try:
            blueprint = json.loads(row["blueprint_json"])
            total_chapters = _coerce_int(blueprint.get("T"), get_total_chapter_count(get_volumes(novel_id)))
            if _is_valid_foreshadowing_blueprint(blueprint, len(all_seeds), len(all_turns), total_chapters):
                return blueprint
        except Exception as e:
            print(f"[WARN] Failed to load/validate global blueprint: {e}")
            
    # 若不一致或尚未預計算，自動觸發並回傳預計算結果
    return precompute_global_foreshadowing(novel_id)


from diagnostics import detect_current_stage, generate_validation_report



def save_single_plot_chapter(novel_id, chapter_index, chapter_outline):
    """
    [新功能] 保存或更新單個章節的大綱，同時保留大綱中所有其他章節，並正確同步到 volumes。
    """
    plot = get_stitched_plot(novel_id) or {"chapters": []}
    chapters = plot.get("chapters", [])
    if not isinstance(chapters, list):
        chapters = []
    
    # 確保章節 index 正確設定為整數
    try:
        chapter_index = int(chapter_index)
        chapter_outline["chapter_index"] = chapter_index
    except Exception as e:
        print(f"[WARN] save_single_plot_chapter: invalid chapter_index {chapter_index}: {e}")
    
    # 更新或追加到完整清單中
    updated = False
    for idx, ch in enumerate(chapters):
        try:
            curr_idx = int(ch.get("chapter_index") or ch.get("chapter") or 0)
            if curr_idx == chapter_index:
                chapters[idx] = chapter_outline
                updated = True
                break
        except:
            pass
            
    if not updated:
        chapters.append(chapter_outline)
        
    # 按 chapter_index 排序
    try:
        chapters.sort(key=lambda x: int(x.get("chapter_index", 0)) if x.get("chapter_index") is not None else 99999)
    except:
        pass
        
    # 調用全量 save_plot_chapters 完成寫入與 volumes 智慧合併
    save_plot_chapters(novel_id, {"chapters": chapters}, skip_volume_sync=False, clear_chapters=False)





