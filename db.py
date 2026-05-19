import sqlite3
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novel_factory.db")

# --- Agent Default Configurations from .env ---
# 根據 .env 設定各 Agent 的預設模型與參數
# 前端 Agent 命名: global, architect, character, plot, writer, editor, copilot
# .env 命名: MODEL_GLOBAL, MODEL_ARCHITECT, MODEL_STORY(MODEL_CHARACTER備援), MODEL_WRITER, MODEL_EDITOR, MODEL_CRITIC(MODEL_PLOT備援), MODEL_COPILOT
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
        "temperature": 0.30,  # 架構性輸出需要精準
        "top_p": 0.95,
        "max_tokens": 16384,  # 增加到 16K
        "enable_thinking": 1
    },
    "character": {
        # .env 中是 MODEL_STORY，作為 MODEL_CHARACTER 的備援
        "model": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY", "openai/gpt-oss-120b"),
        "temperature": 0.40,  # 角色設計需要創意但結構化
        "top_p": 0.95,
        "max_tokens": 16384,  # 增加到 16K
        "enable_thinking": 1
    },
    "plot": {
        # .env 中是 MODEL_CRITIC，作為 MODEL_PLOT 的備援
        "model": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC", "qwen/qwen3.5-122b-a10b"),
        "temperature": 0.35,  # 大綱規劃需要邏輯嚴謹
        "top_p": 0.95,
        "max_tokens": 16384,  # 增加到 16K
        "enable_thinking": 1
    },
    "writer": {
        "model": os.getenv("MODEL_WRITER", "nvidia/nemotron-3-super-120b-a12b"),
        "temperature": 0.65,  # 創意寫作需要高隨機性
        "top_p": 0.95,
        "max_tokens": 16384,  # 正文寫作需要更多 tokens
        "enable_thinking": 1
    },
    "editor": {
        "model": os.getenv("MODEL_EDITOR", "mistralai/mistral-small-4-119b-2603"),
        "temperature": 0.25,  # 精準的文字微調
        "top_p": 0.90,
        "max_tokens": 16384,  # 增加到 16K
        "enable_thinking": 0
    },
    "copilot": {
        "model": os.getenv("MODEL_COPILOT", "stepfun-ai/step-3.5-flash"),
        "temperature": 0.55,  # 創意建議與互動對話
        "top_p": 0.95,
        "max_tokens": 16384,  # 增加到 16K
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
    
    # 5. Chapters table (versioned)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT,
        chapter_index INTEGER,
        content TEXT,
        version INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    )
    """)
    
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
    
    # Pre-populate default agent configurations from AGENT_DEFAULTS
    default_agents = ["global", "architect", "character", "plot", "writer", "editor", "copilot"]
    for agent in default_agents:
        cursor.execute("SELECT 1 FROM agent_configs WHERE agent_name = ?", (agent,))
        if not cursor.fetchone():
            defaults = AGENT_DEFAULTS.get(agent, AGENT_DEFAULTS["global"])
            cursor.execute("""
            INSERT INTO agent_configs (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent,
                "", # Let the user enter their API key in UI
                "https://integrate.api.nvidia.com/v1",
                defaults["model"],
                defaults["temperature"],
                defaults["top_p"],
                defaults["max_tokens"],
                defaults["enable_thinking"]
            ))
            
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
    
    # Get current max version
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
            data["parsed_data"] = json.loads(data["outline_json"])
        except:
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
        "INSERT INTO plot_chapters (novel_id, outline_json, version) VALUES (?, ?, ?)",
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
    # Returns the latest version of all chapters for this novel
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # We select only the latest version for each chapter_index
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

def save_chapter(novel_id, chapter_index, content):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM chapters WHERE novel_id = ? AND chapter_index = ?",
        (novel_id, chapter_index)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
        (novel_id, chapter_index, content, next_version)
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
    # Reverse to return chronological order
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
def append_foreshadowing(novel_id, new_seed):
    """
    增量添加伏筆種子到世界觀。
    不重新生成全部，只在現有內容末尾追加新的伏筆。
    """
    wb = get_latest_worldbuilding(novel_id)
    if not wb:
        return None
    
    current_content = wb["content"]
    # 找到伏筆種子的位置並追加
    if "伏筆種子" in current_content:
        # 在現有伏筆種子後面追加
        parts = current_content.split("【伏筆種子】")
        if len(parts) > 1:
            # 替換最後部分，添加新伏筆
            new_part = parts[1]
            if new_part.strip():
                # 在最後一個條目後面追加
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
    """
    在指定位置後面插入新的大綱章節。
    insert_after_index: 插入到此索引之後（0 表示插入到最前面）
    返回新的 version
    """
    plot = get_latest_plot_chapters(novel_id)
    if not plot:
        return None
    
    plot_data = plot["parsed_data"]
    if "chapters" not in plot_data:
        plot_data["chapters"] = []
    
    chapters = plot_data["chapters"]
    
    # 確保 chapter_index 正確
    if insert_after_index < 0 or insert_after_index >= len(chapters):
        # 插入到最後
        new_chapter["chapter_index"] = len(chapters) + 1
        chapters.append(new_chapter)
    else:
        # 插入到指定位置之後
        insert_pos = insert_after_index + 1
        new_chapter["chapter_index"] = insert_pos + 1
        chapters.insert(insert_pos, new_chapter)
        # 重新計算後面所有章節的 chapter_index
        for i in range(insert_pos + 1, len(chapters)):
            chapters[i]["chapter_index"] = i + 1
    
    return save_plot_chapters(novel_id, plot_data)

def update_character_field(novel_id, char_index, field_name, new_value):
    """
    更新單一角色的特定欄位（細粒度修改）。
    """
    char_data = get_latest_characters(novel_id)
    if not char_data or "parsed_data" not in char_data:
        return None
    
    parsed = char_data["parsed_data"]
    if "characters" not in parsed or char_index >= len(parsed["characters"]):
        return None
    
    # 更新指定欄位
    parsed["characters"][char_index][field_name] = new_value
    
    return save_characters(novel_id, parsed)

def update_character_single_field(novel_id, char_index, field_name, new_value):
    """
    增量更新角色單一欄位（不重新生成全部）。
    """
    result = update_character_field(novel_id, char_index, field_name, new_value)
    if result:
        return {"status": "success", "version": result}
    return {"status": "error", "message": "Failed to update character field"}
