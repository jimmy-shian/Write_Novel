# -*- coding: utf-8 -*-
"""
提示詞隔離層封包 (Prompts Isolation Layer Package)
整合與導出專案中所有的主要提示詞、細節修改提示詞、說明書提示詞
"""
from .prompt_main import (
    STORY_ARCHITECT_PROMPT,
    VOLUMES_PLANNER_PROMPT,
    CHARACTER_DESIGNER_PROMPT,
    VOLUME_SKELETON_PROMPT,
    PLOT_PLANNER_PROMPT,
    CHAPTER_WRITER_PROMPT,
    VOLUME_SKELETON_PROMPT_PLUS,
    CHARACTER_DESIGNER_PROMPT_PLUS
)
from .prompt_detail_modifier import (
    EDITOR_PROMPT,
    INCREMENTAL_CHARACTER_PROMPT,
    INCREMENTAL_CHARACTER_APPEND_PROMPT
)
from .prompt_instructions import (
    CO_PILOT_ORCHESTRATOR_PROMPT,
    DIRECTOR_COMMON_FOOTER
)

