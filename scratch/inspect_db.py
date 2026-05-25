# -*- coding: utf-8 -*-
import sqlite3
import json
import os
import sys

# Force output to use utf-8
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'novel_factory.db'

if not os.path.exists(DB_PATH):
    print(f"找不到資料庫檔案 {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. 列出所有小說
novels = cursor.execute("SELECT id, title, genre, style, created_at FROM novels ORDER BY created_at DESC").fetchall()
print(f"資料庫中共有 {len(novels)} 本小說:")
for n in novels:
    print(f"ID: {n['id']} | 標題: {n['title']} | 題材: {n['genre']} | 建立時間: {n['created_at']}")
print("=" * 80)

# 2. 對於每本小說，查詢其是否有世界觀設定和伏筆種子
for n in novels:
    novel_id = n["id"]
    wb_row = cursor.execute(
        "SELECT content, version FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    
    if wb_row:
        content = wb_row["content"]
        try:
            wb_json = json.loads(content)
            seeds = wb_json.get("foreshadowing_seeds", [])
            tps = wb_json.get("key_turning_points", [])
            vols = wb_json.get("volumes", [])
            print(f"小說《{n['title']}》:")
            print(f"  世界觀版本: {wb_row['version']}")
            print(f"  伏筆種子數量: {len(seeds)}")
            print(f"  關鍵轉折點數量: {len(tps)}")
            print(f"  世界觀內 Volumes 數量: {len(vols)}")
            
            # 查詢 volumes 表格
            v_rows = cursor.execute("SELECT volume_index, title, chapters_outline FROM volumes WHERE novel_id = ?", (novel_id,)).fetchall()
            print(f"  Volumes 表格中卷數量: {len(v_rows)}")
            for vr in v_rows:
                outl = vr["chapters_outline"]
                if outl:
                    try:
                        outl_json = json.loads(outl)
                        # 檢查是否有任何章節有 allocated_tasks 且內有 seeds 或 tps
                        allocated_count = 0
                        for ch in outl_json:
                            alloc = ch.get("allocated_tasks", {})
                            if alloc.get("foreshadowing_plants") or alloc.get("foreshadowing_payoffs") or alloc.get("turning_points"):
                                allocated_count += 1
                        print(f"    卷 {vr['volume_index']} ({vr['title']}): 共 {len(outl_json)} 章, 其中 {allocated_count} 章被分配了伏筆/轉折")
                    except Exception as e:
                        print(f"    卷 {vr['volume_index']} outline 解析失敗: {e}")
                else:
                    print(f"    卷 {vr['volume_index']} ({vr['title']}): 無 chapters_outline")
        except Exception as e:
            print(f"小說《{n['title']}》世界觀 JSON 解析失敗: {e}")
    else:
        print(f"小說《{n['title']}》沒有世界觀設定")
    print("-" * 60)

conn.close()
