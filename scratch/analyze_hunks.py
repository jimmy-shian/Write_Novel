import subprocess, re

# Get the full diff
result = subprocess.run(['git', 'diff', 'static/app.js'], capture_output=True)
diff_text = result.stdout.decode('utf-8', errors='replace')

lines = diff_text.split('\n')

# Find all hunk headers
hunk_positions = []
for i, line in enumerate(lines):
    if line.startswith('@@ '):
        m = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', line)
        if m:
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) else 1
            hunk_positions.append({
                'line_idx': i,
                'old_start': old_start,
                'old_count': old_count,
                'new_start': new_start,
                'new_count': new_count
            })

print(f'Total hunks: {len(hunk_positions)}')
for idx, h in enumerate(hunk_positions):
    end = hunk_positions[idx+1]['line_idx'] if idx+1 < len(hunk_positions) else len(lines)
    hunk_lines = lines[h['line_idx']:end]
    print(f'Hunk {idx+1}: @@ -{h["old_start"]},{h["old_count"]} +{h["new_start"]},{h["new_count"]} @@, {len(hunk_lines)} lines')
    for l in hunk_lines[1:4]:
        print(f'  {l[:100]}')
    print()