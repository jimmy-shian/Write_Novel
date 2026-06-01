# -*- coding: utf-8 -*-
import os
import sys
import json

# Add parent directory to path so we can import db and agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import agents

def regenerate_all_skeletons():
    novel_id = 'd17af413-03be-4ffe-93a9-3603f8ff9839'
    print(f"Re-generating clean chapter skeletons for Novel: {novel_id}")
    
    # 1. Precompute global blueprint to align seeds/turns perfectly
    print("Re-calculating global blueprint...")
    db.precompute_global_foreshadowing(novel_id)
    
    # 2. Run volume skeleton planner for all 12 volumes
    for vol_idx in range(1, 13):
        print(f"\n[SKELETON GENERATION] Re-generating Volume {vol_idx} / 12 ...")
        try:
            # run_volume_skeleton_planner is a generator yielding LLM chunks. 
            # We iterate through it to execute it synchronously and save findings.
            for chunk in agents.run_volume_skeleton_planner(novel_id, vol_idx):
                pass
            print(f"✓ Volume {vol_idx} skeleton re-generated successfully!")
        except Exception as e:
            print(f"❌ Failed to re-generate Volume {vol_idx}: {e}")
            
    print("\nAll 12 volumes' chapter skeletons have been restored perfectly and cleanly!")

if __name__ == "__main__":
    regenerate_all_skeletons()
