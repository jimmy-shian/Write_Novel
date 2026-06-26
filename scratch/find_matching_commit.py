import subprocess
import re
import difflib

# Read temp_agent_json clean structure
with open('scratch/temp_agent_json_utf8.py', 'r', encoding='utf-8') as f:
    temp_text = f.read()

def clean_code(text):
    # Normalize line endings and non-ascii
    text = text.replace('\r\n', '\n')
    # Collapse multiple blank lines to a single blank line
    text = re.sub(r'\n\s*\n', '\n', text)
    # Remove non-ascii
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    return text

clean_temp = clean_code(temp_text)

# Get all commits
commits_output = subprocess.check_output(['git', 'log', '--format=%H %s']).decode('utf-8')
commits = [line.split(' ', 1) for line in commits_output.strip().split('\n')]

for commit_hash, commit_msg in commits:
    try:
        old_bytes = subprocess.check_output(['git', 'show', f'{commit_hash}:agent_json.py'])
        old_text = old_bytes.decode('utf-8')
        clean_old = clean_code(old_text)
        
        ratio = difflib.SequenceMatcher(None, clean_temp, clean_old).ratio()
        print(f"Commit {commit_hash[:8]} ({commit_msg[:40]}): similarity ratio = {ratio:.4f}")
        if ratio > 0.99:
            print(f"===> FOUND MATCHING COMMIT: {commit_hash[:8]}!")
    except Exception as e:
        # File might not exist in that commit
        pass
