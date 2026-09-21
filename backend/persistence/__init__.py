# -*- coding: utf-8 -*-
from backend.persistence.connection import (
    AGENT_DEFAULTS,
    DB_PATH,
    _convert_obj_to_traditional,
    _to_traditional,
    get_db_connection,
)
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.volumes import _get_clean_chapter_count
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.narrative_memory import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *
from backend.persistence.repositories.temporal_graph import *
from backend.persistence.repositories.story_terms import *
from backend.persistence.repositories.draft_proposals import *
from backend.persistence.repositories.chat_memory import *
from backend.persistence.repositories.preferences import *
from backend.persistence.repositories.narrative import *
from backend.persistence.repositories.geometry import *

# 自動確保資料庫 schema 完整性（包括新版 Narrative 體系表格）
try:
    db_init()
except Exception as _init_exc:
    pass


