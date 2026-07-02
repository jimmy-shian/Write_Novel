# -*- coding: utf-8 -*-
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

appdata = os.environ.get("APPDATA", "")
localappdata = os.environ.get("LOCALAPPDATA", "")

print("Searching for 'gateway.db' in AppData...")
search_dirs = [appdata, localappdata]
found = False

for d in search_dirs:
    if not d:
        continue
    for root, dirs, files in os.walk(d):
        # Limit search depth or skip certain heavy folders
        if any(skip in root for skip in ["Microsoft", "Google", "npm", "pip", "cache"]):
            continue
        if "gateway.db" in files:
            path = os.path.join(root, "gateway.db")
            print("Found active gateway.db at:", path)
            found = True

if not found:
    print("gateway.db not found in standard AppData folders.")
