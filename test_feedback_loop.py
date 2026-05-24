# -*- coding: utf-8 -*-
import os
import json
import sqlite3
from db import (
    db_init,
    create_novel,
    get_novel,
    save_volumes,
    get_volumes,
    save_plot_chapters,
    get_latest_plot_chapters,
    save_chapter,
    get_all_chapters_latest,
    add_worldview_patch,
    get_worldview_patches,
    mark_downstream_dirty,
    update_volume_outline,
    get_db_connection
)

def run_test():
    print("=== [FEEDBACK LOOP & LAZY ALIGNMENT TEST STARTED] ===")
    
    # 1. Initialize Database
    db_init()
    
    novel_id = "test-loop-novel"
    
    # Clean up any existing test data to start fresh
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()
    
    # 2. Create Novel
    create_novel(novel_id, "反饋環路測試史詩", "科幻", "史詩殘酷")
    print("[OK] Novel created successfully.")
    
    # 3. Save initial volumes
    volumes_list = [
        {"volume_index": 1, "title": "開端：磁帶之謎", "summary": "林浩發現了古神電路磁帶。", "factions": "流浪者同盟", "is_dirty": 0},
        {"volume_index": 2, "title": "中局：多世界奇異點", "summary": "多陣營在 Sector 7 激戰。", "factions": "黑星財閥, 機械教廷", "is_dirty": 0}
    ]
    save_volumes(novel_id, volumes_list)
    print("[OK] Volumes saved.")
    
    # 4. Save initial plot chapters (e.g. Chapter 1 in Volume 1, Chapter 51 in Volume 2)
    initial_outline = [
        {"chapter_index": 1, "title": "磁帶開啟", "summary": "林浩買到了古神磁帶。", "time_setting": "第4天", "scene": "Scrap Iron Alley"},
        {"chapter_index": 51, "title": " Sector 7 會戰", "summary": "黑星財閥突然發動總攻。", "time_setting": "第10天", "scene": "Sector 7"}
    ]
    save_plot_chapters(novel_id, {"chapters": initial_outline})
    print("[OK] Plot chapters saved.")
    
    # 5. Simulate a new worldview patch derived during Chapter 1 writing
    print("\n[Simulating chapter writing worldview tag interception...]")
    new_law_category = "Physics"
    new_law_details = "Gravity is reversed in Sector 7 when electromagnetic activity peaks."
    source_chapter = 1
    
    # Add patch to DB
    add_worldview_patch(novel_id, new_law_category, new_law_details, source_chapter)
    # Mark downstream dirty (since source is Chapter 1, downstream Volume 2 (ch 51) and ch > 1 are marked dirty)
    mark_downstream_dirty(novel_id, source_chapter)
    print("[OK] Worldview patch added & downstream marked dirty.")
    
    # 6. Verify Database States
    patches = get_worldview_patches(novel_id)
    assert len(patches) > 0, "Error: Worldview patches not saved."
    print(f"[OK] Worldview Patches Verified: {json.dumps(patches, ensure_ascii=False)}")
    
    volumes = get_volumes(novel_id)
    vol2 = next(v for v in volumes if v["volume_index"] == 2)
    vol1 = next(v for v in volumes if v["volume_index"] == 1)
    
    assert vol2["is_dirty"] == 1, "Error: Volume 2 should be marked dirty."
    assert vol1["is_dirty"] == 0, "Error: Volume 1 should NOT be marked dirty."
    print("[OK] Volume dirty states verified (Volume 2 is dirty, Volume 1 is clean).")
    
    # 7. Verify dynamic JIT stitching and alignment save helper
    aligned_chapters = [
        {"chapter_index": 51, "title": "Sector 7 重力顛倒會戰", "summary": "重力突然反轉，黑星財閥戰車升空懸浮，戰局劇變。", "time_setting": "第10天", "scene": "Sector 7"}
    ]
    update_volume_outline(novel_id, 2, aligned_chapters)
    print("[OK] JIT Volume alignment output stitched to DB.")
    
    # Load and verify plot outline again
    plot = get_latest_plot_chapters(novel_id)
    chapters = plot["parsed_data"].get("chapters", [])
    
    ch51 = next(c for c in chapters if c["chapter_index"] == 51)
    assert "重力突然反轉" in ch51["summary"], "Error: Chapter 51 summary was not updated with aligned outline."
    print(f"[OK] Aligned outline verified: {json.dumps(ch51, ensure_ascii=False)}")
    
    # Check if Volume 2 is dirty again (should be cleared to 0)
    volumes_after = get_volumes(novel_id)
    vol2_after = next(v for v in volumes_after if v["volume_index"] == 2)
    assert vol2_after["is_dirty"] == 0, "Error: Volume 2 should be marked clean after alignment."
    print("[OK] Volume 2 dirty state cleared successfully.")
    
    print("\n=== [ALL TESTS PASSED SUCCESSFULLY!] ===")

if __name__ == "__main__":
    run_test()
