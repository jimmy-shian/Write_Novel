# -*- coding: utf-8 -*-
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def run_migration():
    conn = db.get_db_connection()
    cursor = conn.cursor()
    try:
        # Migrate all base URLs to local gateway
        cursor.execute("UPDATE agent_configs SET base_url = 'https://integrate.api.nvidia.com/v1'")
        # Migrate all models to patcher-main
        cursor.execute("UPDATE agent_configs SET model = 'patcher-main'")
        conn.commit()
        print("Database migration completed successfully: all base URLs set to https://integrate.api.nvidia.com/v1 and all models set to patcher-main.")
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
