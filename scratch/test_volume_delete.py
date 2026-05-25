# -*- coding: utf-8 -*-
import sys
import os
import json

# Ensure parent directory is in sys.path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def run_test():
    print("=" * 60)
    print("[TEST] Running Volume Deletion Bug Reproduction & Verification")
    print("=" * 60)
    
    # 1. Create a dummy novel
    novel_id = "test-novel-delete-vol-id"
    # Clean up first
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM worldbuilding WHERE novel_id = ?", (novel_id,))
    conn.commit()
    
    cursor.execute("INSERT INTO novels (id, title, genre, style) VALUES (?, ?, ?, ?)", (novel_id, "Test Volume Delete Novel", "Fantasy", "Web Novel"))
    conn.commit()
    
    # 2. Setup 3 volumes with chapters inside chapters_outline
    v1_chapters = [{"chapter_index": i, "title": f"Ch {i}", "summary": f"Summary {i}"} for i in range(1, 6)]
    v2_chapters = [{"chapter_index": i, "title": f"Ch {i}", "summary": f"Summary {i}"} for i in range(6, 11)]
    v3_chapters = [{"chapter_index": i, "title": f"Ch {i}", "summary": f"Summary {i}"} for i in range(11, 16)]
    
    volumes_list = [
        {
            "volume_index": 1,
            "title": "Volume 1",
            "summary": "V1 Summary",
            "factions": "[\"Faction A\"]",
            "is_dirty": 0,
            "chapter_count": 5,
            "chapters_outline": json.dumps(v1_chapters, ensure_ascii=False)
        },
        {
            "volume_index": 2,
            "title": "Volume 2",
            "summary": "V2 Summary",
            "factions": "[\"Faction B\"]",
            "is_dirty": 0,
            "chapter_count": 5,
            "chapters_outline": json.dumps(v2_chapters, ensure_ascii=False)
        },
        {
            "volume_index": 3,
            "title": "Volume 3",
            "summary": "V3 Summary",
            "factions": "[\"Faction C\"]",
            "is_dirty": 0,
            "chapter_count": 5,
            "chapters_outline": json.dumps(v3_chapters, ensure_ascii=False)
        }
    ]
    
    db.save_volumes(novel_id, volumes_list)
    # Put chapters_outline directly since save_volumes doesn't save it by default (it creates empty '[]' or ignores it depending on schema)
    # Let's verify and force update it:
    for v in volumes_list:
        cursor.execute(
            "UPDATE volumes SET chapters_outline = ?, chapter_count = ? WHERE novel_id = ? AND volume_index = ?",
            (v["chapters_outline"], v["chapter_count"], novel_id, v["volume_index"])
        )
    conn.commit()
    
    # Create worldview JSON with volumes
    wb_content = {
        "theme": "Test Theme",
        "volumes": [
            {"volume_index": 1, "title": "Volume 1"},
            {"volume_index": 2, "title": "Volume 2"},
            {"volume_index": 3, "title": "Volume 3"}
        ]
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_content, ensure_ascii=False))
    
    # Create plot chapters
    all_chaps = v1_chapters + v2_chapters + v3_chapters
    cursor.execute(
        "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, 1, 0)",
        (novel_id, json.dumps({"chapters": all_chaps}, ensure_ascii=False))
    )
    conn.commit()
    
    print("[INIT] Initial Volumes and chapters set up successfully.")
    print(f"Stitched plot chapters: {[c['chapter_index'] for c in db.get_stitched_plot(novel_id)['chapters']]}")
    
    # 3. Delete Volume 2
    print("[ACTION] Deleting Volume 2...")
    db.delete_volume(novel_id, 2)
    
    # 4. Check results
    vols = db.get_volumes(novel_id)
    print(f"[RESULT] Remaining Volumes count: {len(vols)}")
    for v in vols:
        print(f"  Vol {v['volume_index']}: {v['title']} (chapter_count={v['chapter_count']})")
        outline = v['chapters_outline']
        if outline:
            ch_list = json.loads(outline)
            print(f"    Chapters inside chapters_outline: {[c['chapter_index'] for c in ch_list]}")
        else:
            print("    No chapters outline")
            
    stitched = db.get_stitched_plot(novel_id)
    print(f"[RESULT] Stitched chapters: {[c['chapter_index'] for c in stitched['chapters']]}")
    
    # Worldbuilding check
    wb = db.get_latest_worldbuilding(novel_id)
    wb_json = json.loads(wb["content"])
    print(f"[RESULT] Worldbuilding Volumes: {wb_json.get('volumes')}")
    
    # Assertions
    assert len(vols) == 2, f"Expected 2 volumes, got {len(vols)}"
    assert vols[0]["volume_index"] == 1, "Expected first volume index to be 1"
    assert vols[1]["volume_index"] == 2, "Expected second volume index to be 2"
    
    # Clean up test
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM worldbuilding WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()
    
    print("\n[SUCCESS] Test executed without issues!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()


