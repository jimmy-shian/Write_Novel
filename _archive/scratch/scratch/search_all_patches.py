# -*- coding: utf-8 -*-
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

patches_dir = r"C:\Users\user\Desktop\test_html\patches"

print("Searching 'response_format' or 'stream' overrides in patches files:")
for root, dirs, files in os.walk(patches_dir):
    if "node_modules" in root or ".git" in root or "dist" in root:
        continue
    for file in files:
        if file.endswith((".js", ".py", ".html", ".json")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "response_format" in content or "stream" in content:
                    print(f"File: {os.path.relpath(path, patches_dir)}")
                    # Find matching lines
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if "response_format" in line or "stream:" in line or "stream =" in line:
                            print(f"  Line {i+1}: {line.strip()}")
            except Exception as e:
                pass
