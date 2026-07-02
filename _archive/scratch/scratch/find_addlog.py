# -*- coding: utf-8 -*-
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

gateway_path = r"C:\Users\user\Desktop\test_html\patches\gateway.js"

with open(gateway_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for addLog in gateway.js:")
for i, line in enumerate(lines):
    if "function addLog" in line:
        # print 10 lines
        for j in range(max(0, i - 2), min(len(lines), i + 15)):
            print(f"Line {j+1}: {lines[j].rstrip()}")
        break
conn.close()
