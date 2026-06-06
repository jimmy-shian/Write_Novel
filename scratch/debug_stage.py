# -*- coding: utf-8 -*-
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

novel_id = "test-novel-uuid-12345"

# Recreate test case
db.delete_novel(novel_id)
db.create_novel(novel_id, "剛性測試小說", "Fantasy", "Classic")

wv_content = json.dumps({
    "theme": "主線",
    "main_conflict": "對立",
    "worldview": "規則",
    "macro_outline": "故事大綱",
    "multi_act_structure": [],
    "progressive_character_plan": [],
    "foreshadowing_seeds": ["伏筆種子1"],
    "key_turning_points": ["轉折點1"]
}, ensure_ascii=False)
db.save_worldbuilding(novel_id, wv_content)

char_data = {
    "characters": [
        {
            "name": "主角A",
            "role": "主角",
            "personality": ["堅毅"],
            "want": "生存",
            "need": "救贖",
            "fatal_flaw": "衝動",
            "motivation": "復仇",
            "arc": "無",
            "relationships": []
        }
    ]
}
db.save_characters(novel_id, char_data)

volumes_list = [
    {"volume_index": 1, "title": "第一卷", "summary": "開篇卷", "chapter_count": 1}
]
db.save_volumes(novel_id, volumes_list)

skeleton_outline = [
    {"chapter_index": 1, "brief_title": "第1章", "brief_summary": "介紹"}
]
db.update_volume_outline(novel_id, 1, skeleton_outline)

# Debug stage detection step-by-step
vols = db.get_volumes(novel_id)
print("vols:", vols)

has_all_skeletons = True
for v in vols:
    skeleton_list = v.get("chapters_outline")
    print(f"vol {v['volume_index']} skeleton_list:", skeleton_list)
    if not skeleton_list:
        print("  Missing skeleton list!")
        has_all_skeletons = False
        break
    
    empty_titles = 0
    for c in skeleton_list:
        title = c.get("chapter_title") or c.get("brief_title") or c.get("title") or ""
        print(f"  chapter title: '{title}'")
        if not title or title.strip() == "" or title == "待設定標題":
            empty_titles += 1
    print(f"  empty_titles: {empty_titles}, total: {len(skeleton_list)}")
    if empty_titles > len(skeleton_list) * 0.5:
        print("  Too many empty titles!")
        has_all_skeletons = False
        break

print("has_all_skeletons:", has_all_skeletons)
stage = db.detect_current_stage(novel_id)
print("detected stage:", stage)
