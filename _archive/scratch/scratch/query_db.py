# -*- coding: utf-8 -*-
import os
import sys
import json

# Add parent directory to path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def query():
    output_lines = []
    novel_id = 'd17af413-03be-4ffe-93a9-3603f8ff9839'
    output_lines.append(f"Target Novel ID: {novel_id}")
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM novels WHERE id = ?", (novel_id,))
    row = cursor.fetchone()
    if not row:
        output_lines.append("Novel not found!")
        write_output(output_lines)
        conn.close()
        return
        
    novel_title = row['title']
    output_lines.append(f"Novel Title: {novel_title}")
    
    # 2. Get the latest worldbuilding
    wb = db.get_latest_worldbuilding(novel_id)
    if not wb:
        output_lines.append("No worldbuilding found.")
        write_output(output_lines)
        conn.close()
        return
        
    # 3. Parse worldview to JSON and print key turning points and foreshadowing seeds
    parsed_wb = db.parse_worldview_to_json(wb["content"])
    seeds = parsed_wb.get("foreshadowing_seeds", [])
    turns = parsed_wb.get("key_turning_points", [])
    
    output_lines.append("\n=== Worldbuilding Foreshadowing Seeds ===")
    for i, s in enumerate(seeds):
        output_lines.append(f"Seed-{i+1}: {s}")
        
    output_lines.append("\n=== Worldbuilding Key Turning Points ===")
    for j, t in enumerate(turns):
        output_lines.append(f"Turn-{j+1}: {t}")
        
    # 4. Get the blueprint
    blueprint = db.get_global_foreshadowing_blueprint(novel_id)
    turning_allocations = blueprint.get("turning_allocations", [])
    foreshadowing_allocations = blueprint.get("foreshadowing_allocations", [])
    
    output_lines.append("\n=== Blueprint Allocations ===")
    output_lines.append("Turning Allocations (jdx -> chapter_index):")
    for jdx, chap in enumerate(turning_allocations):
        if jdx < len(turns):
            output_lines.append(f"  Turn-{jdx+1} (\"{turns[jdx][:40]}...\") is allocated to Chapter {chap}")
            
    # 5. Retrieve Chapter 246's outline
    plot_data = db.get_stitched_plot(novel_id)
    chapters_outlines = plot_data.get("chapters", [])
    ch246 = next((ch for ch in chapters_outlines if int(ch.get("chapter_index", 0)) == 246), None)
    
    output_lines.append("\n=== Chapter 246 Detail ===")
    if ch246:
        output_lines.append(json.dumps(ch246, ensure_ascii=False, indent=2))
    else:
        output_lines.append("Chapter 246 not found in stitched plot.")
        chaps_found = [int(c.get("chapter_index", 0)) for c in chapters_outlines]
        output_lines.append(f"Stitched plot chapters count: {len(chapters_outlines)}")
        output_lines.append(f"Stitched plot chapter indexes present: {chaps_found[:20]} ... {chaps_found[-20:] if len(chaps_found) > 20 else ''}")
        
    # 6. Check validation report's specific warnings for Ch 246
    output_lines.append("\n=== Running Validation Report ===")
    report = db.generate_validation_report(novel_id)
    output_lines.append(report)
    
    write_output(output_lines)
    conn.close()

def write_output(lines):
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_db_output.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Results written to {output_path}")

if __name__ == "__main__":
    query()
