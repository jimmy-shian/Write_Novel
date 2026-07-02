# -*- coding: utf-8 -*-
import sqlite3
import re
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

ids = ["a49c3f9e-5b2e-4f5d-8258-e618f79c1a6e", "f77b3465-d23b-46e8-9e39-5f157cf2fbb9"]

def clean_and_parse(content):
    print(f"Original content starts with: {repr(content[:50])}")
    print(f"Original content ends with: {repr(content[-50:])}")
    
    # Strip think tags
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    
    # Try to find JSON block
    # Let's see what happens if we find the first '{' and last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    
    if first_brace != -1 and last_brace != -1:
        json_str = cleaned[first_brace:last_brace+1]
        try:
            parsed = json.loads(json_str)
            print("SUCCESSFULLY PARSED JSON!")
            return parsed
        except Exception as e:
            print(f"Failed to parse extracted JSON block: {e}")
            # Try to print around the error if we can
            return None
    else:
        print("Could not find both open and close braces!")
        return None

for nid in ids:
    print(f"\n=================== {nid} ===================")
    wb = cursor.execute("SELECT * FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC LIMIT 1", (nid,)).fetchone()
    if wb:
        clean_and_parse(wb['content'])
    else:
        print("No worldbuilding record.")

conn.close()
