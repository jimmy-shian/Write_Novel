import sqlite3

def main():
    DB_PATH = "novel_factory.db"
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    tables_to_clear = [
        "characters",
        "volumes",
        "chapters",
        "chat_memory",
        "plot_chapters",
        "worldbuilding",
        "foreshadowing_blueprints",
    ]
    print("Start clearing generated content...")
    total = 0
    for table in tables_to_clear:
        try:
            cur = conn.execute(f"DELETE FROM {table}")
            deleted = cur.rowcount
            conn.commit()
            print(f" - {table}: deleted {deleted} rows")
            total += deleted
        except sqlite3.OperationalError as e:
            print(f" - {table}: skipped ({e})")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()
    print(f"\nDone! Total deleted: {total} rows.")
    print("novels table preserved.")

if __name__ == "__main__":
    main()