import sqlite3
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novel_factory.db")

# --- Agent Default Configurations from .env ---
AGENT_DEFAULTS = {
    "global": {
        "model": os.getenv("MODEL_GLOBAL", "google/gemma-3n-e4b-it"),
        "temperature": 0.70,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 1
    },
    "architect": {
        "model": os.getenv("MODEL_ARCHITECT", "qwen/qwen3.5-122b-a10b"),
        "temperature": 0.30,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 1
    },
    "character": {
        "model": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY", "openai/gpt-oss-120b"),
        "temperature": 0.40,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 1
    },
    "plot": {
        "model": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC", "qwen/qwen3.5-122b-a10b"),
        "temperature": 0.35,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 1
    },
    "writer": {
        "model": os.getenv("MODEL_WRITER", "nvidia/nemotron-3-super-120b-a12b"),
        "temperature": 0.65,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 1
    },
    "editor": {
        "model": os.getenv("MODEL_EDITOR", "mistralai/mistral-small-4-119b-2603"),
        "temperature": 0.25,
        "top_p": 0.90,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "copilot": {
        "model": os.getenv("MODEL_COPILOT", "stepfun-ai/step-3.5-flash"),
        "temperature": 0.55,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    }
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

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
    
    # Clean up empty configurations to let .env configuration take priority
    cursor.execute("DELETE FROM agent_configs WHERE api_key = '' OR api_key IS NULL")
    
    conn.commit()
    conn.close()

# --- NOVELS CRUD ---
def create_novel(novel_id, title, genre, style):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO novels (id, title, genre, style, pipeline_prompt) VALUES (?, ?, ?, ?, ?)",
        (novel_id, title, genre, style, "")
    )
    conn.commit()
    conn.close()

def update_novel_pipeline_prompt(novel_id, pipeline_prompt):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE novels SET pipeline_prompt = ? WHERE id = ?",
        (pipeline_prompt, novel_id)
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
def save_volumes(novel_id, volumes_list):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
    for idx, vol in enumerate(volumes_list):
        volume_index = vol.get("volume_index", idx + 1)
        title = vol.get("title", f"第 {volume_index} 卷")
        summary = vol.get("summary", "")
        factions = vol.get("factions", "")
        if isinstance(factions, list) or isinstance(factions, dict):
            factions = json.dumps(factions, ensure_ascii=False)
        is_dirty = vol.get("is_dirty", 0)
        cursor.execute(
            "INSERT INTO volumes (novel_id, volume_index, title, summary, factions, is_dirty) VALUES (?, ?, ?, ?, ?, ?)",
            (novel_id, volume_index, title, summary, factions, is_dirty)
        )
    conn.commit()
    conn.close()

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
        res.append(d)
    return res

def update_volume_dirty(novel_id, volume_index, is_dirty):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE volumes SET is_dirty = ? WHERE novel_id = ? AND volume_index = ?", (is_dirty, novel_id, volume_index))
    conn.commit()
    conn.close()

def update_volume_outline(novel_id, volume_index, node_chapters):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Update volumes table's chapters_outline column
    chapters_json = json.dumps(node_chapters, ensure_ascii=False)
    cursor.execute(
        "UPDATE volumes SET chapters_outline = ?, is_dirty = 0 WHERE novel_id = ? AND volume_index = ?",
        (chapters_json, novel_id, volume_index)
    )
    conn.commit()
    conn.close()
    
    # 2. Stitch these chapters back into the master plot_chapters outline
    plot = get_latest_plot_chapters(novel_id)
    all_ch = plot["parsed_data"].get("chapters", []) if plot else []
    
    filtered_ch = []
    for c in all_ch:
        ch_idx = c.get("chapter_index")
        if ch_idx is not None:
            c_vol = (int(ch_idx) - 1) // 50 + 1
            if c_vol != int(volume_index):
                filtered_ch.append(c)
        else:
            filtered_ch.append(c)
            
    # Append the new aligned chapters
    for nc in node_chapters:
        filtered_ch.append(nc)
        
    # Sort them by chapter_index
    filtered_ch.sort(key=lambda x: int(x.get("chapter_index", 0)) if x.get("chapter_index") is not None else 99999)
    
    # Save back to plot_chapters
    save_plot_chapters(novel_id, {"chapters": filtered_ch})

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
        "category": category,
        "details": details,
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
    
    # 3. Mark downstream volumes as dirty (approx 50 chapters per volume)
    source_volume = (source_chapter_index - 1) // 50 + 1
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

def save_worldbuilding(novel_id, content):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM worldbuilding WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO worldbuilding (novel_id, content, version) VALUES (?, ?, ?)",
        (novel_id, content, next_version)
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
            data["parsed_data"] = json.loads(data["json_data"])
        except:
            data["parsed_data"] = {}
        return data
    return None

def save_characters(novel_id, json_data):
    if isinstance(json_data, dict) or isinstance(json_data, list):
        json_str = json.dumps(json_data, ensure_ascii=False)
    else:
        json_str = json_data
        
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
            parsed = json.loads(data["outline_json"])
            if isinstance(parsed, list):
                data["parsed_data"] = {"chapters": parsed}
            else:
                data["parsed_data"] = parsed
        except Exception as e:
            print(f"[ERROR] Failed to parse plot_chapters JSON: {e}")
            data["parsed_data"] = {}
        return data
    return None

def save_plot_chapters(novel_id, outline_json):
    if isinstance(outline_json, dict) or isinstance(outline_json, list):
        json_str = json.dumps(outline_json, ensure_ascii=False)
    else:
        json_str = outline_json
        
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM plot_chapters WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, ?, 0)",
        (novel_id, json_str, next_version)
    )
    conn.commit()
    conn.close()
    return next_version

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
        (novel_id, chapter_index, content, synopsis, thinking, next_version)
    )
    conn.commit()
    conn.close()
    return next_version

# --- CHAT MEMORY ---
def get_chat_memory(novel_id, limit=20):
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT role, content, timestamp FROM chat_memory WHERE novel_id = ? ORDER BY id DESC LIMIT ?",
        (novel_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def save_chat_message(novel_id, role, content):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_memory (novel_id, role, content) VALUES (?, ?, ?)",
        (novel_id, role, content)
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
        "three_act_structure": [
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
    
    content_stripped = content.strip()
    if content_stripped.startswith("{") and content_stripped.endswith("}"):
        try:
            parsed = json.loads(content_stripped)
            
            ta = parsed.get("three_act_structure", [])
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
                normalized_ta = default_structure["three_act_structure"]

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

            return {
                "theme": parsed.get("theme", ""),
                "main_conflict": parsed.get("main_conflict", ""),
                "worldview": parsed.get("worldview", ""),
                "macro_outline": parsed.get("macro_outline", ""),
                "three_act_structure": normalized_ta,
                "progressive_character_plan": normalized_cp,
                "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []) if isinstance(parsed.get("foreshadowing_seeds"), list) else [],
                "key_turning_points": parsed.get("key_turning_points", []) if isinstance(parsed.get("key_turning_points"), list) else []
            }
        except Exception as e:
            print(f"[WARN] parse_worldview_to_json JSON load failed: {e}. Falling back to text parser.")
            
    result = {
        "theme": "",
        "main_conflict": "",
        "worldview": "",
        "macro_outline": "",
        "three_act_structure": [
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
        "【三幕式結構】",
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
        
    if "【三幕式結構】" in sections:
        three_act_text = sections["【三幕式結構】"]
        for line in three_act_text.split("\n"):
            line = line.strip()
            if "第一幕" in line or "Setup" in line:
                result["three_act_structure"][0]["content"] = line.split("：", 1)[-1] if "：" in line else (line.split(":", 1)[-1] if ":" in line else line)
            elif "第二幕" in line or "Confrontation" in line:
                result["three_act_structure"][1]["content"] = line.split("：", 1)[-1] if "：" in line else (line.split(":", 1)[-1] if ":" in line else line)
            elif "第三幕" in line or "Resolution" in line:
                result["three_act_structure"][2]["content"] = line.split("：", 1)[-1] if "：" in line else (line.split(":", 1)[-1] if ":" in line else line)

    if "【角色漸進規劃策略】" in sections:
        prog_text = sections["【角色漸進規劃策略】"]
        for line in prog_text.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("•") or line.startswith("*"):
                line = line[1:].strip()
            if ":" in line or "：" in line:
                sep = "：" if "：" in line else ":"
                parts = line.split(sep, 1)
                k = parts[0].strip()
                v = parts[1].strip()
                if "wave_1" in k or "wave1" in k or "開篇" in k or "第一波" in k:
                    result["progressive_character_plan"][0]["content"] = v
                elif "wave_2" in k or "wave2" in k or "第二波" in k or "發展" in k:
                    result["progressive_character_plan"][1]["content"] = v
                elif "wave_3" in k or "wave3" in k or "第三波" in k or "高潮" in k:
                    result["progressive_character_plan"][2]["content"] = v
            else:
                if line:
                    if not result["progressive_character_plan"][0]["content"]:
                        result["progressive_character_plan"][0]["content"] = line
                    elif not result["progressive_character_plan"][1]["content"]:
                        result["progressive_character_plan"][1]["content"] = line
                    elif not result["progressive_character_plan"][2]["content"]:
                        result["progressive_character_plan"][2]["content"] = line
                        
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

def insert_plot_chapter(novel_id, insert_after_index, new_chapter):
    plot = get_latest_plot_chapters(novel_id)
    if not plot:
        return None
    
    plot_data = plot["parsed_data"]
    if "chapters" not in plot_data:
        plot_data["chapters"] = []
    
    chapters = plot_data["chapters"]
    
    if insert_after_index < 0 or insert_after_index >= len(chapters):
        new_chapter["chapter_index"] = len(chapters) + 1
        chapters.append(new_chapter)
    else:
        insert_pos = insert_after_index + 1
        new_chapter["chapter_index"] = insert_pos + 1
        chapters.insert(insert_pos, new_chapter)
        for i in range(insert_pos + 1, len(chapters)):
            chapters[i]["chapter_index"] = i + 1
    
    return save_plot_chapters(plot_data)

def update_character_field(novel_id, char_index, field_name, new_value):
    char_data = get_latest_characters(novel_id)
    if not char_data or "parsed_data" not in char_data:
        return None
    
    parsed = char_data["parsed_data"]
    if "characters" not in parsed or char_index >= len(parsed["characters"]):
        return None
    
    parsed["characters"][char_index][field_name] = new_value
    
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
