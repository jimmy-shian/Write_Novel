import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

print("Running db_init to trigger sync...")
db.db_init()
print("db_init completed successfully!")

configs = db.get_agent_configs()
print(f"Loaded {len(configs)} agent configurations from database:")
for agent, cfg in configs.items():
    print(f"  {agent}: model={cfg['model']} | temp={cfg['temperature']} | base_url={cfg['base_url']}")
