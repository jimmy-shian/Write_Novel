import json
from .connection import get_db_connection

def create_novel(novel_id: str, title: str, background: str, target_word_count: int = 300000):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO novels (id, title, background, target_word_count) VALUES (?, ?, ?, ?)",
        (novel_id, title, background, target_word_count)
    )
    conn.commit()
    conn.close()

def get_novel(novel_id: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_worldview(novel_id: str, content: str):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO worldview (novel_id, content, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (novel_id, content)
    )
    conn.commit()
    conn.close()

def get_worldview(novel_id: str):
    conn = get_db_connection()
    row = conn.execute("SELECT content FROM worldview WHERE novel_id = ?", (novel_id,)).fetchone()
    conn.close()
    return row["content"] if row else ""

def add_character(char_id: str, novel_id: str, name: str, role: str, description: str, personality: str):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO characters (id, novel_id, name, role, description, personality) VALUES (?, ?, ?, ?, ?, ?)",
        (char_id, novel_id, name, role, description, personality)
    )
    conn.commit()
    conn.close()

def get_characters(novel_id: str):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM characters WHERE novel_id = ?", (novel_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_volumes(novel_id: str, volumes: list):
    """volumes: list of dicts with keys: id, vol_index, title, summary"""
    conn = get_db_connection()
    for vol in volumes:
        conn.execute(
            "INSERT OR REPLACE INTO volumes (id, novel_id, vol_index, title, summary, status) VALUES (?, ?, ?, ?, ?, ?)",
            (vol["id"], novel_id, vol["vol_index"], vol["title"], vol["summary"], vol.get("status", "pending"))
        )
    conn.commit()
    conn.close()

def get_volumes(novel_id: str):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY vol_index ASC", (novel_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_chapters_skeleton(novel_id: str, vol_index: int, chapters: list):
    """chapters: list of dicts with keys: id, ch_index, title, summary"""
    conn = get_db_connection()
    for ch in chapters:
        conn.execute(
            "INSERT OR REPLACE INTO chapters (id, novel_id, vol_index, ch_index, title, summary, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ch["id"], novel_id, vol_index, ch["ch_index"], ch["title"], ch.get("summary", ""), ch.get("status", "pending"))
        )
    conn.commit()
    conn.close()

def get_chapters(novel_id: str, vol_index: int = None):
    conn = get_db_connection()
    if vol_index is not None:
        rows = conn.execute("SELECT * FROM chapters WHERE novel_id = ? AND vol_index = ? ORDER BY ch_index ASC", (novel_id, vol_index)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM chapters WHERE novel_id = ? ORDER BY vol_index ASC, ch_index ASC", (novel_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_chapter_plot(novel_id: str, vol_index: int, ch_index: int, summary: str):
    conn = get_db_connection()
    conn.execute(
        "UPDATE chapters SET summary = ?, status = 'plot_generated', last_updated = CURRENT_TIMESTAMP WHERE novel_id = ? AND vol_index = ? AND ch_index = ?",
        (summary, novel_id, vol_index, ch_index)
    )
    conn.commit()
    conn.close()

def update_chapter_content(novel_id: str, vol_index: int, ch_index: int, content: str):
    conn = get_db_connection()
    conn.execute(
        "UPDATE chapters SET content = ?, status = 'completed', last_updated = CURRENT_TIMESTAMP WHERE novel_id = ? AND vol_index = ? AND ch_index = ?",
        (content, novel_id, vol_index, ch_index)
    )
    conn.commit()
    conn.close()

def save_worldview_patch(patch_id: str, novel_id: str, vol_index: int, patch_type: str, details: str):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO worldview_patches (id, novel_id, vol_index, patch_type, details) VALUES (?, ?, ?, ?, ?)",
        (patch_id, novel_id, vol_index, patch_type, details)
    )
    conn.commit()
    conn.close()

def get_worldview_patches(novel_id: str, vol_index: int = None):
    conn = get_db_connection()
    if vol_index is not None:
        rows = conn.execute("SELECT * FROM worldview_patches WHERE novel_id = ? AND vol_index = ? ORDER BY created_at ASC", (novel_id, vol_index)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM worldview_patches WHERE novel_id = ? ORDER BY vol_index ASC, created_at ASC", (novel_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_chat_message(novel_id: str, role: str, content: str):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO chat_memory (novel_id, role, content) VALUES (?, ?, ?)",
        (novel_id, role, content)
    )
    conn.commit()
    conn.close()

def get_chat_history(novel_id: str, limit: int = 20):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT role, content FROM chat_memory WHERE novel_id = ? ORDER BY id ASC LIMIT ?",
        (novel_id, limit)
    )
    conn.close()
    return [dict(r) for r in rows]

# ==================== Formulaic Equations ====================

def get_vol_range(vols: list, vol_index: int) -> tuple:
    """
    Equation 1: Chapter Index Range Equation
    Given volumes list, mathematically JIT derive target volume's chapter boundary index offsets.
    If each volume has standard K chapters, we can infer starting/ending offsets.
    Wait, if chapter table already exists and holds entries, we can fetch min and max.
    Let's combine: if chapters exist in db, look them up. If not, use standard K=10 partition.
    """
    conn = get_db_connection()
    # Let's see if chapters are stored in database
    row = conn.execute(
        "SELECT MIN(ch_index) as start_ch, MAX(ch_index) as end_ch FROM chapters WHERE vol_index = ?",
        (vol_index,)
    ).fetchone()
    conn.close()
    
    if row and row["start_ch"] is not None:
        return row["start_ch"], row["end_ch"]
    
    # Mathematical approximation: assume 10 chapters per volume
    start_ch = vol_index * 10 + 1
    end_ch = (vol_index + 1) * 10
    return start_ch, end_ch

def infer_stage(novel_id: str) -> str:
    """
    Equation 2: Pipeline Stage Inference Equation
    Automatically inspects DB table counts to dynamically determine active pipeline stage.
    """
    novel = get_novel(novel_id)
    if not novel:
        return "init"
    
    wv = get_worldview(novel_id)
    if not wv:
        return "worldview"
    
    chars = get_characters(novel_id)
    if not chars:
        return "characters"
    
    vols = get_volumes(novel_id)
    if not vols:
        return "volumes"
    
    chaps = get_chapters(novel_id)
    if not chaps:
        return "skeleton"
    
    # If we have chapters, check if plot (summary) is generated
    pending_plot = [c for c in chaps if not c["summary"] or len(c["summary"].strip()) < 5]
    if pending_plot:
        return "plot"
    
    # If all plots are generated, check if chapter content is written
    pending_write = [c for c in chaps if not c["content"] or len(c["content"].strip()) < 100]
    if pending_write:
        return "writer"
    
    return "completed"

def get_bucket_seeds(seeds: list, vol_idx: int, total_vols: int) -> list:
    """
    Equation 3: Foreshadowing Seed Bucket Isolation Equation
    Isolates seeds deterministically using mathematical partition to guarantee zero cross-volume leaks.
    """
    if not seeds:
        return []
    n = len(seeds)
    if total_vols <= 0:
        return seeds
    
    size = max(1, n // total_vols)
    start = vol_idx * size
    # For the last volume, grab everything remaining
    end = n if vol_idx == total_vols - 1 else (vol_idx + 1) * size
    
    return seeds[start:end]

# ==================== Agent Configuration Helpers ====================

def get_agent_configs() -> dict:
    conn = get_db_connection()
    # Check if table exists first (safeguard)
    try:
        rows = conn.execute("SELECT * FROM agent_configs").fetchall()
    except Exception:
        conn.close()
        return {}
    conn.close()
    
    configs = {}
    for r in rows:
        configs[r["agent_name"]] = {
            "api_key": r["api_key"],
            "base_url": r["base_url"],
            "model": r["model"],
            "temperature": r["temperature"],
            "top_p": r["top_p"],
            "max_tokens": r["max_tokens"],
            "enable_thinking": r["enable_thinking"]
        }
    return configs

def update_agent_config(agent_name: str, api_key: str, base_url: str, model: str, temperature: float, top_p: float, max_tokens: int, enable_thinking: int):
    conn = get_db_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO agent_configs 
        (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking)
    )
    conn.commit()
    conn.close()
