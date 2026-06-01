# -*- coding: utf-8 -*-
import os
import sys
import json

# Add parent directory to path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def clear_data():
    novel_id = 'd17af413-03be-4ffe-93a9-3603f8ff9839'
    print(f"Targeting Novel: {novel_id}")
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # 1. Clear characters (keep only first 10)
    char_data = db.get_latest_characters(novel_id)
    if char_data and char_data.get("json_data"):
        try:
            parsed_chars = json.loads(char_data["json_data"])
            chars_list = parsed_chars.get("characters", [])
            print(f"Current character count: {len(chars_list)}")
            
            # Keep only the first 10 characters
            trimmed_list = chars_list[:10]
            print(f"Trimming to count: {len(trimmed_list)}")
            
            trimmed_json = {"characters": trimmed_list}
            db.save_characters(novel_id, trimmed_json)
            print("Successfully trimmed characters to first 10!")
        except Exception as e:
            print(f"Failed to trim characters: {e}")
    else:
        print("No characters found to trim.")
        
    # 2. Revert detailed outlines in volumes to clean skeletons
    cursor.execute("SELECT id, volume_index, chapters_outline FROM volumes WHERE novel_id = ?", (novel_id,))
    vol_rows = cursor.fetchall()
    print(f"Found {len(vol_rows)} volumes.")
    
    for row in vol_rows:
        vol_id = row['id']
        vol_idx = row['volume_index']
        outline_str = row['chapters_outline']
        if outline_str:
            try:
                chaps = json.loads(outline_str)
                if isinstance(chaps, list):
                    cleaned_chaps = []
                    for ch in chaps:
                        # Extract only skeleton fields
                        skel_ch = {
                            "chapter_index": int(ch.get("chapter_index", 0)),
                            "chapter_title": ch.get("chapter_title") or ch.get("title") or "待設定標題",
                            "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or "待設定摘要",
                            "volume_index": vol_idx,
                            "allocated_tasks": ch.get("allocated_tasks") or {
                                "foreshadowing_plants": [],
                                "foreshadowing_payoffs": [],
                                "turning_points": []
                            }
                        }
                        cleaned_chaps.append(skel_ch)
                    
                    cleaned_json = json.dumps(cleaned_chaps, ensure_ascii=False, indent=2)
                    cursor.execute("UPDATE volumes SET chapters_outline = ? WHERE id = ?", (cleaned_json, vol_id))
                    print(f"Volume {vol_idx} detail outlines cleared back to skeleton.")
            except Exception as e:
                print(f"Failed to clean Volume {vol_idx}: {e}")
                
    # 3. Clean or delete plot_chapters master records
    cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
    print("Deleted all master plot_chapters versions for this novel.")
    
    # Save a clean empty master plot outline to avoid breaking the front-end
    cursor.execute(
        "INSERT INTO plot_chapters (novel_id, outline_json, version, is_dirty) VALUES (?, ?, 1, 1)",
        (novel_id, json.dumps({"chapters": []}, ensure_ascii=False))
    )
    print("Inserted fresh empty master plot outline.")
    
    # Commit database changes
    conn.commit()
    conn.close()
    print("Database changes committed successfully!")

if __name__ == "__main__":
    clear_data()
