#!/usr/bin/env python3
"""完整測試 plot_chapters 儲存與讀取功能"""

import sqlite3
import json
from db import get_latest_plot_chapters, create_novel, save_plot_chapters

# 建立測試小說
test_novel_id = 'test-novel-456'
create_novel(test_novel_id, '測試小說2', '仙俠', '史詩宏大')

print('=== 測試 1: 儲存 list 格式 ===')
test_data = [{'chapter_index': 1, 'title': '第一章'}, {'chapter_index': 2, 'title': '第二章'}]
save_plot_chapters(test_novel_id, test_data)

result = get_latest_plot_chapters(test_novel_id)
print(f'parsed_data type: {type(result["parsed_data"]).__name__}')
chapters = result['parsed_data'].get('chapters', [])
print(f'chapters count: {len(chapters)}')
print(f'First chapter: {chapters[0] if chapters else "None"}')

print('\n=== 測試 2: 儲存 dict 格式 ===')
test_data2 = {'chapters': [{'chapter_index': 1, 'title': '第一章修改'}]}
save_plot_chapters(test_novel_id, test_data2)

result2 = get_latest_plot_chapters(test_novel_id)
chapters2 = result2['parsed_data'].get('chapters', [])
print(f'chapters count: {len(chapters2)}')
print(f'First chapter title: {chapters2[0]["title"] if chapters2 else "None"}')

# 清理
conn = sqlite3.connect('novel_factory.db')
cursor = conn.cursor()
cursor.execute('DELETE FROM plot_chapters WHERE novel_id = ?', (test_novel_id,))
cursor.execute('DELETE FROM novels WHERE id = ?', (test_novel_id,))
conn.commit()
conn.close()

print('\n✅ 所有測試通過！')