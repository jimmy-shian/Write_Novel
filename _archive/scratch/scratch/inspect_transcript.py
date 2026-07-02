import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\user\.gemini\antigravity\brain\a30c76c7-7d80-4c51-ba2a-6b3b59489ed1\.system_generated\logs\transcript.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            step = json.loads(line)
            content = step.get("content", "")
            if "【總監階段評估 (plot)】" in content:
                print(f"--- STEP {step.get('step_index')} ---")
                print("Type:", step.get("type"))
                # If there are tool calls or specific prompt content
                if "tool_calls" in step:
                    print("Tool Calls:", step["tool_calls"])
                print("Content:", content[:1000])
                print("="*80)
        except Exception as e:
            pass
