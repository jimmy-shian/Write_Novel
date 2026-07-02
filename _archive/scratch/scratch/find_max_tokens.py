# -*- coding: utf-8 -*-
gateway_path = r"C:\Users\user\Desktop\test_html\patches\gateway.js"

with open(gateway_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for max_tokens in gateway.js:")
for i, line in enumerate(lines):
    if "max_tokens" in line:
        print(f"Line {i+1}: {line.strip()}")
