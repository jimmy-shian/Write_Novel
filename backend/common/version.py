# -*- coding: utf-8 -*-
"""
Version Single Source of Truth helper for backend.
Reads root version.json.
"""
import json
import os
from functools import lru_cache
from typing import Dict, Any

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_VERSION_FILE = os.path.join(_ROOT_DIR, 'version.json')

@lru_cache(maxsize=1)
def get_app_info() -> Dict[str, Any]:
    try:
        if os.path.exists(_VERSION_FILE):
            with open(_VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {'version': '4.0.0', 'appName': 'AI Novel Factory', 'codename': 'ObsidianGraphiti'}

def get_version() -> str:
    return str(get_app_info().get('version', '4.0.0'))

VERSION = get_version()
