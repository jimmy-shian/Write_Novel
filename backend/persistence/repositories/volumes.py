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
            cursor.execute("DELETE FROM chapter_memory WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM arc_summaries WHERE novel_id = ?", (novel_id,))
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
    from backend.services.foreshadowing.chapter_math import get_clean_chapter_count
    return get_clean_chapter_count(vol)

def get_volume_chapter_range(volumes, target_volume_index):
    from backend.services.foreshadowing.chapter_math import get_volume_chapter_range as _get_volume_chapter_range
    return _get_volume_chapter_range(volumes, target_volume_index)

def get_chapter_volume_index(volumes, chapter_index):
    from backend.services.foreshadowing.chapter_math import get_chapter_volume_index as _get_chapter_volume_index
    return _get_chapter_volume_index(volumes, chapter_index)

def get_total_chapter_count(volumes):
    from backend.services.foreshadowing.chapter_math import get_total_chapter_count as _get_total_chapter_count
    return _get_total_chapter_count(volumes)

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
            stitched_chapters.sort(
                key=lambda x: int(x.get("chapter_index", 0))
                if x.get("chapter_index") is not None
                else 99999
            )
        except Exception:
            pass
        return {"chapters": stitched_chapters}

    plot = get_latest_plot_chapters(novel_id)
    return plot["parsed_data"] if plot else {"chapters": []}


def save_volume_skeletons(novel_id, volume_index, chapters_skeleton):
    """
    [新功能] 保存某卷的簡易章節骨架大綱到 volumes 表的 chapters_outline 欄位
    這是 Stage 2 (Volume Skeleton) 的產出儲存點，強制過濾超界章節。
    """
    volumes = get_volumes(novel_id)
    start_ch, end_ch = get_volume_chapter_range(volumes, volume_index)
    
    # 過濾與映射章節，避免不連續跳號或骨架寫入其他卷
    cleaned_skeleton = []
    
    # 建立映射以防相對/缺漏索引
    expected_count = (end_ch - start_ch + 1) if (start_ch is not None and end_ch is not None) else len(chapters_skeleton)
    
    for idx, ch in enumerate(chapters_skeleton):
        if not isinstance(ch, dict):
            continue
        c_idx = ch.get("chapter_index")
        
        if start_ch is not None and end_ch is not None:
            if c_idx is not None:
                try:
                    c_idx_int = int(c_idx)
                    # 💡 [相對索引映射]: 若為相對卷內索引 (如 1..10)，將其映射至絕對章節區間
                    if 1 <= c_idx_int <= expected_count and c_idx_int < start_ch:
                        c_idx_int = start_ch + c_idx_int - 1
                        ch["chapter_index"] = c_idx_int
                    
                    if start_ch <= c_idx_int <= end_ch:
                        cleaned_skeleton.append(ch)
                    else:
                        print(f"[WARN] save_volume_skeletons filtered out out-of-bounds chapter {c_idx_int} for Vol {volume_index} (expected [{start_ch}, {end_ch}])")
                except Exception as e:
                    print(f"[WARN] Failed to parse/map chapter index {c_idx} in save_volume_skeletons: {e}")
            else:
                # 💡 [補全缺漏索引]: 若無 chapter_index，自動依序賦予
                assigned_idx = start_ch + len(cleaned_skeleton)
                if assigned_idx <= end_ch:
                    ch["chapter_index"] = assigned_idx
                    cleaned_skeleton.append(ch)
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






# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *

from backend.services.diagnostics import detect_current_stage, generate_validation_report
