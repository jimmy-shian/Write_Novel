# -*- coding: utf-8 -*-
"""
測試剛性診斷模組 (UTF-8 檔案輸出)
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from diagnostics import diagnose_worldview, diagnose_characters, diagnose_volumes_and_skeletons, diagnose_detailed_plot, diagnose_written_chapters

output_lines = []

# 測試世界觀診斷
output_lines.append("--- 測試世界觀 ---")
wb_empty = ""
output_lines.append(f"空世界觀: {diagnose_worldview(wb_empty)}")

wb_incomplete = '{"theme": "主題"}'
output_lines.append(f"不完整世界觀: {diagnose_worldview(wb_incomplete)}")

wb_complete = '{"theme": "主題", "main_conflict": "衝突", "worldview": "世界觀", "macro_outline": "大綱", "foreshadowing_seeds": ["伏筆1", "伏筆2"], "key_turning_points": ["轉折1"]}'
output_lines.append(f"完整世界觀: {diagnose_worldview(wb_complete)}")

# 測試角色診斷
output_lines.append("\n--- 測試角色 ---")
char_empty = ""
output_lines.append(f"空角色: {diagnose_characters(char_empty)}")

char_incomplete = '{"characters": [{"name": "主角", "personality": "性格"}]}'
output_lines.append(f"不完整角色: {diagnose_characters(char_incomplete)}")

char_complete = '{"characters": [{"name": "主角", "personality": "性格", "want": "想要", "need": "需要", "fatal_flaw": "缺陷"}]}'
output_lines.append(f"完整角色: {diagnose_characters(char_complete)}")

# 測試卷骨架診斷
output_lines.append("\n--- 測試卷骨架 ---")
vols_empty = []
output_lines.append(f"空卷: {diagnose_volumes_and_skeletons(vols_empty)}")

vols_incomplete = [{"volume_index": 1, "chapters_outline": []}]
output_lines.append(f"不完整卷骨架: {diagnose_volumes_and_skeletons(vols_incomplete)}")

vols_complete = [{"volume_index": 1, "chapters_outline": [{"chapter_index": 1, "chapter_title": "第一章"}]}]
output_lines.append(f"完整卷骨架: {diagnose_volumes_and_skeletons(vols_complete)}")

output_lines.append("\n--- 所有測試完成 ---")

with open("scratch/test_diagnostics_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))
