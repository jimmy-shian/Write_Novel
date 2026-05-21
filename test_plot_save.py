#!/usr/bin/env python3
"""測試 plot_chapters 儲存功能"""

import sqlite3
import json
from db import save_plot_chapters, create_novel

# 建立測試小說
test_novel_id = 'test-novel-123'
create_novel(test_novel_id, '測試小說', '仙俠', '史詩宏大')

# 建立測試數據
test_data1 = {'chapters': [{'chapter_index': 1, 'title': '測試章節1'}, {'chapter_index': 2, 'title': '測試章節2'}]}
test_data2 = [{'chapter_index': 1, 'title': '測試章節1'}, {'chapter_index': 2, 'title': '測試章節2'}]
test_data3 = json.dumps({'chapters': [{'chapter_index': 1, 'title': '測試章節1'}]})

conn = sqlite3.connect('novel_factory.db')
cursor = conn.cursor()
cursor.execute('DELETE FROM plot_chapters WHERE novel_id = ?', (test_novel_id,))
conn.close()

print('Testing save_plot_chapters with different formats:')

# 測試 1: dict with chapters key
v1 = save_plot_chapters(test_novel_id, test_data1)
print(f'Test 1 (dict with chapters): version={v1}')

# 測試 2: list (should be wrapped)
v2 = save_plot_chapters(test_novel_id, test_data2)
print(f'Test 2 (list): version={v2}')

# 測試 3: JSON string
v3 = save_plot_chapters(test_novel_id, test_data3)
print(f'Test 3 (JSON string): version={v3}')

# 查詢結果
conn = sqlite3.connect('novel_factory.db')
cursor = conn.cursor()
cursor.execute('SELECT outline_json FROM plot_chapters WHERE novel_id = ? ORDER BY version', (test_novel_id,))
rows = cursor.fetchall()
print(f'\nSaved {len(rows)} records:')
for i, (outline,) in enumerate(rows, 1):
    data = json.loads(outline)
    chapters_count = len(data.get('chapters', [])) if isinstance(data, dict) else 'N/A (not dict)'
    print(f'  Record {i}: type={type(data).__name__}, chapters count: {chapters_count}')

conn.close()
print('\nTest completed successfully!')