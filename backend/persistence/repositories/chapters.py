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
    cursor.execute("DELETE FROM chapter_memory WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM arc_summaries WHERE novel_id = ?", (novel_id,))
    # Clear backup after restore
    cursor.execute("DELETE FROM chapters_backup WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()
    try:
        from backend.services import narrative_memory

        for chapter in get_all_chapters_latest(novel_id):
            outline = narrative_memory.get_chapter_outline(novel_id, chapter["chapter_index"])
            narrative_memory.store_chapter_memory(
                novel_id,
                chapter["chapter_index"],
                chapter.get("content", ""),
                source_version=chapter.get("version"),
                outline=outline,
            )
    except Exception as exc:
        print(f"[WARN] Failed to rebuild narrative memory after chapter backup restore: {exc}")

# --- PIPELINE LOCK FUNCTIONS (P0-3) ---

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
            from backend.models.parsers import extract_json_block
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
            from backend.models.parsers import extract_json_block
            parsed_dict = extract_json_block(json_str)
            if parsed_dict:
                json_str = json.dumps(parsed_dict, ensure_ascii=False)
        except:
            parsed_dict = {}
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if clear_chapters:
        cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM chapter_memory WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM arc_summaries WHERE novel_id = ?", (novel_id,))
    
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


def save_director_review_status(
    novel_id,
    stage_name,
    status,
    block_name=None,
    volume_index=None,
    chapter_index=None,
    reason="",
    decision_json=None,
):
    """Append a Director review status record without mutating content tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if decision_json is not None and not isinstance(decision_json, str):
        try:
            decision_json = json.dumps(decision_json, ensure_ascii=False, indent=2)
        except Exception:
            decision_json = str(decision_json)
    cursor.execute(
        """
        INSERT INTO director_reviews (
            novel_id, stage_name, status, block_name, volume_index, chapter_index, reason, decision_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (novel_id, stage_name, status, block_name, volume_index, chapter_index, reason, decision_json),
    )
    conn.commit()
    conn.close()


def get_latest_director_review_status(novel_id, stage_name=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if stage_name:
        row = cursor.execute(
            """
            SELECT * FROM director_reviews
            WHERE novel_id = ? AND stage_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (novel_id, stage_name),
        ).fetchone()
    else:
        row = cursor.execute(
            """
            SELECT * FROM director_reviews
            WHERE novel_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (novel_id,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def clear_chat_memory(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_memory WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()


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
        from backend.persistence.repositories.narrative_memory import shift_chapter_memories
        shift_chapter_memories(novel_id, insert_pos + 1, 1)
    
    return save_plot_chapters(novel_id, plot_data, skip_volume_sync=skip_volume_sync)



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
    cursor.execute(
        "DELETE FROM chapter_memory WHERE novel_id = ? AND chapter_index >= ? AND chapter_index <= ?",
        (novel_id, start_del, end_del)
    )
    
    # 2. 將 `chapters` 表後續已寫正文的索引向前平移 `del_count`
    cursor.execute(
        "UPDATE chapters SET chapter_index = chapter_index - ? WHERE novel_id = ? AND chapter_index > ?",
        (del_count, novel_id, end_del)
    )
    cursor.execute(
        "UPDATE chapter_memory SET chapter_index = -chapter_index WHERE novel_id = ? AND chapter_index > ?",
        (novel_id, end_del)
    )
    cursor.execute(
        "UPDATE chapter_memory SET chapter_index = (-chapter_index) - ? WHERE novel_id = ? AND chapter_index < 0",
        (del_count, novel_id)
    )
    cursor.execute("DELETE FROM arc_summaries WHERE novel_id = ?", (novel_id,))
    
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




# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *
