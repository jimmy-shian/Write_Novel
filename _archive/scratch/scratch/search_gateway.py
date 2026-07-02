# -*- coding: utf-8 -*-
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

gateway_path = r"C:\Users\user\Desktop\test_html\patches\gateway.js"

with open(gateway_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for '/chat/completions' or 'stream' or 'response_format' in gateway.js:")
for i, line in enumerate(lines):
    if "chat/completions" in line or "stream" in line or "response_format" in line or "json" in line:
        # Limit output
        if any(term in line for term in ["chat/completions", "stream", "response_format", "json_object"]):
            print(f"Line {i+1}: {line.strip()}")
