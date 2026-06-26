import sqlite3
import argparse
import sys
import os

TABLES_TO_MERGE = [
    "novels",
    "worldbuilding",
    "characters",
    "volumes",
    "plot_chapters",
    "chapters",
    "chat_memory",
    "agent_configs"
]

def merge_databases(main_db_path, source_dbs):
    if not os.path.exists(main_db_path):
        print(f"Error: 主資料庫不存在 ({main_db_path})")
        sys.exit(1)

    # 確保主資料庫啟用 WAL 模式，支援高併發存取
    conn = sqlite3.connect(main_db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(main_db_path)
    cursor = conn.cursor()

    for src in source_dbs:
        if not os.path.exists(src):
            print(f"Warning: 來源資料庫不存在，已跳過 ({src})")
            continue
            
        print(f"正在合併資料庫: {src} -> {main_db_path}")
        try:
            # 附加來源資料庫
            cursor.execute("ATTACH DATABASE ? AS src_db", (src,))
            
            for table in TABLES_TO_MERGE:
                print(f"  - 複製資料表: {table}")
                # 檢查來源是否擁有此 Table
                cursor.execute(f"SELECT count(*) FROM src_db.sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone()[0] == 0:
                    continue
                
                # 使用 INSERT OR IGNORE 來避免 Primary Key / UUID 衝突
                try:
                    cursor.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM src_db.{table}")
                except sqlite3.OperationalError as e:
                    print(f"    [錯誤] 無法複製 {table}: {e}")
            
            cursor.execute("DETACH DATABASE src_db")
            conn.commit()
            print(f"✅ 成功合併: {src}")
            
        except Exception as e:
            print(f"❌ 合併 {src} 發生錯誤: {e}")
            conn.rollback()
            try:
                cursor.execute("DETACH DATABASE src_db")
            except:
                pass

    conn.close()
    print("\n🎉 所有資料庫合併完畢！")
    print("現在多本小說已經統一管理於單一主資料庫中。由於系統原生使用 UUID 作為 novel_id 區隔，並且已啟動 WAL 模式，不同小說同時操作不會互相干擾。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="合併多個 AI Novel Factory 資料庫")
    parser.add_argument("--main", "-m", default="novel_factory.db", help="主資料庫路徑 (預設: novel_factory.db)")
    parser.add_argument("sources", nargs="+", help="要被合併的來源資料庫清單 (例如: db1.db db2.db)")
    
    args = parser.parse_args()
    
    merge_databases(args.main, args.sources)
