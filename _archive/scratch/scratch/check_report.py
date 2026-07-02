import sys
import os
sys.path.append(os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from db import generate_validation_report, detect_current_stage, get_novel

novel_id = 'd17af413-03be-4ffe-93a9-3603f8ff9839'
print("--- STAGE DETECTION ---")
stage = detect_current_stage(novel_id)
print(f"Current Stage Detected: {stage}")

print("\n--- VALIDATION REPORT ---")
report = generate_validation_report(novel_id)
print(report)
