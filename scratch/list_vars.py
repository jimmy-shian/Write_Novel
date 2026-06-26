import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scratch/temp_agent_json_utf8.py', 'r', encoding='utf-8') as f:
    for line in f:
        line_strip = line.strip()
        if not line_strip:
            continue
        if '=' in line_strip and not line[0].isspace() and not line.startswith('#') and not line.startswith('"') and not line.startswith("'"):
            print(line_strip)
