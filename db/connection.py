import os
import sqlite3

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "novel_factory.db")

def get_db_connection():
    """Establish connection to SQLite database and set row factory and foreign keys."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initialize database tables from scratch."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table 1: Novels
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS novels (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        background TEXT NOT NULL,
        target_word_count INTEGER DEFAULT 300000,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Table 2: Worldview
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS worldview (
        novel_id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    );
    """)

    # Table 3: Volumes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS volumes (
        id TEXT PRIMARY KEY,
        novel_id TEXT NOT NULL,
        vol_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        status TEXT DEFAULT 'pending', -- 'pending', 'active', 'completed'
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
        UNIQUE(novel_id, vol_index)
    );
    """)

    # Table 4: Characters
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id TEXT PRIMARY KEY,
        novel_id TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL, -- 'protagonist', 'antagonist', 'supporting'
        description TEXT NOT NULL,
        personality TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    );
    """)

    # Table 5: Chapters
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id TEXT PRIMARY KEY,
        novel_id TEXT NOT NULL,
        vol_index INTEGER NOT NULL,
        ch_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        summary TEXT DEFAULT '',
        content TEXT DEFAULT '',
        status TEXT DEFAULT 'pending', -- 'pending', 'plot_generated', 'completed'
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
        UNIQUE(novel_id, vol_index, ch_index)
    );
    """)

    # Table 6: Chat Memory
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT NOT NULL,
        role TEXT NOT NULL, -- 'user', 'assistant'
        content TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    );
    """)

    # Table 7: Worldview Patches / Foreshadowing Seeds
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS worldview_patches (
        id TEXT PRIMARY KEY,
        novel_id TEXT NOT NULL,
        vol_index INTEGER NOT NULL,
        patch_type TEXT NOT NULL, -- 'foreshadowing', 'lore', 'character_arc'
        details TEXT NOT NULL, -- JSON or text summary
        status TEXT DEFAULT 'active', -- 'active', 'resolved'
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
    );
    """)

    # Table 8: Agent Configurations (Decoupled settings helper)
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
    );
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database successfully initialized!")
