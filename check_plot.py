import sqlite3
import json

DB_PATH = 'novel_factory.db'
NOVEL_ID = '8f88c76c-2601-4ae7-a1b8-be00ea13f1c1'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 查詢 plot_chapters 表格
rows = cursor.execute("""
    SELECT id, novel_id, outline_json, version, created_at, is_dirty 
    FROM plot_chapters 
    WHERE novel_id = ? 
    ORDER BY version DESC 
    LIMIT 5
""", (NOVEL_ID,)).fetchall()

print(f"找到 {len(rows)} 筆 plot 記錄")
print("=" * 80)

for row in rows:
    print(f"ID: {row[0]}")
    print(f"版本: {row[3]}")
    print(f"建立時間: {row[4]}")
    print(f"is_dirty: {row[5]}")
    
    # 解析 JSON 內容
    try:
        outline = json.loads(row[2])
        chapters = outline.get("chapters", [])
        print(f"章節數量: {len(chapters)}")
        if chapters:
            print(f"第一筆章節: {chapters[0].get('title', '無標題')} (索引: {chapters[0].get('chapter_index', '?')})")
            print(f"最後一筆章節: {chapters[-1].get('title', '無標題')} (索引: {chapters[-1].get('chapter_index', '?')})")
    except Exception as e:
        print(f"JSON 解析錯誤: {e}")
        print(f"原始內容前 200 字元: {row[2][:200]}...")
    
    print("-" * 80)

conn.close()