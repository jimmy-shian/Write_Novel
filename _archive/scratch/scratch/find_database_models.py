# -*- coding: utf-8 -*-
db_js_path = r"C:\Users\user\Desktop\test_html\patches\database.js"

with open(db_js_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Searching database.js for models config:")
for i, line in enumerate(lines):
    if "models_config" in line or "modelsConfig" in line or "models" in line:
        if any(term in line for term in ["models_config", "CREATE TABLE", "defaultModels"]):
            print(f"Line {i+1}: {line.strip()}")
