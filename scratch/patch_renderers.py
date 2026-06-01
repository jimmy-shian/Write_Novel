# -*- coding: utf-8 -*-
import os

file_path = "static/renderers.js"
temp_path = "static/renderers.js.tmp"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = """                                    const eventText = typeof e === 'string' ? e : [e.action, e.scene, e.consequence].filter(Boolean).join(' ➔ ') || JSON.stringify(e);"""

replacement = """                                    let eventText = '';
                                    if (typeof e === 'string') {
                                        eventText = e;
                                    } else if (typeof e === 'object' && e !== null) {
                                        eventText = e.description || e.content || e.action || '';
                                        if (!eventText) {
                                            eventText = [e.scene, e.consequence].filter(Boolean).join(' ➔ ') || JSON.stringify(e);
                                        }
                                    }"""

if target in content:
    content = content.replace(target, replacement)
    
    # Save using bypass
    if os.path.exists(temp_path):
        os.remove(temp_path)
    os.rename(file_path, temp_path)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    os.remove(temp_path)
    print("SUCCESS: static/renderers.js patched successfully!")
else:
    print("ERROR: Target string not found in static/renderers.js!")
