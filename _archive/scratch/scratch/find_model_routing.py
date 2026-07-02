# -*- coding: utf-8 -*-
gateway_path = r"C:\Users\user\Desktop\test_html\patches\gateway.js"

with open(gateway_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching for model resolution in gateway.js:")
for i, line in enumerate(lines):
    if "model_id" in line or "modelGroup" in line or "configuredModels" in line:
        if any(term in line for term in ["model_id", "modelGroup", "configuredModels"]):
            print(f"Line {i+1}: {line.strip()}")
