import os

# Use bytes path to bypass Windows unicode mapping/replacement issues in absolute path
filepath = b"incremental_patch_engine.py"
print(f"Opening file (bytes): {filepath}")

with open(filepath, "rb") as f:
    content_bytes = f.read()

content = content_bytes.decode("utf-8")

target = """            else:
                # Whole characters replace (e.g. revision)
                new_list = payload.get("characters", payload) if isinstance(payload, dict) else payload
                if isinstance(new_list, list):
                    current_chars["characters"] = new_list
                return current_chars"""

replacement = """            else:
                # Whole characters replace (e.g. revision) - smart merge by name
                new_list = payload.get("characters", payload) if isinstance(payload, dict) else payload
                if isinstance(new_list, list):
                    existing_chars = current_chars.get("characters", [])
                    existing_by_name = {c.get("name"): c for c in existing_chars if isinstance(c, dict) and c.get("name")}
                    
                    merged_chars = []
                    # First, keep all existing characters in their original order, updating them if they are in the new list
                    updated_names = set()
                    for c in existing_chars:
                        name = c.get("name")
                        matched = None
                        for nc in new_list:
                            if isinstance(nc, dict) and nc.get("name") == name:
                                matched = nc
                                break
                        if matched:
                            # Update existing character
                            merged_c = c.copy()
                            merged_c.update(matched)
                            merged_chars.append(merged_c)
                            updated_names.add(name)
                        else:
                            # Preserve unmodified character
                            merged_chars.append(c)
                    
                    # Next, append any new characters that were not in the original list
                    for nc in new_list:
                        if isinstance(nc, dict):
                            name = nc.get("name")
                            if name and name not in updated_names:
                                merged_chars.append(nc)
                                
                    current_chars["characters"] = merged_chars
                return current_chars"""

if target in content:
    new_content = content.replace(target, replacement)
    try:
        with open(filepath, "wb") as f:
            f.write(new_content.encode("utf-8"))
        print("SUCCESS: File updated successfully using bytes path!")
    except Exception as e:
        print(f"FAILED to write: {e}")
else:
    print("FAILED: Target content not found!")
