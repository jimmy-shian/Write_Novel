import subprocess, re, os

HUNK_ASSIGNMENTS = {
    # hunk_index (1-based) -> commit_label
    "commit3": {2, 3, 19},          # 索引補正
    "commit4": {1, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21},  # 管線重構（含hideIndicator清理）
    "commit6": {6},                  # streamAPI maxRetries
}

def extract_hunks(file_path):
    """Extract individual hunks from git diff"""
    result = subprocess.run(['git', 'diff', file_path], capture_output=True)
    text = result.stdout.decode('utf-8', errors='replace')
    lines = text.split('\n')
    
    # Find the diff header (first @@ line)
    header_lines = []
    hunk_start = None
    hunks = []
    
    for i, line in enumerate(lines):
        if line.startswith('@@ '):
            if hunk_start is not None:
                hunks.append(header_lines + lines[hunk_start:i])
            else:
                # First hunk - save header
                header_lines = lines[:i]
            hunk_start = i
    
    # Last hunk
    if hunk_start is not None:
        hunks.append(header_lines + lines[hunk_start:])
    
    return hunks

def create_patch(hunks, indices):
    """Create a patch from selected hunk indices (1-based)"""
    selected = [hunks[i-1] for i in sorted(indices)]
    patch_text = '\n'.join(selected)
    return patch_text

def apply_patch(patch_text, file_path):
    """Apply a patch to staged area"""
    # Write patch to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False, encoding='utf-8') as f:
        f.write(patch_text)
        patch_path = f.name
    
    try:
        result = subprocess.run(['git', 'apply', '--cached', patch_path], capture_output=True)
        if result.returncode != 0:
            err = result.stderr.decode('utf-8', errors='replace')
            print(f"  ❌ Patch apply failed: {err[:300]}")
            return False
        return True
    finally:
        os.unlink(patch_path)

# Main
file_path = 'static/app.js'
hunks = extract_hunks(file_path)
print(f"Extracted {len(hunks)} hunks from {file_path}")

for commit_name, indices in HUNK_ASSIGNMENTS.items():
    print(f"\n--- Creating patch for {commit_name} ---")
    patch = create_patch(hunks, indices)
    patch_len = len(patch)
    hunk_count = len(indices)
    print(f"  Patch size: {patch_len} chars, {hunk_count} hunks")
    
    # Apply to staged area
    success = apply_patch(patch, file_path)
    if success:
        print(f"  ✅ Applied successfully")
    else:
        print(f"  ❌ Failed to apply")
        break
    
print("\nDone")