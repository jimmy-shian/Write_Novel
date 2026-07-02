# -*- coding: utf-8 -*-
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

gateway_path = r"C:\Users\user\Desktop\test_html\patches\gateway.js"

with open(gateway_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for validateContent in gateway.js:")
for i, line in enumerate(lines):
    if "validateContent" in line or "function validate" in line:
        print(f"Line {i+1}: {line.strip()}")
